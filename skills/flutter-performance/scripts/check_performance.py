#!/usr/bin/env python3
"""check_performance.py: find performance traps in a Flutter project (read-only).

Usage:
  python3 -I check_performance.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (list-item widgets are found across
             files); only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  PERF-001 eager-list-over-data           PERF-007 global-key-in-build
  PERF-002 shrinkwrap-nested-scrollable   PERF-008 watch-whole-for-one-field
  PERF-003 intrinsic-in-list-item         PERF-009 setstate-per-frame-listener
  PERF-004 image-full-size-decode-in-list PERF-010 sort-in-build
  PERF-005 opacity-animated-or-in-list    PERF-011 json-decode-on-ui-isolate
  PERF-006 savelayer-in-list-item

A "list item" is code inside the itemBuilder of a lazy list or grid (ListView.builder,
GridView.builder, SliverList, SliverChildBuilderDelegate, ...), or inside a project widget
that such an itemBuilder constructs directly (one hop, across files). PageView items are
full-screen pages, not list items.

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so.

Suppression (in the analysed code):
  // perf-ignore: PERF-001 <reason>        on the reported line or the line above
  // perf-ignore-file: PERF-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/performance@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
SKIP_ROLES = ('barrel', 'di')

RULES = {
    'PERF-001': ('eager-list-over-data', 'medium',
                 'A scrollable builds one child per data item up front (children: list.map(...), List.generate, '
                 'collection-for), so every item is built and laid out even when off screen. Use a builder '
                 'constructor (ListView.builder, GridView.builder, SliverList.builder).'),
    'PERF-002': ('shrinkwrap-nested-scrollable', 'medium',
                 'A shrinkWrap: true list sits inside another scroll view or list item, so it lays out every child '
                 'to measure itself and loses laziness. Use one CustomScrollView with slivers instead.'),
    'PERF-003': ('intrinsic-in-list-item', 'medium',
                 'IntrinsicHeight/IntrinsicWidth inside a list item adds a speculative layout pass per item, every '
                 'time the list lays out (can be O(n^2) when nested). Size the row explicitly or align with '
                 'CrossAxisAlignment / Table.'),
    'PERF-004': ('image-full-size-decode-in-list', 'low',
                 'An image in a list item is decoded at its full source resolution. Set cacheWidth/cacheHeight '
                 '(or wrap the provider in ResizeImage; memCacheWidth for cached_network_image) to the display '
                 'size times devicePixelRatio.'),
    'PERF-005': ('opacity-animated-or-in-list', 'low',
                 'An Opacity widget is animated or repeated per list item; intermediate values composite a layer '
                 'for the whole subtree. Animate with FadeTransition/AnimatedOpacity; for static translucency paint '
                 'with a translucent colour.'),
    'PERF-006': ('savelayer-in-list-item', 'medium',
                 'An offscreen-layer or path-clip widget (BackdropFilter, ShaderMask, ClipPath) is built for every '
                 'list item, which multiplies saveLayer passes or path clips on the raster thread while scrolling.'),
    'PERF-007': ('global-key-in-build', 'medium',
                 'A GlobalKey is created inside build() or an itemBuilder: every rebuild makes a new key, so the '
                 'subtree is torn down and remounted (state lost) and the global key registry churns.'),
    'PERF-008': ('watch-whole-for-one-field', 'low',
                 'build() watches a whole object to read one field, so the widget rebuilds on every change of any '
                 'field. Select only that field.'),
    'PERF-009': ('setstate-per-frame-listener', 'medium',
                 'A scroll or animation listener calls setState unconditionally, rebuilding the whole State on '
                 'every scroll offset or animation tick.'),
    'PERF-010': ('sort-in-build', 'low',
                 'A list is sorted inside build(): O(n log n) work on every rebuild, and sort() mutates the list '
                 'in place (possibly state you do not own). Sort once in the state layer.'),
    'PERF-011': ('json-decode-on-ui-isolate', 'info',
                 'A JSON list payload is decoded synchronously in the data layer, on the UI isolate. For large or '
                 'unbounded payloads, parse it in a background isolate (Isolate.run / compute) inside the same '
                 'source or repository.'),
}

FIX_BY_PROFILE = {
    'PERF-001': {
        'mvn': 'MVN: keep the list in the notifier state and render ListView.builder(itemCount: state.items.length, ...)',
        'riverpod': 'Riverpod: watch the list provider and render ListView.builder(itemCount: items.length, ...)',
        'mvvm': 'MVVM: ListenableBuilder(listenable: viewModel, builder: ...) around ListView.builder over viewModel.items',
        'bloc': 'Bloc: BlocBuilder/BlocSelector for state.items, then ListView.builder(itemCount: items.length, ...)',
        'provider': 'Provider: context.select((M m) => m.items) then ListView.builder(itemCount: items.length, ...)',
        'getx': 'GetX: Obx(() => ListView.builder(itemCount: c.items.length, itemBuilder: ...))',
        'mvc': 'MVC: render controller.items with ListView.builder',
        'setstate': 'setState: render the State list with ListView.builder(itemCount: _items.length, ...)',
    },
    'PERF-008': {
        'mvn': 'MVN: ref.watch(xProvider.select((s) => s.field)) (works on the sealed state too: select a derived value)',
        'riverpod': 'Riverpod: ref.watch(xProvider.select((s) => s.field)); for AsyncValue select on (s) => s.valueOrNull?.field',
        'provider': 'Provider: context.select((Model m) => m.field)',
        'bloc': 'Bloc: context.select((XBloc b) => b.state.field), or BlocSelector<XBloc, XState, T>',
        'mvvm': 'MVVM: listen to a narrower ValueListenable, or context.select when the view model is provided',
    },
    'PERF-009': {
        'mvn': 'MVN: keep the scroll offset out of setState; drive the one dependent widget with ListenableBuilder(listenable: _scroll) or a ValueNotifier',
        'riverpod': 'Riverpod: drive only the dependent widget with ListenableBuilder(listenable: _scroll), or setState only when a derived bool flips',
        'mvvm': 'MVVM: wrap only the dependent widget in ListenableBuilder(listenable: _scroll); the view model never sees scroll offsets',
        'bloc': 'Bloc: do not emit per scroll tick; ListenableBuilder for visuals, add an event only when a threshold is crossed (e.g. load more)',
        'provider': 'Provider: ListenableBuilder(listenable: _scroll) around the dependent widget, or setState only when a derived bool flips',
        'getx': 'GetX: update an Rx only when a threshold flips and wrap just that widget in Obx',
        'mvc': 'MVC: rebuild only the dependent widget (ListenableBuilder), or setState when a derived bool flips',
        'setstate': 'setState: compute the derived value, call setState only when it changes, or use ListenableBuilder(listenable: _scroll)',
    },
    'PERF-010': {
        'mvn': 'MVN: sort in the use case or notifier and expose the sorted list in state',
        'riverpod': 'Riverpod: expose a derived provider (ref.watch(items) sorted once), not a sort in build',
        'mvvm': 'MVVM: sort in the view model (a getter cached on change) or in the repository',
        'bloc': 'Bloc: sort in the event handler before emit(state.copyWith(items: sorted))',
        'provider': 'Provider: sort in the ChangeNotifier when the data changes',
        'getx': 'GetX: sort in the controller (or a computed RxList) when the data changes',
        'mvc': 'MVC: sort in the controller or model',
        'setstate': 'setState: sort when the data arrives (initState / the load callback), not in build',
    },
    'PERF-011': {
        'mvn': 'MVN: decode in the data source: final list = await Isolate.run(() => parseItems(body)); the notifier only awaits the use case',
        'riverpod': 'Riverpod: decode in the repository with await Isolate.run(() => parseItems(body)), never in a provider build or widget',
        'mvvm': 'MVVM: decode in the service/api client with await Isolate.run(...); repositories return models, view models never parse',
        'bloc': 'Bloc: decode in the data provider/repository with await Isolate.run(...); blocs only await the repository',
        'provider': 'Provider: decode in the service with await Isolate.run(...), never in the ChangeNotifier',
        'getx': 'GetX: decode in the provider/repository (GetConnect decoder or Isolate.run), not in the controller',
        'mvc': 'MVC: decode in the model/service layer with Isolate.run',
        'setstate': 'setState: decode in a service function with Isolate.run, not in the State',
    },
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
SUPPRESS_RE = re.compile(r'perf-ignore(-file)?\s*:\s*((?:PERF-\d{3})(?:\s*,\s*PERF-\d{3})*)\s*(.*)')

# ---------------------------------------------------------------------------------------- lexing

def lex(text):
    """Return (code, masked, comments).

    code:    comments blanked (newlines kept), strings intact.
    masked:  comments and string *contents* blanked (quotes kept); safe for bracket matching.
    """
    n = len(text)
    code = list(text)
    masked = list(text)
    comments = []

    def blank(buf, s, e):
        for k in range(s, e):
            if buf[k] != '\n':
                buf[k] = ' '

    def skip_block(i):
        depth, i = 1, i + 2
        while i < n and depth:
            if text.startswith('/*', i):
                depth += 1
                i += 2
            elif text.startswith('*/', i):
                depth -= 1
                i += 2
            else:
                i += 1
        return i

    def skip_expr(i):
        depth = 1
        while i < n:
            c = text[i]
            if text.startswith('//', i):
                j = text.find('\n', i)
                i = n if j < 0 else j
                continue
            if text.startswith('/*', i):
                i = skip_block(i)
                continue
            if c in '\'"' or (c in 'rR' and i + 1 < n and text[i + 1] in '\'"' and not _ident(text, i - 1)):
                i = skip_string(i)
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return n

    def skip_string(i):
        raw = text[i] in 'rR'
        if raw:
            i += 1
        q = text[i]
        delim = q * 3 if text.startswith(q * 3, i) else q
        i += len(delim)
        while i < n:
            if not raw and text[i] == '\\':
                i += 2
                continue
            if text.startswith(delim, i):
                return i + len(delim)
            if len(delim) == 1 and text[i] == '\n':
                return i
            if not raw and text[i] == '$' and i + 1 < n and text[i + 1] == '{':
                i = skip_expr(i + 2)
                continue
            i += 1
        return n

    i = 0
    while i < n:
        c = text[i]
        if c == '/' and text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            blank(code, i, j)
            blank(masked, i, j)
            comments.append((i, j))
            i = j
        elif c == '/' and text.startswith('/*', i):
            j = skip_block(i)
            blank(code, i, j)
            blank(masked, i, j)
            comments.append((i, j))
            i = j
        elif c in '\'"' or (c in 'rR' and i + 1 < n and text[i + 1] in '\'"' and not _ident(text, i - 1)):
            j = skip_string(i)
            p = i + (1 if text[i] in 'rR' else 0)
            q = text[p]
            dl = 3 if text.startswith(q * 3, p) else 1
            blank(masked, p + dl, max(p + dl, j - dl))
            i = j
        else:
            i += 1
    return ''.join(code), ''.join(masked), comments


def _ident(text, i):
    return i >= 0 and (text[i].isalnum() or text[i] in '_$')


def match_pairs(masked, open_c, close_c):
    pairs, stack = {}, []
    for i, c in enumerate(masked):
        if c == open_c:
            stack.append(i)
        elif c == close_c and stack:
            o = stack.pop()
            pairs[o] = i
            pairs[i] = o
    return pairs


class DartFile(object):
    def __init__(self, root, rel):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.masked, self.comments = lex(self.raw)
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.lines = self.raw.split('\n')
        self.braces = match_pairs(self.masked, '{', '}')
        self.parens = match_pairs(self.masked, '(', ')')
        self.brace_opens = sorted(k for k, v in self.braces.items() if self.masked[k] == '{')
        self.parent = {}
        stack = []
        for o in self.brace_opens:
            while stack and self.braces[stack[-1]] < o:
                stack.pop()
            self.parent[o] = stack[-1] if stack else None
            stack.append(o)
        self.role, self.layer = 'other', 'other'
        self.classes = []          # (name, open, close, header)
        self.funcs = []            # (name, header_start, body_open, body_close, is_async)
        self.suppress_line = {}    # line -> {id: reason}
        self.suppress_file = {}    # id -> reason
        self._parse()

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def snippet(self, s, e, limit=110):
        t = ' '.join(self.raw[s:e].split())
        return t if len(t) <= limit else t[:limit - 3] + '...'

    def _parse(self):
        m = self.masked
        for mm in CLASS_RE.finditer(m):
            o = mm.end() - 1
            c = self.braces.get(o)
            if c is not None:
                self.classes.append((mm.group(2) or '', o, c, mm.group(0)))
        for mm in FUNC_RE.finditer(m):
            name = mm.group(1)
            if name in KEYWORDS:
                continue
            po = mm.end() - 1
            pc = self.parens.get(po)
            if pc is None:
                continue
            k = pc + 1
            tail = re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>)', m[k:k + 40])
            if not tail:
                continue
            is_async = bool(tail.group(1) and tail.group(1).startswith('async'))
            bo = k + tail.start(2)
            if tail.group(2) == '{':
                bc = self.braces.get(bo)
                if bc is None:
                    continue
            else:
                bc = expr_end(m, bo + 2)
            self.funcs.append((name, mm.start(1), bo, bc, is_async))
        for s, e in self.comments:
            txt = self.raw[s:e]
            sm = SUPPRESS_RE.search(txt)
            if not sm:
                continue
            ids = [x.strip() for x in sm.group(2).split(',')]
            reason = sm.group(3).strip().strip('*/').strip() or '(no reason given)'
            if sm.group(1):
                for i in ids:
                    self.suppress_file[i] = reason
            else:
                ln = self.line_of(s)
                d = self.suppress_line.setdefault(ln, {})
                for i in ids:
                    d[i] = reason

    def enclosing_func(self, pos):
        best = None
        for f in self.funcs:
            if f[2] <= pos <= f[3] and (best is None or f[2] > best[2]):
                best = f
        return best

    def enclosing_class(self, pos):
        best = None
        for c in self.classes:
            if c[1] < pos < c[2] and (best is None or c[1] > best[1]):
                best = c
        return best

    def func_named(self, name, cls=None):
        for f in self.funcs:
            if f[0] == name and (cls is None or cls[1] < f[2] < cls[2]):
                return f
        return None


CLASS_RE = re.compile(r'\b(?:(?:abstract|sealed|final|base|interface|mixin)\s+)*(class|mixin|extension)\s+'
                      r'([A-Za-z_]\w*)?[^{;]*?\{')
FUNC_RE = re.compile(r'(?<![\w.$])([A-Za-z_$][\w$]*)[ \t]*(?:<[^<>(){};]*(?:<[^<>(){};]*>[^<>(){};]*)*>[ \t]*)?\(')
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'on', 'return', 'assert', 'super', 'this', 'new', 'await',
            'throw', 'when', 'with', 'yield', 'print', 'sizeOf', 'typeOf', 'const', 'else', 'do', 'try', 'in', 'is',
            'as', 'case', 'late', 'final', 'var'}


def expr_end(m, i):
    depth, n = 0, len(m)
    while i < n:
        c = m[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return i
            depth -= 1
        elif c in ',;' and depth == 0:
            return i
        i += 1
    return n


def split_args(df, po):
    """Named and positional args of the call whose '(' is at po: list of (name, vstart, vend)."""
    pc = df.parens.get(po)
    if pc is None:
        return [], po
    m = df.masked
    out, depth, start = [], 0, po + 1
    i = po + 1
    while i <= pc:
        c = m[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0 or i == pc:
                if i == pc:
                    seg = (start, i)
                    _add_arg(m, seg, out)
                    break
            depth -= 1
        elif c == ',' and depth == 0:
            _add_arg(m, (start, i), out)
            start = i + 1
        i += 1
    return out, pc


def _add_arg(m, seg, out):
    s, e = seg
    txt = m[s:e]
    if not txt.strip():
        return
    nm = re.match(r'\s*([A-Za-z_]\w*)\s*:(?!:)', txt)
    if nm:
        out.append((nm.group(1), s + nm.end(), e))
    else:
        out.append((None, s, e))


def arg_map(df, po):
    args, pc = split_args(df, po)
    d = {}
    for name, s, e in args:
        if name:
            d[name] = (s, e)
    return d, pc


# ---------------------------------------------------------------------------------------- widget index

CALL_RE = re.compile(r'(?<![\w$.])(?:const\s+|new\s+)?(_?[A-Z][\w$]*(?:[ \t]*\.[ \t]*[a-z]\w*)?)[ \t]*'
                     r'(?:<[^()<>;{}]*(?:<[^()<>;{}]*>[^()<>;{}]*)*>[ \t]*)?\(')
WIDGET_HEADER = re.compile(r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|'
                           r'HookWidget|HookConsumerWidget|StatelessHookWidget|StatefulHookWidget|'
                           r'StatefulHookConsumerWidget|GetView\s*<|GetWidget\s*<|AnimatedWidget|'
                           r'ImplicitlyAnimatedWidget|SingleChildStatelessWidget|\w*(?:Widget|View|Page|Screen)\b)')
STATE_HEADER = re.compile(r'\bextends\s+(?:State|ConsumerState|AnimatedWidgetBaseState|ImplicitlyAnimatedWidgetState)'
                          r'\s*<\s*(\w+)\s*>')
SCROLLABLES = ('ListView', 'GridView', 'SingleChildScrollView', 'CustomScrollView', 'NestedScrollView',
               'ReorderableListView', 'SliverToBoxAdapter', 'SliverList', 'SliverGrid', 'SliverFillRemaining',
               'SliverPadding', 'MasonryGridView', 'AlignedGridView')
NOT_ITEM_LISTS = ('PageView', 'TabBarView', 'CarouselSlider', 'CarouselView', 'Swiper', 'PreloadPageView',
                  'ListWheelScrollView')
PASS_THROUGH = ('Padding', 'Center', 'Container', 'SizedBox', 'ConstrainedBox', 'Align', 'DecoratedBox', 'ColoredBox',
                'SafeArea', 'Scrollbar', 'CupertinoScrollbar', 'RawScrollbar', 'Material', 'Card', 'Form',
                'Column', 'Row', 'Wrap', 'Flex', 'Expanded', 'Flexible', 'IntrinsicHeight', 'DefaultTextStyle',
                'Theme', 'Builder', 'RefreshIndicator', 'FocusTraversalGroup', 'AnimatedSize', 'ListBody',
                'LimitedBox', 'FractionallySizedBox', 'Semantics', 'MediaQuery', 'GestureDetector', 'InkWell')
ASYNC_MEMBERS = {'value', 'valueOrNull', 'requireValue', 'hasValue', 'hasError', 'isLoading', 'isRefreshing',
                 'isReloading', 'error', 'stackTrace', 'asData', 'asError', 'when', 'maybeWhen', 'map', 'maybeMap',
                 'whenData', 'whenOrNull', 'unwrapPrevious', 'state', 'notifier', 'future', 'stream', 'hashCode',
                 'runtimeType', 'length', 'isEmpty', 'isNotEmpty', 'first', 'last', 'single', 'firstOrNull',
                 'lastOrNull', 'keys', 'values', 'entries', 'iterator', 'reversed'}
IMAGE_CALLS = ('Image.network', 'Image.file', 'Image.memory', 'NetworkImage', 'FileImage', 'MemoryImage',
               'CachedNetworkImage', 'CachedNetworkImageProvider', 'FadeInImage.memoryNetwork',
               'FadeInImage.assetNetwork', 'ExtendedImage.network', 'ExtendedImage.file', 'ExtendedNetworkImageProvider')
IMAGE_SIZING = re.compile(r'\b(?:cacheWidth|cacheHeight|memCacheWidth|memCacheHeight|maxWidthDiskCache|'
                          r'maxHeightDiskCache|imageCacheWidth|imageCacheHeight|placeholderCacheWidth|'
                          r'imageCacheHeight|cacheRawData|compressionRatio)\s*:|\bResizeImage\b')
SAVELAYER = {'BackdropFilter': 'medium', 'ShaderMask': 'low', 'ClipPath': 'low'}
ANIM_BUILDERS = ('AnimatedBuilder', 'TweenAnimationBuilder')


class Calls(object):
    """Every capitalised call (constructor or static) in a file: (name, start, open_paren, close_paren)."""

    def __init__(self, df):
        self.items = []
        for mm in CALL_RE.finditer(df.masked):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            name = re.sub(r'\s+', '', mm.group(1))
            self.items.append((name, mm.start(), po, pc))

    def ancestors(self, pos):
        """Calls whose argument list contains pos, innermost first."""
        out = [c for c in self.items if c[2] < pos < c[3]]
        out.sort(key=lambda c: -c[2])
        return out


def base(name):
    return name.split('.')[0]


def is_item_list(name):
    b = base(name)
    if b in NOT_ITEM_LISTS:
        return False
    return bool(re.search(r'(?:List|Grid)(?:View)?$|ListView|GridView|^Sliver\w*(?:List|Grid)\b|BuilderDelegate$|'
                          r'^SliverAnimated|^SuperListView|^ScrollablePositionedList', b))


def receiver_start(df, pos, lo):
    """Start of the receiver expression that ends right before pos (`a.b(c).d` in `a.b(c).d..sort(`)."""
    m = df.masked
    k = pos
    while k > lo:
        c = m[k - 1]
        if c.isspace() or c.isalnum() or c in '_$.?!':
            k -= 1
        elif c in ')]' and df.parens.get(k - 1) is not None and c == ')':
            k = df.parens[k - 1]
        elif c == ']':
            j, depth = k - 1, 0
            while j > lo:
                if m[j] == ']':
                    depth += 1
                elif m[j] == '[':
                    depth -= 1
                    if depth == 0:
                        break
                j -= 1
            k = j
        else:
            break
    while k < pos and m[k].isspace():
        k += 1
    if m[k:pos].lstrip().startswith(('.', '?', '!')):
        k = pos
    return k


def numeric_literal(text):
    return bool(re.match(r'^\s*(?:const\s+)?-?\d+(?:\.\d+)?\s*$', text))


def class_of_widget(header):
    return bool(WIDGET_HEADER.search(header))


class Checker(object):
    def __init__(self, files, profile):
        self.files = files
        self.profile = profile
        self.findings = []
        self.suppressed = []
        self._seen = set()
        self.stats = {'item_builders': 0, 'item_widgets': 0, 'scrollables': 0, 'images': 0, 'build_methods': 0}

    # -- reporting
    def add(self, df, rid, pos, evidence, note='', severity=None, profile_note=True):
        ln = df.line_of(pos)
        key = (rid, df.rel, ln)
        if key in self._seen:
            return
        self._seen.add(key)
        sev = severity or RULES[rid][1]
        reason = None
        if rid in df.suppress_file:
            reason = df.suppress_file[rid]
        else:
            for l in (ln, ln - 1):
                if rid in df.suppress_line.get(l, {}):
                    reason = df.suppress_line[l][rid]
                    break
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': df.rel, 'line': ln, 'reason': reason})
            return
        prof = FIX_BY_PROFILE.get(rid, {}).get(self.profile, '') if profile_note else ''
        if prof:
            note = (note + '; ' if note else '') + prof
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    def ev(self, df, s, e, limit=110):
        return df.snippet(s, min(e, s + 400), limit)

    # -- indexing
    def index(self):
        self.widget_classes = {}            # name -> (df, [(o, c), ...])
        for df in self.files:
            df.calls = Calls(df)
            df.item_spans = []              # (s, e, origin)
            df.builds = [f for f in df.funcs if f[0] == 'build']
            self.stats['build_methods'] += len(df.builds)
            states = {}
            for name, o, c, header in df.classes:
                sm = STATE_HEADER.search(header)
                if sm:
                    states.setdefault(sm.group(1), []).append((o, c))
            for name, o, c, header in df.classes:
                if name and class_of_widget(header) and not STATE_HEADER.search(header):
                    self.widget_classes[name] = (df, [(o, c)] + states.get(name, []))
        for df in self.files:
            for name, st, po, pc in df.calls.items:
                if not is_item_list(name):
                    continue
                args, _ = arg_map(df, po)
                spans = [args[k] for k in ('itemBuilder', 'builder') if k in args]
                if base(name).endswith('BuilderDelegate') and not spans:
                    pos_args = [a for a in split_args(df, po)[0] if a[0] is None]
                    if pos_args:
                        spans.append((pos_args[0][1], pos_args[0][2]))
                for s, e in spans:
                    df.item_spans.append((s, e, '%s itemBuilder at line %d' % (name, df.line_of(st))))
                    self.stats['item_builders'] += 1
        # one hop: project widgets constructed directly in an itemBuilder
        hop = []
        for df in self.files:
            for s, e, origin in df.item_spans:
                for name, st, po, pc in df.calls.items:
                    if s <= st < e and name in self.widget_classes:
                        hop.append((name, '%s, built in the %s of %s' % (name, origin.split(' at ')[0], df.rel)))
        done = set()
        for name, origin in hop:
            if name in done:
                continue
            done.add(name)
            tdf, spans = self.widget_classes[name]
            self.stats['item_widgets'] += 1
            for o, c in spans:
                tdf.item_spans.append((o, c, origin))

    def item_origin(self, df, pos):
        for s, e, origin in df.item_spans:
            if s <= pos < e:
                return origin
        return None

    def in_build(self, df, pos):
        for f in df.builds:
            if f[2] <= pos <= f[3]:
                return f
        return None

    def run(self):
        self.index()
        for df in self.files:
            if df.layer not in ('data', 'domain') or df.role in ('view', 'widget'):
                self.check_eager_lists(df)
                self.check_shrinkwrap(df)
                self.check_item_widgets(df)
                self.check_opacity(df)
                self.check_global_keys(df)
                self.check_watch_one_field(df)
                self.check_listeners(df)
                self.check_sort_in_build(df)
            self.check_json_decode(df)

    # -- PERF-001 eager list over data
    def collection_of(self, df, s, e):
        """The data expression a `children:` value is built from, or None."""
        m, code = df.masked, df.code
        v = m[s:e].strip()
        vs = s + (len(m[s:e]) - len(m[s:e].lstrip()))
        mm = re.match(r'([A-Za-z_$][\w$]*(?:\s*[?!]?\s*\.\s*[A-Za-z_$][\w$]*)*(?:\s*\([^()]*\))?)\s*[?!]?\s*\.\s*'
                      r'(?:map|mapIndexed|expand)\s*[(<]', v)
        if mm:
            return code[vs:vs + len(mm.group(1))]
        gm = re.match(r'List\s*(?:<[^>]*>)?\s*\.\s*generate\s*\(', v)
        if gm:
            po = vs + gm.end() - 1
            args, _ = split_args(df, po)
            if args:
                return 'List.generate(' + code[args[0][1]:args[0][2]].strip()
        if v.startswith('['):
            inner = m[vs:e]
            self._mixed = self.list_elements(df, vs, e) > 1
            for pat in (r'\.\.\.\s*\??\s*([A-Za-z_$][\w$]*(?:\s*[?!]?\s*\.\s*[A-Za-z_$][\w$]*)*)\s*[?!]?\s*\.\s*'
                        r'(?:map|mapIndexed|expand)\s*[(<]',
                        r'\bfor\s*\(\s*(?:final|var|const)?\s*[\w<>?,\s]*?\s+\w+\s+in\s+([^)]+)\)',
                        r'\bfor\s*\([^;()]*;\s*\w+\s*<=?\s*([^;]+?)\s*;'):
                fm = re.search(pat, inner)
                if fm:
                    return ' '.join(code[vs + fm.start(1):vs + fm.end(1)].split())
            gm = re.search(r'\.\.\.\s*List\s*(?:<[^>]*>)?\s*\.\s*generate\s*\(', inner)
            if gm:
                po = vs + gm.end() - 1
                args, _ = split_args(df, po)
                if args:
                    return 'List.generate(' + code[args[0][1]:args[0][2]].strip()
        return None

    @staticmethod
    def list_elements(df, s, e):
        """Number of top-level elements in the list literal spanning masked[s:e]."""
        m = df.masked
        o = m.find('[', s, e)
        depth, n, seen = 0, 0, False
        for i in range(o + 1, e):
            c = m[i]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                if depth == 0:
                    break
                depth -= 1
            elif c == ',' and depth == 0:
                n += 1 if seen else 0
                seen = False
                continue
            if not c.isspace() and not (depth == 0 and c == ','):
                seen = True
        return n + (1 if seen else 0)

    def bounded(self, df, expr):
        x = expr.strip()
        if x.startswith('List.generate('):
            n = x[len('List.generate('):].strip()
            if numeric_literal(n) or re.match(r'^_?[A-Z_][A-Z0-9_]*$|^_?k[A-Z]\w*$', n):
                return 'a fixed count'
            lm = re.match(r'^(.*?)\s*[?!]?\s*\.\s*length$', n)
            if not lm:
                return 'a count, not a collection'
            x = lm.group(1)
        if re.search(r'^\s*\[|\{', x) and not re.search(r'\w\s*[\[{]', x):
            return 'a literal list'
        if re.search(r'\.values\b(?!\s*\.\s*where)', x) and re.match(r'^_?[A-Z]', x):
            return 'enum values'
        if re.search(r'\.\s*take\s*\(\s*\d+\s*\)', x):
            return 'take(n)'
        if re.search(r'\b\d+\s*\.\.\s*|\bInclusive\b|range\s*\(\s*\d', x):
            return 'a numeric range'
        head = re.match(r'^(?:widget\s*\.\s*)?_?([A-Za-z_$][\w$]*)', x)
        if head:
            name = head.group(1)
            if re.search(r'\b(?:static\s+)?const\s+(?:[\w<>?,\s]+\s)?_?%s\s*=' % re.escape(name), df.masked) or \
                    re.search(r'\bfinal\s+(?:List<[^>]*>\s+)?_?%s\s*=\s*(?:const\s*)?(?:<[^>]*>\s*)?\[' %
                              re.escape(name), df.masked):
                return 'a constant list'
            if re.match(r'^_?[A-Z][A-Z0-9_]+$|^k[A-Z]', name):
                return 'a constant'
        return None

    def check_eager_lists(self, df):
        m = df.masked
        for name, st, po, pc in df.calls.items:
            b = base(name)
            scroll = None
            if b in ('ListView', 'GridView') and name in ('ListView', 'GridView', 'GridView.count', 'GridView.extent'):
                scroll = name
            elif b in ('Column', 'Row', 'Wrap', 'ListBody', 'Flex'):
                for a in df.calls.ancestors(st):
                    if base(a[0]) == 'SingleChildScrollView':
                        scroll = '%s in SingleChildScrollView' % b
                        break
                    if base(a[0]) not in PASS_THROUGH:
                        break
            if not scroll:
                continue
            args, _ = arg_map(df, po)
            if 'children' not in args:
                continue
            if b in ('ListView', 'GridView'):
                self.stats['scrollables'] += 1
            s, e = args['children']
            self._mixed = False
            coll = self.collection_of(df, s, e)
            if not coll:
                continue
            why = self.bounded(df, coll)
            if why:
                continue
            horizontal = bool(re.search(r'\bscrollDirection\s*:\s*Axis\s*\.\s*horizontal', m[po:pc])) or b == 'Row'
            for a in df.calls.ancestors(st):
                if base(a[0]) == 'SingleChildScrollView' and \
                        re.search(r'\bscrollDirection\s*:\s*Axis\s*\.\s*horizontal', m[a[2]:a[3]]):
                    horizontal = True
                    break
                if base(a[0]) not in PASS_THROUGH:
                    break
            sev = 'low' if horizontal or self._mixed else None
            note = '%s over `%s`' % (scroll, ' '.join(coll.split())[:60])
            if horizontal:
                note += ' (horizontal strip: usually short)'
            elif self._mixed:
                note += ' mixed with fixed children: CustomScrollView with a SliverList.builder for the data part'
            self.add(df, 'PERF-001', st, self.ev(df, st, s + 60), note=note, severity=sev)

    # -- PERF-002 shrinkWrap nested in another scrollable or list item
    def check_shrinkwrap(self, df):
        m = df.masked
        for name, st, po, pc in df.calls.items:
            b = base(name)
            if b not in ('ListView', 'GridView', 'CustomScrollView', 'ReorderableListView', 'MasonryGridView',
                         'AlignedGridView'):
                continue
            args, _ = arg_map(df, po)
            if 'shrinkWrap' not in args or m[args['shrinkWrap'][0]:args['shrinkWrap'][1]].strip() != 'true':
                continue
            outer = None
            for a in df.calls.ancestors(st):
                if base(a[0]) in SCROLLABLES and a[1] != st:
                    outer = '%s at line %d' % (a[0], df.line_of(a[1]))
                    break
            origin = self.item_origin(df, st)
            if not outer and origin:
                outer = 'a list item (%s)' % origin
            if not outer:
                continue
            lazy = '.' in name and name.split('.')[1] in ('builder', 'separated', 'custom') or 'itemBuilder' in args
            horizontal = bool(re.search(r'\bscrollDirection\s*:\s*Axis\s*\.\s*horizontal', m[po:pc]))
            sev = 'medium' if lazy and not horizontal else 'low'
            note = 'inside %s%s' % (outer, '; a builder list that is no longer lazy' if lazy else
                                    '; children are already eager, the cost is the extra layout')
            self.add(df, 'PERF-002', st, self.ev(df, st, args['shrinkWrap'][1]), note=note, severity=sev)

    # -- PERF-003 / 004 / 006: expensive widgets inside list items
    def check_item_widgets(self, df):
        if not df.item_spans:
            return
        m = df.masked
        for name, st, po, pc in df.calls.items:
            origin = None
            b = base(name)
            if b in ('IntrinsicHeight', 'IntrinsicWidth'):
                origin = self.item_origin(df, st)
                if origin:
                    self.add(df, 'PERF-003', st, self.ev(df, st, po + 1), note='in %s' % origin)
            elif name in IMAGE_CALLS:
                self.stats['images'] += 1
                origin = self.item_origin(df, st)
                if not origin:
                    continue
                if IMAGE_SIZING.search(m[po:pc]):
                    continue
                if any(base(a[0]) in ('ResizeImage',) or IMAGE_SIZING.search(m[a[2]:a[3]]) and
                       base(a[0]) in ('Image', 'FadeInImage', 'Ink', 'DecoratedBox', 'BoxDecoration')
                       for a in df.calls.ancestors(st)[:3]):
                    continue
                fix = 'memCacheWidth: (width * MediaQuery.devicePixelRatioOf(context)).round()' \
                    if name.startswith('Cached') else \
                    'cacheWidth: (width * MediaQuery.devicePixelRatioOf(context)).round()' \
                    if name.startswith(('Image.', 'FadeInImage')) else \
                    'ResizeImage(%s(...), width: (size * dpr).round())' % name
                self.add(df, 'PERF-004', st, self.ev(df, st, pc + 1), note='in %s; add %s' % (origin, fix))
            elif b in SAVELAYER and name == b:
                origin = self.item_origin(df, st)
                if origin:
                    if b == 'ClipPath' and re.search(r'\bclipBehavior\s*:\s*Clip\s*\.\s*(?:hardEdge|none)\b',
                                                     m[po:pc]):
                        continue
                    self.add(df, 'PERF-006', st, self.ev(df, st, po + 1), severity=SAVELAYER[b],
                             note='%s in %s; %s' % (b, origin,
                                                    'blur once behind the whole list, or use a pre-blurred image'
                                                    if b == 'BackdropFilter' else
                                                    'prefer ClipRRect/borderRadius or a pre-rendered asset'
                                                    if b == 'ClipPath' else
                                                    'apply the gradient once outside the list or bake it into the asset'))

    # -- PERF-005 Opacity animated or per list item
    def check_opacity(self, df):
        m = df.masked
        for name, st, po, pc in df.calls.items:
            if name != 'Opacity':
                continue
            args, _ = arg_map(df, po)
            if 'opacity' not in args:
                continue
            val = m[args['opacity'][0]:args['opacity'][1]].strip()
            literal = numeric_literal(val)
            animated = None
            if not literal:
                for a in df.calls.ancestors(st):
                    if base(a[0]) in ANIM_BUILDERS:
                        animated = 'inside %s' % a[0]
                        break
                if not animated:
                    cls = df.enclosing_class(st)
                    if cls and re.search(r'\bextends\s+AnimatedWidget\b', cls[3]):
                        animated = 'in an AnimatedWidget'
                    elif re.search(r'(?i)(anim|controller|tween|curve)\w*\s*[?!]?\s*\.\s*value\b|'
                                   r'\.evaluate\s*\(|\.transform\s*\(', val):
                        animated = 'driven by `%s`' % ' '.join(val.split())[:40]
            if animated:
                self.add(df, 'PERF-005', st, self.ev(df, st, args['opacity'][1]),
                         note='%s; use FadeTransition(opacity: animation) or AnimatedOpacity' % animated)
                continue
            origin = self.item_origin(df, st)
            if origin and not re.match(r'^\s*(?:const\s+)?(?:0|1|0\.0|1\.0)\s*$', val):
                self.add(df, 'PERF-005', st, self.ev(df, st, args['opacity'][1]),
                         note='per list item (%s); paint with color.withValues(alpha: ...) or the disabled theme'
                              % origin)

    # -- PERF-007 GlobalKey created in build or an itemBuilder
    def check_global_keys(self, df):
        m = df.masked
        for gm in re.finditer(r'(?<![\w$.])(?:const\s+|new\s+)?GlobalKey\s*(?:<[^()]*?>)?\s*\(', m):
            pos = gm.start()
            f = self.in_build(df, pos)
            spans = [(s, e) for s, e, o in df.item_spans if s <= pos < e and m[s:e].lstrip().startswith('(')]
            if not f and not spans:
                continue
            before = m[max(0, pos - 80):pos]
            if re.search(r'\?\?=\s*$|\?\?\s*$', before):
                continue                                # cached: _key ??= GlobalKey()
            heads = [a[0] for a in df.calls.ancestors(pos)]
            enc = m[max(0, pos - 200):pos]
            if re.search(r'\b(?:useMemoized|useState|useRef|useRef<[^>]*>|putIfAbsent|memo\w*)\s*\([^;]*$', enc):
                continue                                # hooks / caches keep one key per element
            where = 'build()' if f else 'an itemBuilder'
            cls = df.enclosing_class(pos)
            if cls and re.search(r'\bextends\s+\w*Hook\w*', cls[3]):
                fix = 'keep one per element with useMemoized(GlobalKey<...>.new)'
            else:
                fix = 'create it once in State (a final field), or use ValueKey(item.id) if you only need identity'
            self.add(df, 'PERF-007', pos, self.ev(df, pos, m.find(')', gm.end()) + 1),
                     note='created in %s; %s' % (where, fix))

    # -- PERF-008 watch a whole object to read one field
    def check_watch_one_field(self, df):
        m, code = df.masked, df.code
        for f in df.builds:
            cls = df.enclosing_class(f[2])
            if not cls or not (class_of_widget(cls[3]) or STATE_HEADER.search(cls[3])):
                continue                                # a Notifier/provider build(): watching whole objects is normal
            body = m[f[2]:f[3]]
            watched = {}
            hits = []
            for wm in re.finditer(r'\bref\s*\.\s*watch\s*\(|\bcontext\s*\.\s*watch\s*<\s*([\w.]+)\s*>\s*\(\s*\)|'
                                  r'\bProvider\s*\.\s*of\s*<\s*([\w.]+)\s*>\s*\(\s*context\s*\)', body):
                po = f[2] + wm.end() - 1
                if wm.group(0).startswith('ref'):
                    pc = df.parens.get(po)
                    if pc is None:
                        continue
                    target = re.sub(r'\s+', '', m[po + 1:pc])
                    if re.search(r'\.\s*(?:select|selectAsync|notifier|future|stream)\b', target):
                        continue
                    kind = 'ref'
                else:
                    pc = po
                    target = wm.group(1) or wm.group(2)
                    kind = 'provider' if wm.group(2) else 'watch'
                watched[target] = watched.get(target, 0) + 1
                tail = m[pc + 1:pc + 80]
                am = re.match(r'\s*(?:\.\s*(state)\s*)?\.\s*([a-z_]\w*)\b(\s*[(<]|\s*\??\.\s*[a-z]\w*\s*[(])?', tail)
                if not am:
                    continue
                field = am.group(2)
                if am.group(3) or field in ASYNC_MEMBERS:
                    continue
                if kind == 'provider' and am.group(1):
                    continue
                hits.append((f[2] + wm.start(), pc + 1 + am.end(), target, kind, bool(am.group(1)), field))
            for s, e, target, kind, via_state, field in hits:
                if watched.get(target, 0) > 1:
                    continue                            # several fields of one object: a select each is optional
                if kind == 'ref':
                    fix = 'ref.watch(%s.select((s) => s.%s))' % (target, field)
                elif via_state:
                    fix = 'context.select((%s b) => b.state.%s)' % (target, field)
                else:
                    fix = 'context.select((%s m) => m.%s)' % (target, field)
                if kind == 'provider':
                    fix += ' (Provider.of listens to the whole object)'
                self.add(df, 'PERF-008', s, ' '.join(code[s:e].split()), note='only `.%s` is read; %s' % (field, fix))

    # -- PERF-009 setState in a scroll / animation listener
    def check_listeners(self, df):
        m = df.masked
        scroll_vars = set(re.findall(r'\b(_?[A-Za-z$][\w$]*)\s*=\s*(?:new\s+)?ScrollController\s*\(', m))
        scroll_vars |= set(re.findall(r'\bScrollController\??\s+(_?[A-Za-z$][\w$]*)\s*[;=]', m))
        anim_vars = set(re.findall(r'\b(_?[A-Za-z$][\w$]*)\s*=\s*(?:new\s+)?AnimationController\s*\(', m))
        anim_vars |= set(re.findall(r'\b(?:AnimationController|Animation\s*<[^>]*>)\??\s+(_?[A-Za-z$][\w$]*)\s*[;=]', m))
        anim_vars |= set(re.findall(r'\b(_?[A-Za-z$][\w$]*)\s*=\s*[^;]*?\.animate\s*\(', m))
        for lm in re.finditer(r'(?<![\w$])((?:widget\s*\.\s*)?_?[A-Za-z$][\w$]*)\s*[?!]?\s*\.\s*addListener\s*\(', m):
            recv = re.sub(r'\s+', '', lm.group(1)).split('.')[-1]
            kind = self._listenable_kind(m, recv, scroll_vars, anim_vars)
            if not kind:
                continue
            po = lm.end() - 1
            args, pc = split_args(df, po)
            if not args:
                continue
            s, e = args[0][1], args[0][2]
            cb = m[s:e].strip()
            body = None
            name = None
            if re.match(r'\(\s*\)\s*(?:\{|=>)', cb):
                body = (s, e)
            elif re.match(r'^_?[A-Za-z$][\w$]*$', cb):
                name = cb
                fn = df.func_named(cb, df.enclosing_class(lm.start())) or df.func_named(cb)
                if fn:
                    body = (fn[2], fn[3])
            if not body:
                continue
            for sm in re.finditer(r'(?<![\w$.])setState\s*\(', m[body[0]:body[1]]):
                spos = body[0] + sm.start()
                if self._guarded(df, body[0], spos):
                    continue
                note = '%s listener on `%s`%s' % (kind, recv, ' (%s)' % name if name else '')
                evidence = self.ev(df, lm.start(), (pc or po) + 2)
                if kind == 'animation':
                    note += '; use AnimatedBuilder(animation: %s, child: ..., builder: ...) or a *Transition widget' \
                            % recv
                    self.add(df, 'PERF-009', lm.start(), evidence, note=note, severity='low', profile_note=False)
                else:
                    self.add(df, 'PERF-009', lm.start(), evidence, note=note)
                break

    @staticmethod
    def _listenable_kind(m, recv, scroll_vars, anim_vars):
        """'scroll', 'animation' or None, from the declared type first and the name second."""
        types = set(re.findall(r'\b([A-Z]\w*)\s*(?:<[^<>;()]*>)?\??\s+%s\s*[;,=)]' % re.escape(recv), m))
        types |= set(re.findall(r'\b%s\s*=\s*(?:new\s+)?([A-Z]\w*)\s*[(.<]' % re.escape(recv), m))
        types.discard('final')
        if types:
            if any(t.endswith('ScrollController') or t in ('PageController', 'ScrollPosition', 'TrackingScrollController')
                   for t in types):
                return 'scroll'
            if any(t in ('AnimationController', 'Animation', 'CurvedAnimation', 'Ticker') for t in types):
                return 'animation'
            return None
        if recv in scroll_vars:
            return 'scroll'
        if recv in anim_vars:
            return 'animation'
        if re.search(r'(?i)scroll', recv):
            return 'scroll'
        if re.search(r'(?i)anim', recv):
            return 'animation'
        return None

    def _guarded(self, df, lo, pos):
        m = df.masked
        stmt = m[lo:pos]
        k = max(stmt.rfind(';'), stmt.rfind('{'), stmt.rfind('}'))
        if re.search(r'\bif\s*\(.*\)\s*$|\belse\s*$|\?\s*$|&&\s*$|=>\s*$', stmt[k + 1:], re.S) and \
                not re.search(r'\(\s*\)\s*=>\s*$', stmt[k + 1:]):
            if re.search(r'\bif\s*\(|\belse\b|\?|&&', stmt[k + 1:]):
                return True
        o = None
        idx = bisect.bisect_left(df.brace_opens, pos) - 1
        if idx >= 0:
            o = df.brace_opens[idx]
            while o is not None and not (o < pos < df.braces.get(o, -1)):
                o = df.parent.get(o)
        while o is not None and o > lo:
            head = m[max(lo, o - 200):o]
            if re.search(r'\b(?:if\s*\([^;{}]*\)|else|case\s[^;{}]*:)\s*$', head, re.S):
                return True
            o = df.parent.get(o)
        return False

    # -- PERF-010 sort inside build
    def check_sort_in_build(self, df):
        m = df.masked
        for f in df.builds:
            cls = df.enclosing_class(f[2])
            if not cls or not (class_of_widget(cls[3]) or STATE_HEADER.search(cls[3])):
                continue
            for sm in re.finditer(r'(?:\.\.|[?!]?\.)\s*sort\s*\(', m[f[2]:f[3]]):
                pos = f[2] + sm.start()
                k = receiver_start(df, pos, f[2])
                recv = ' '.join(df.code[k:pos].split())
                mutates = bool(re.match(r'^(?:widget\s*\.|state\s*\.|_?[a-z]\w*\s*\.\s*(?:state|value)\b)', recv)) \
                    and not re.search(r'\b(?:toList|toIList|List\.of|List\.from|sorted)\b|\[\s*\.\.\.', recv)
                note = 'sorting `%s` on every rebuild%s' % (recv[:50], '; it mutates a list the widget does not own'
                                                                       if mutates else '')
                spc = df.parens.get(f[2] + sm.end() - 1, pos + 6)
                self.add(df, 'PERF-010', pos, self.ev(df, k, spc + 1), note=note)

    # -- PERF-011 jsonDecode of a list payload on the UI isolate (data layer)
    def check_json_decode(self, df):
        if df.layer != 'data' and df.role not in ('source', 'service', 'repository', 'repository-impl'):
            return
        if df.role in ('dto', 'entity', 'state', 'logic', 'view', 'widget'):
            return
        m = df.masked
        isolate_names = set(re.findall(r'\b(?:compute|Isolate\s*\.\s*run|isolate\w*\s*\.\s*\w+)\s*(?:<[^()]*>)?\s*\(\s*'
                                       r'(_?[A-Za-z$][\w$]*)\s*[,)]', m))
        for jm in re.finditer(r'(?<![\w$.])(?:jsonDecode|json\s*\.\s*decode)\s*\(', m):
            po = jm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            after = m[pc + 1:pc + 60]
            before = m[max(0, jm.start() - 80):jm.start()]
            is_list = bool(re.match(r'\s*\)?\s*as\s+List\b', after) or
                           re.search(r'\bList\s*(?:<[^>]*>)?\s+\w+\s*=\s*$', before) or
                           re.search(r'\(\s*$', before) and re.match(r'\s*as\s+List', after))
            if not is_list:
                continue
            f = df.enclosing_func(jm.start())
            if f and f[0] in isolate_names:
                continue
            if any(re.match(r'^(?:compute|Isolate\.run)$', a[0]) for a in df.calls.ancestors(jm.start())) or \
                    re.search(r'\b(?:compute|Isolate\s*\.\s*run)\s*(?:<[^()]*>)?\s*\(\s*\(\s*\)\s*(?:async\s*)?'
                              r'(?:=>|\{)[^;]*$', m[max(0, jm.start() - 200):jm.start()]):
                continue
            if f and re.search(r'\bfactory\b|\bfromJson\b', m[max(0, f[1] - 40):f[1] + 40]):
                continue                                # a model factory: the caller decides the isolate
            self.add(df, 'PERF-011', jm.start(), self.ev(df, jm.start(), pc + 20),
                     note='in %s()' % (f[0] if f else 'a top-level expression'))


# ---------------------------------------------------------------------------------------- classification

def find_arch_check():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.normpath(os.path.join(here, '..', '..', 'flutter-architecture', 'scripts', 'arch_check.py'))
    return p if os.path.isfile(p) else None


def _fps_arch_json(root, profile):
    """Reuse an arch_check --json document that review.sh computed once (FPS_ARCH_JSON, CONTRACTS §19).

    Only used when it describes the same root and, if a profile was forced, the same profile."""
    p = os.environ.get('FPS_ARCH_JSON')
    if not p or not os.path.isfile(p):
        return None
    try:
        with open(p, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or os.path.realpath(str(data.get('root', ''))) != os.path.realpath(root):
        return None
    if profile and profile != 'auto' and (data.get('profile') or {}).get('presentation') != profile:
        return None
    return data


def run_arch_check(root, profile):
    path = find_arch_check()
    if not path:
        return None, 'path-based fallback (flutter-architecture skill not installed: ' \
                     '../flutter-architecture/scripts/arch_check.py missing)'
    cmd = [sys.executable or 'python3', '-I', path, root, '--json']
    if profile != 'auto':
        cmd += ['--profile', profile]
    try:
        data = _fps_arch_json(root, profile)
        if data is None:
            out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
            data = json.loads(out.stdout.decode('utf-8', 'replace'))
    except Exception as exc:  # noqa: BLE001 - any failure means "fall back"
        return None, 'path-based fallback (arch_check.py failed: %s)' % str(exc)[:80]
    if not isinstance(data.get('files'), list):
        return data, 'path-based fallback (arch_check.py has no "files" array; profile taken from it)'
    return data, 'arch_check files[]'


def classify_fallback(rel):
    segs = [s.lower() for s in rel.split('/')]
    base = segs[-1]
    if any(s in ('notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
                 'cubit', 'cubits', 'controller', 'controllers') for s in segs) or \
            re.search(r'_(notifier|view_model|viewmodel|bloc|cubit|controller|store)\.dart$', base):
        return 'presentation', 'logic'
    if any(s in ('view', 'views', 'screens', 'pages', 'ui') for s in segs) or \
            re.search(r'_(screen|page|view)\.dart$', base):
        return 'presentation', 'view'
    if any(s in ('widget', 'widgets', 'presentation', 'forms') for s in segs):
        return 'presentation', 'widget'
    if 'domain' in segs:
        return 'domain', 'other'
    if 'data' in segs:
        return 'data', 'other'
    return 'other', 'other'


def detect_profile_fallback(pubspec, rels):
    deps = set(re.findall(r'^\s{2}(\w+)\s*:', pubspec, re.M))
    if deps & {'flutter_riverpod', 'hooks_riverpod', 'riverpod'}:
        if any('/notifier' in r for r in rels) and not any('view_model' in r or 'viewmodel' in r for r in rels):
            return 'mvn'
    if 'get' in deps:
        return 'getx'
    if any('view_model' in r or 'viewmodel' in r for r in rels):
        return 'mvvm'
    if deps & {'bloc', 'flutter_bloc'} or any(r.endswith(('_bloc.dart', '_cubit.dart')) for r in rels):
        return 'bloc'
    if 'provider' in deps:
        return 'provider'
    if deps & {'flutter_riverpod', 'hooks_riverpod', 'riverpod'}:
        return 'riverpod'
    return 'setstate' if 'flutter' in deps else 'unknown'


def read_files_arg(root, arg):
    if os.path.isfile(arg):
        with open(arg, encoding='utf-8', errors='replace') as fh:
            items = [l.strip() for l in fh if l.strip()]
    else:
        items = [x.strip() for x in arg.split(',') if x.strip()]
    out = set()
    for it in items:
        p = it
        if os.path.isabs(p):
            p = os.path.relpath(p, root)
        p = os.path.normpath(p).replace(os.sep, '/')
        if p.startswith('./'):
            p = p[2:]
        out.add(p)
    return out


def usage(msg):
    sys.stderr.write('check_performance.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_performance.py <project-root> [--json] [--files <list>] '
                     '[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]\n')
    sys.exit(2)


def parse_args(argv):
    opts = {'json': False, 'files': None, 'profile': 'auto', 'max': 5, 'root': None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--json':
            opts['json'] = True
        elif a in ('--files', '--profile', '--max'):
            if i + 1 >= len(argv):
                usage('%s needs a value' % a)
            v = argv[i + 1]
            i += 1
            if a == '--files':
                opts['files'] = v
            elif a == '--profile':
                if v not in PROFILES:
                    usage('unknown profile %r' % v)
                opts['profile'] = v
            else:
                try:
                    opts['max'] = max(0, int(v))
                except ValueError:
                    usage('--max needs an integer')
        elif a in ('-h', '--help'):
            sys.stdout.write(__doc__)
            sys.exit(0)
        elif a.startswith('-'):
            usage('unknown option %s' % a)
        elif opts['root'] is None:
            opts['root'] = a
        else:
            usage('unexpected argument %s' % a)
        i += 1
    if not opts['root']:
        usage('missing <project-root>')
    return opts



def main(argv):
    opts = parse_args(argv)
    root = os.path.abspath(opts['root'])
    pub = os.path.join(root, 'pubspec.yaml')
    if not os.path.isfile(pub):
        usage('no pubspec.yaml in %s' % root)
    with open(pub, encoding='utf-8', errors='replace') as fh:
        pubspec = fh.read()
    pm = re.search(r'^name\s*:\s*([\w]+)', pubspec, re.M)
    package = pm.group(1) if pm else ''
    only = read_files_arg(root, opts['files']) if opts['files'] else None

    rels = []
    lib = os.path.join(root, 'lib')
    if os.path.isdir(lib):
        for dp, dns, fns in os.walk(lib):
            dns[:] = sorted(d for d in dns if not d.startswith('.') and d != 'generated')
            for fn in sorted(fns):
                if fn.endswith('.dart'):
                    rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/')
                    if not GENERATED_RE.search(rel):
                        rels.append(rel)

    arch, classification = (None, 'no lib/ directory') if not rels else run_arch_check(root, opts['profile'])
    arch_files = {}
    if arch and isinstance(arch.get('files'), list):
        for f in arch['files']:
            if isinstance(f, dict) and f.get('file'):
                arch_files[f['file']] = f

    files = []
    skipped = 0
    for rel in rels:
        a = arch_files.get(rel)
        if arch_files and a is None:
            skipped += 1                            # arch_check left it out: generated or out of scope
            continue
        if a and (a.get('role') in SKIP_ROLES):
            skipped += 1
            continue
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if re.search(r'GENERATED CODE - DO NOT MODIFY', df.raw[:400]):
            skipped += 1
            continue
        if a:
            df.layer, df.role = a.get('layer') or 'other', a.get('role') or 'other'
        else:
            df.layer, df.role = classify_fallback(rel)
        files.append(df)

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(pubspec, rels), 'fallback detection from pubspec and folders'

    ck = Checker(files, profile)
    if files:
        ck.run()
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))

    stats = dict(ck.stats)
    stats['files'] = len(files)
    stats['skipped'] = skipped
    stats['reported_scope'] = 'files list (%d)' % len(only) if only is not None else 'all'
    report = {
        'schema': SCHEMA, 'root': root, 'package': package,
        'profile': {'presentation': profile, 'source': psource},
        'classification': classification,
        'stats': stats,
        'findings': findings,
        'suppressed': suppressed,
    }
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2) + '\n')
        return 0
    out = ['== PERFORMANCE',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  scanned: %d files, %d build methods, %d lazy item builders (+%d item widgets one hop), '
           '%d eager-capable scrollables, %d network/file images' %
           (len(files), stats['build_methods'], stats['item_builders'], stats['item_widgets'],
            stats['scrollables'], stats['images'])]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no performance findings')
    for (rid, sev), items in groups:
        out.append('  [%s] %s (%s) x%d — %s' % (rid, RULES[rid][0], sev, len(items), RULES[rid][2]))
        for it in items[:opts['max']]:
            line = '      %s:%d  %s' % (it['file'], it['line'], it['evidence'])
            if it['note']:
                line += '   [%s]' % it['note']
            out.append(line)
        if len(items) > opts['max']:
            out.append('      ... %d more' % (len(items) - opts['max']))
    if suppressed:
        out.append('  suppressed: %d (see --json)' % len(suppressed))
    sys.stdout.write('\n'.join(out) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
