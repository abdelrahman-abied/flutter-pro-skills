#!/usr/bin/env python3
"""check_adaptive.py: find layout and platform code that breaks on other screens, inputs or platforms (read-only).

Usage:
  python3 -I check_adaptive.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (breakpoint tokens, web guards and the
             platforms the app targets are project-wide facts); only findings in the
             listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  ADAPT-001 io-platform-on-web            ADAPT-006 orientation-decides-layout
  ADAPT-002 platform-check-in-widget      ADAPT-007 screen-size-in-logic
  ADAPT-003 app-wide-orientation-lock     ADAPT-008 hover-only-action
  ADAPT-004 magic-breakpoint              ADAPT-009 desktop-window-unbounded
  ADAPT-005 device-identity-layout        ADAPT-010 test-view-size-not-reset

The checker reads Dart under lib/ (and test/ and integration_test/ for ADAPT-010),
pubspec.yaml, and which of web/, macos/, windows/, linux/, android/ and ios/ exist, to
know the platforms the app targets. For ADAPT-009 it also reads the desktop runner
sources (macos/Runner/*.swift and *.xib, windows/runner/*.cpp, linux/**/*.cc) for a
minimum window size.

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so. Generated files are skipped.

Suppression (in the analysed code):
  // adapt-ignore: ADAPT-004 <reason>        on the reported line or the line above
  // adapt-ignore-file: ADAPT-004 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import glob
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/adaptive-layout@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
TOOL = 'check_adaptive.py'

RULES = {
    'ADAPT-001': ('io-platform-on-web', 'high',
                  'dart:io Platform (Platform.isAndroid, Platform.operatingSystem, ...) is read in a widget, view, '
                  'logic class or the app root of an app that also builds for the web, and nothing guards it with '
                  'kIsWeb. On the web every Platform getter throws UnsupportedError, so the screen (or the app) '
                  'fails there. Use defaultTargetPlatform or Theme.of(context).platform for idioms, and put real '
                  'capability checks in a source behind kIsWeb.'),
    'ADAPT-002': ('platform-check-in-widget', 'low',
                  'A widget branches on dart:io Platform.isX. Platform reports the real host, so tests, '
                  'debugDefaultTargetPlatformOverride and ThemeData.platform cannot change it, and the widget '
                  'cannot be previewed as another platform. Use Theme.of(context).platform or '
                  'defaultTargetPlatform for look and feel, and ask a source whether a native feature exists.'),
    'ADAPT-003': ('app-wide-orientation-lock', 'medium',
                  'The app locks every screen to portrait (or landscape) at start-up, with no size or platform '
                  'condition. Android 16 ignores orientation locks on screens 600 dp and wider for apps that target '
                  'API 36 (tablets, foldables, desktop windows), iPad multitasking and Android multi-window resize the app anyway, so layouts that were '
                  'never built for the other shape break there. Lay out by the available size instead; lock only a '
                  'screen that needs it, or only on small phones.'),
    'ADAPT-004': ('magic-breakpoint', 'low',
                  'A layout decision compares a width with a literal breakpoint (constraints.maxWidth > 600, '
                  'MediaQuery.sizeOf(context).width >= 840). Literal breakpoints drift apart across screens, so '
                  'one screen switches to two panes at 600 and the next at 700. Define the window size classes '
                  'once (Material 3: compact < 600, medium < 840, expanded < 1200, large < 1600, extra-large) and '
                  'compare against those tokens.'),
    'ADAPT-005': ('device-identity-layout', 'medium',
                  'The layout is chosen from what the device is (isTablet from the platform, the device model or a '
                  'device-type package) instead of the space the app has. A tablet in split screen, a foldable, a '
                  'phone in landscape and a desktop window all get the wrong layout. Choose the layout from the '
                  'window width (a size class) or LayoutBuilder constraints.'),
    'ADAPT-006': ('orientation-decides-layout', 'low',
                  'The layout is chosen from the orientation (OrientationBuilder, MediaQuery.orientationOf). '
                  'Orientation says nothing about the space: a tablet in portrait is wider than a phone in '
                  'landscape, and a split-screen window can be "portrait" on a wide display. Choose by width (a '
                  'size class) or LayoutBuilder constraints.'),
    'ADAPT-007': ('screen-size-in-logic', 'medium',
                  'A logic class (notifier, view model, bloc, cubit, controller) reads or stores the screen size or '
                  'a breakpoint. Logic then changes when the window resizes, cannot be tested without a view, and '
                  'mixes layout with state. Expose data only; the view reads LayoutBuilder or MediaQuery.sizeOf and '
                  'picks the layout.'),
    'ADAPT-008': ('hover-only-action', 'medium',
                  'An action (a button, a tap target) appears only while the mouse hovers (MouseRegion onEnter/onExit '
                  'toggles it) and nothing else shows it: no tap, long press or focus path. Touch and keyboard users '
                  'can never reach it. Keep the action visible on touch, or also show it on focus and long press.'),
    'ADAPT-009': ('desktop-window-unbounded', 'low',
                  'The app targets desktop but never sets a minimum window size (window_manager, desktop_window, '
                  'window_size or the native runner). Users can shrink the window below the smallest layout you '
                  'built, and the UI overflows. Set a minimum size at start-up, at least the compact width your '
                  'layouts support.'),
    'ADAPT-010': ('test-view-size-not-reset', 'low',
                  'A widget test changes the test view size or pixel ratio (tester.view.physicalSize, '
                  'devicePixelRatio, binding.setSurfaceSize) without resetting it. The size can leak into later '
                  'tests in the file, which then pass or fail by test order. Reset it with '
                  'addTearDown(tester.view.reset) (or setSurfaceSize(null)).'),
}

TOKEN_HOME = {
    'mvn': 'MVN: define the size classes once, in lib/core/presentation/layout/ (or the design-system package), '
           'and read them in views; notifiers and use cases never see them.',
    'mvvm': 'MVVM: define the size classes once, in lib/ui/core/ next to the shared theme and widgets; views pick '
            'the layout and view models stay size-agnostic.',
    'bloc': 'Bloc: define the size classes once, in the design-system package (app_ui) or lib/app/view/; blocs '
            'never see them.',
    'riverpod': 'Riverpod: define the size classes once, in lib/core/ (or the design system), as plain constants '
                'or an enum, not as a provider that logic reads.',
    'provider': 'Provider: define the size classes once, in lib/core/ or the theme folder; ChangeNotifiers never '
                'see them.',
    'getx': 'GetX: define the size classes once, in lib/app/core/values/ (or the theme); controllers never read '
            'Get.width for layout.',
    'mvc': 'MVC: define the size classes once, next to the shared views or theme; controllers never see them.',
    'setstate': 'Define the size classes once (lib/core/layout/breakpoints.dart, an enum WindowSizeClass with a '
                'fromWidth constructor) and use them in every screen.',
    'unknown': 'Define the size classes once (an enum WindowSizeClass with a fromWidth constructor) in the shared UI '
               'folder or design system.',
}

LOGIC_NOTE = {
    'mvn': 'MVN: the notifier exposes the data (items, selected id); the view reads LayoutBuilder or '
           'MediaQuery.sizeOf and picks one or two panes. Keep a selection that must survive a resize in the '
           'view\'s State (or in the notifier as data, never as a layout flag).',
    'mvvm': 'MVVM: the view model exposes data and commands; the view decides single pane or list-detail from '
            'its constraints.',
    'bloc': 'Bloc: states carry data, not layout; the view (BlocBuilder) picks the layout from its constraints. '
            'A selection that survives a resize can be data in the state (selectedId).',
    'riverpod': 'Riverpod: providers expose data; widgets read MediaQuery.sizeOf or LayoutBuilder and choose the '
                'layout.',
    'provider': 'Provider: the ChangeNotifier exposes data; the widget chooses the layout from its constraints.',
    'getx': 'GetX: the controller exposes Rx data; the view (GetView/Obx) reads its constraints and chooses the '
            'layout. Avoid Get.width in controllers.',
    'mvc': 'MVC: the controller exposes data; the view chooses the layout.',
    'setstate': 'Keep layout decisions in the widget; state classes hold data only.',
    'unknown': 'Keep layout decisions in the view; logic exposes data only.',
}

PLATFORM_NOTE = {
    'mvn': 'MVN: a native capability check belongs in a data source (kIsWeb first, then defaultTargetPlatform), '
           'surfaced through the repository and use case as a typed "unsupported" result.',
    'mvvm': 'MVVM: a native capability check belongs in a service under data/services, which the repository '
            'turns into a Result the view model exposes.',
    'bloc': 'Bloc: a native capability check belongs in the data provider or repository; the bloc emits it as '
            'state.',
    'riverpod': 'Riverpod: a native capability check belongs in a source provider (kIsWeb first); widgets read the '
                'result.',
    'provider': 'Provider: a native capability check belongs in a service built at the root.',
    'getx': 'GetX: a native capability check belongs in a GetxService; GetPlatform is web-safe but cannot be '
            'overridden in tests either.',
    'mvc': 'MVC: a native capability check belongs in the model or a service.',
    'setstate': 'A native capability check belongs in a small wrapper class, guarded with kIsWeb first.',
    'unknown': 'A native capability check belongs in a data source, guarded with kIsWeb first.',
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.gen|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|'
                              r'AUTO[- ]?GENERATED FILE|Autogenerated from Pigeon|Autogenerated by jnigen|'
                              r'Generated by `?package:ffigen|Generated by: OpenAPI Generator', re.I)
SUPPRESS_RE = re.compile(r'adapt-ignore(-file)?\s*:\s*((?:ADAPT-\d{3})(?:\s*,\s*ADAPT-\d{3})*)\s*(.*)')

KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'on', 'return', 'assert', 'super', 'this', 'new', 'await',
            'throw', 'when', 'with', 'yield', 'const', 'else', 'do', 'try', 'in', 'is', 'as', 'case', 'late',
            'final', 'var', 'true', 'false', 'null', 'async', 'sync', 'get', 'set', 'required', 'static', 'void',
            'dynamic', 'default', 'break', 'continue', 'external', 'factory', 'operator', 'covariant', 'show',
            'hide', 'import', 'export', 'part', 'of', 'library', 'typedef', 'extends', 'implements', 'enum',
            'class', 'mixin', 'abstract', 'sealed', 'base', 'interface'}

# ---------------------------------------------------------------------------------------- lexing


def _ident(text, i):
    return i >= 0 and (text[i].isalnum() or text[i] in '_$')


_MAIN_TOK = re.compile(r"//|/\*|['\"]")
_EXPR_TOK = re.compile(r"//|/\*|['\"{}]")
_STR_TOK = {}


def _str_tok(delim, raw):
    key = (delim, raw)
    if key not in _STR_TOK:
        alts = [re.escape(delim)]
        if len(delim) == 1:
            alts.append(r'\n')
        if not raw:
            alts += [r'\\', r'\$']
        _STR_TOK[key] = re.compile('|'.join(alts))
    return _STR_TOK[key]


def lex(text):
    """Return (code, masked, iview, comments, strings).

    code:     comments blanked (newlines kept), strings intact.
    masked:   comments and string contents blanked (quotes kept); safe for bracket matching.
    iview:    like masked, but interpolated expressions inside strings are kept (for identifier scans).
    strings:  list of dicts {s, e, cs, ce, interps: [(s, e, braced)]} sorted by start.
    """
    n = len(text)
    code = list(text)
    masked = list(text)
    comments = []
    strings = []

    def blank(buf, s, e):
        for k in range(s, e):
            if buf[k] != '\n':
                buf[k] = ' '

    def skip_block(i):
        depth, i = 1, i + 2
        while i < n and depth:
            a, b = text.find('/*', i), text.find('*/', i)
            if b < 0:
                return n
            if 0 <= a < b:
                depth += 1
                i = a + 2
            else:
                depth -= 1
                i = b + 2
        return i

    def string_start(t):
        """Index where the literal starting with the quote at t begins (a raw prefix r/R counts)."""
        if t > 0 and text[t - 1] in 'rR' and not _ident(text, t - 2):
            return t - 1
        return t

    def skip_expr(i):
        depth = 1
        while i < n:
            mm = _EXPR_TOK.search(text, i)
            if not mm:
                return n
            t, tok = mm.start(), mm.group(0)
            if tok == '//':
                j = text.find('\n', t)
                i = n if j < 0 else j
            elif tok == '/*':
                i = skip_block(t)
            elif tok in '\'"':
                i = skip_string(string_start(t))
            elif tok == '{':
                depth += 1
                i = t + 1
            else:
                depth -= 1
                i = t + 1
                if depth == 0:
                    return i
        return n

    def skip_string(i):
        s0 = i
        raw = text[i] in 'rR'
        if raw:
            i += 1
        q = text[i]
        delim = q * 3 if text.startswith(q * 3, i) else q
        i += len(delim)
        rec = {'s': s0, 'e': n, 'cs': i, 'ce': n, 'interps': []}
        strings.append(rec)
        rx = _str_tok(delim, raw)
        while i < n:
            mm = rx.search(text, i)
            if not mm:
                break
            t, tok = mm.start(), mm.group(0)
            if tok == '\\':
                i = t + 2
            elif tok == '\n':
                rec['ce'], rec['e'] = t, t
                return t
            elif tok == '$':
                if t + 1 < n and text[t + 1] == '{':
                    j = skip_expr(t + 2)
                    rec['interps'].append((t + 2, j - 1, True))
                    i = j
                elif t + 1 < n and (text[t + 1].isalpha() or text[t + 1] == '_'):
                    j = t + 1
                    while j < n and (text[j].isalnum() or text[j] == '_'):
                        j += 1
                    rec['interps'].append((t + 1, j, False))
                    i = j
                else:
                    i = t + 1
            else:
                rec['ce'], rec['e'] = t, t + len(delim)
                return t + len(delim)
        rec['ce'] = n
        return n

    i = 0
    while i < n:
        mm = _MAIN_TOK.search(text, i)
        if not mm:
            break
        t, tok = mm.start(), mm.group(0)
        if tok == '//':
            j = text.find('\n', t)
            j = n if j < 0 else j
            blank(code, t, j)
            blank(masked, t, j)
            comments.append((t, j))
            i = j
        elif tok == '/*':
            j = skip_block(t)
            blank(code, t, j)
            blank(masked, t, j)
            comments.append((t, j))
            i = j
        else:
            idx = len(strings)
            j = skip_string(string_start(t))
            rec = strings[idx]
            blank(masked, rec['cs'], rec['ce'])
            i = j
    iview = list(masked)
    # restore interpolated expressions, then blank the contents of strings nested inside them again
    strings.sort(key=lambda r: r['s'])
    starts = [r['s'] for r in strings]
    nested = []
    for rec in strings:
        for s, e, _ in rec['interps']:
            iview[s:e] = code[s:e]
            lo, hi = bisect.bisect_left(starts, s), bisect.bisect_left(starts, e)
            nested.extend(strings[lo:hi])
    for rec in nested:
        k = rec['cs']
        for s, e, _ in rec['interps'] + [(rec['ce'], rec['ce'], False)]:
            blank(iview, k, s)
            k = e
    return ''.join(code), ''.join(masked), ''.join(iview), comments, strings


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


def split_top(m, s, e, seps=','):
    """Split m[s:e] at depth-0 separators; return [(start, end)] ranges (stripped of nothing)."""
    out, depth, start = [], 0, s
    i = s
    while i < e:
        c = m[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c in seps and depth == 0:
            out.append((start, i))
            start = i + 1
        i += 1
    out.append((start, e))
    return [(a, b) for a, b in out if m[a:b].strip()]


def strip_range(t, s, e):
    while s < e and t[s].isspace():
        s += 1
    while e > s and t[e - 1].isspace():
        e -= 1
    return s, e


class Callable(object):
    __slots__ = ('name', 'ps', 'pe', 'bo', 'bc', 'params', 'start', 'expr_body')

    def __init__(self, name, ps, pe, bo, bc, params, start, expr_body):
        self.name, self.ps, self.pe, self.bo, self.bc = name, ps, pe, bo, bc
        self.params, self.start, self.expr_body = params, start, expr_body


def parse_params(m, s, e):
    """[(name, type, named)] from the parameter list m[s:e] (without the outer parentheses)."""
    out = []
    named = False
    txt = m[s:e]
    depth, start, parts = 0, 0, []
    for i, c in enumerate(txt):
        if c in '(<[{':
            if c in '[{' and depth == 0:
                named = named or c == '{'
                parts.append((txt[start:i], False))
                start = i + 1
                continue
            depth += 1
        elif c in ')>]}':
            if c in ']}' and depth == 0:
                parts.append((txt[start:i], c == '}'))
                start = i + 1
                continue
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append((txt[start:i], named))
            start = i + 1
    parts.append((txt[start:], named))
    for p, is_named in parts:
        p = re.sub(r'@\w+(?:\s*\([^()]*\))?', ' ', p)
        p = re.split(r'\s*=(?!=)|\s*:(?!:)', p)[0]
        p = re.sub(r'\b(required|covariant|final|const|var|late)\b', ' ', p).strip()
        p = re.sub(r'\b(this|super)\s*\.\s*', '', p)
        if not p:
            continue
        mm = re.search(r'([A-Za-z_$][\w$]*)\s*$', p)
        if not mm:
            continue
        out.append((mm.group(1), p[:mm.start()].strip(), is_named))
    return out


CLASS_RE = re.compile(r'\b(?:(?:abstract|sealed|final|base|interface|mixin)\s+)*(class|mixin|extension)\s+'
                      r'(?:const\s+|type\s+)?([A-Za-z_]\w*)?[^{;]*?\{')
NAME_BEFORE = re.compile(r'([A-Za-z_$][\w$]*)\s*(?:<[^<>(){};]*(?:<[^<>(){};]*>[^<>(){};]*)*>)?\s*$')


class DartFile(object):
    def __init__(self, root, rel):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.masked, self.iview, self.comments, self.strings = lex(self.raw)
        self.string_starts = [r['s'] for r in self.strings]
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.braces = match_pairs(self.masked, '{', '}')
        self.parens = match_pairs(self.masked, '(', ')')
        self.brackets = None
        self.role, self.layer = 'other', 'other'
        self.classes = []          # (name, open, close, header, header_start)
        self.callables = []        # Callable
        self.suppress_line = {}
        self.suppress_file = {}
        self.imports = set(re.findall(r'''^\s*(?:import|export)\s+['"]package:(\w+)/''', self.code, re.M))
        self._parse()

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def line_text(self, pos):
        ln = self.line_of(pos)
        s = self.line_starts[ln - 1]
        e = self.raw.find('\n', s)
        return ' '.join(self.raw[s:e if e >= 0 else len(self.raw)].split())

    def snippet(self, s, e, limit=120):
        t = ' '.join(self.raw[s:e].split())
        return t if len(t) <= limit else t[:limit - 3] + '...'

    def _parse(self):
        m = self.masked
        for mm in CLASS_RE.finditer(m):
            o = mm.end() - 1
            c = self.braces.get(o)
            if c is not None:
                self.classes.append((mm.group(2) or '', o, c, mm.group(0), mm.start()))
        for po in sorted(k for k, v in self.parens.items() if m[k] == '('):
            pc = self.parens[po]
            tail = re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>)', m[pc + 1:pc + 40])
            if not tail:
                continue
            nb = NAME_BEFORE.search(m[max(0, po - 120):po])
            name = None
            start = po
            if nb:
                name = nb.group(1)
                start = po - (len(m[max(0, po - 120):po]) - nb.start(1))
                if name in KEYWORDS:
                    if name in ('if', 'for', 'while', 'switch', 'catch', 'on', 'when', 'return', 'await', 'yield',
                                'throw', 'else', 'in', 'is', 'as', 'case', 'assert', 'super', 'this', 'new'):
                        if name in ('return', 'await', 'yield', 'throw', 'else', 'in', 'case'):
                            name = None          # closure after a keyword: return (x) => ...
                        else:
                            continue
                    else:
                        name = None
                elif po - 1 >= 0 and re.search(r'\.\s*$', m[max(0, start - 3):start]):
                    continue                     # x.method() { ... } is not valid Dart; method call
                elif re.search(r'\b(?:class|mixin|enum)\s+(?:const\s+)?$', m[max(0, start - 20):start]):
                    continue                     # primary constructor header: class Foo(final int x) {
            bo = pc + 1 + tail.start(2)
            if tail.group(2) == '{':
                bc = self.braces.get(bo)
                if bc is None:
                    continue
                expr_body = False
            else:
                bc = expr_end(m, bo + 2)
                expr_body = True
            self.callables.append(Callable(name, po, pc, bo, bc, parse_params(m, po + 1, pc), start, expr_body))
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

    def enclosing_callables(self, pos):
        """Callables whose body contains pos, innermost first."""
        fs = [f for f in self.callables if f.bo <= pos < f.bc + (1 if not f.expr_body else 0)]
        fs.sort(key=lambda f: -f.bo)
        return fs

    def enclosing_class(self, pos):
        best = None
        for c in self.classes:
            if c[1] < pos < c[2] and (best is None or c[1] > best[1]):
                best = c
        return best

    def enclosing_calls(self, pos):
        """Names of the calls whose argument list contains pos, innermost first: [(name, open_paren)]."""
        out = []
        m = self.masked
        for po, pc in self.parens.items():
            if m[po] == '(' and po < pos < pc:
                nb = NAME_BEFORE.search(m[max(0, po - 120):po])
                out.append((nb.group(1) if nb else '', po))
        out.sort(key=lambda t: -t[1])
        return out

    def string_at(self, pos):
        i = bisect.bisect_right(self.string_starts, pos) - 1
        while i >= 0:
            r = self.strings[i]
            if r['s'] <= pos < r['e']:
                return r
            i -= 1
        return None

    def top_strings(self, s, e):
        """String literals fully inside [s, e) that are not nested in another literal of that range."""
        out = []
        for r in self.strings:
            if r['s'] >= s and r['e'] <= e:
                if out and out[-1]['s'] <= r['s'] < out[-1]['e']:
                    continue
                out.append(r)
        return out


# ---------------------------------------------------------------------------------------- vocab

UI_ROLES = {'view', 'widget'}
WIDGET_CLASS = re.compile(r'\bextends\s+(?:State|ConsumerState|HookState)\s*<|'
                          r'\bextends\s+(?:\w+\s*\.\s*)?(?:StatelessWidget|StatefulWidget|ConsumerWidget|'
                          r'ConsumerStatefulWidget|HookWidget|HookConsumerWidget|StatefulHookWidget|'
                          r'StatefulHookConsumerWidget|StatelessHookWidget|GetView|GetWidget|GetResponsiveView)\b')
LOGIC_CLASS = re.compile(r'\b(?:extends|with)\s+(?:Cubit|Bloc|ChangeNotifier|Notifier|AsyncNotifier|StreamNotifier|'
                         r'StateNotifier|GetxController|FullLifeCycleController|FamilyNotifier|'
                         r'FamilyAsyncNotifier|AutoDisposeNotifier|AutoDisposeAsyncNotifier)\b|'
                         r'\bextends\s+_\$\w+|\bclass\s+\w*ViewModel\b')
LOGIC_NAME = re.compile(r'(Notifier|Bloc|Cubit|ViewModel|Controller|Store)$')
LAYOUT_CLASS_NAME = re.compile(r'(?i)(breakpoint|layout|window|screen|size|responsive|adaptive|formfactor|display)')

PLATFORM_GETTERS = (r'is(?:Android|IOS|MacOS|Windows|Linux|Fuchsia)|operatingSystem(?:Version)?|localeName|'
                    r'numberOfProcessors|pathSeparator|environment|executable|resolvedExecutable|script|'
                    r'localHostname|version|lineTerminator|executableArguments|packageConfig')
IO_IMPORT_RE = re.compile(r'''^\s*import\s+['"]dart:io['"]\s*(?:as\s+(\w+))?\s*((?:show|hide)\s+[^;]*)?;''', re.M)
COND_IMPORT_RE = re.compile(r'''\bif\s*\(\s*dart\s*\.\s*library\s*\.\s*(?:io|ffi)\s*\)\s*['"]([^'"]+)['"]''')
PLATFORM_PATH_TOKENS = {'android', 'ios', 'macos', 'windows', 'linux', 'desktop', 'mobile', 'native', 'io',
                        'tray', 'system_tray', 'fuchsia', 'ffi'}
PLATFORM_PATH_DIRS = PLATFORM_PATH_TOKENS | {'window', 'platform_specific'}

ORIENT_LOCK_RE = re.compile(r'(?<![\w$.])SystemChrome\s*\.\s*setPreferredOrientations\s*\(')
STARTUP_FN_RE = re.compile(r'(?i)^(main\w*|_?bootstrap\w*|_?run\w*|_?init\w*|\w*initiali[sz]\w*|_?setup\w*|'
                           r'_?configure\w*|_?startup\w*|_?start)$')
SIZE_WORDS_RE = re.compile(r'(?i)(size|width|height|shortestside|longestside|tablet|phone|handset|formfactor|'
                           r'platform|kisweb|ismobile|isdesktop|screen|display|device|breakpoint|orientation)')

WIDTH_NAME_RE = re.compile(r'^_?(?:screen|window|device|viewport|available|layout|app|view|max|content|total|'
                           r'parent)?(?:Width|width|Size\.width|size\.width)$')
WIDTH_SOURCE_RE = re.compile(r'MediaQuery|\bconstraints\b|\.maxWidth\b|\bView\s*\.\s*of\b|physicalSize|'
                             r'\bGet\s*\.\s*(?:width|size)\b|\bcontext\s*\.\s*(?:width|screenWidth|mediaQuerySize)\b|'
                             r'\bbiggest\b')
CMP_NUM = r'(\d{3,4}(?:\.\d+)?)'
CMP_RE = re.compile(r'(<=|>=|<|>)\s*' + CMP_NUM + r'(?![\w.]|\s*[*/+-])')
CMP_REV_RE = re.compile(r'(?<![\w.$])' + CMP_NUM + r'\s*(<=|>=|<|>)(?!=)')
CASE_RE = re.compile(r'(?:\bcase\s*|(?<=[,{])\s*)(<=|>=|<|>)\s*' + CMP_NUM + r'(?![\w.])')
BP_MIN, BP_MAX = 300, 2000

TOKEN_CLASS_RE = re.compile(r'^(?:\w*Breakpoints?|\w*SizeClass(?:es)?|WindowSize\w*|ScreenSizes?|ScreenType|'
                            r'FormFactors?|LayoutSizes?|DeviceSizes?|WindowClass\w*|ScreenBreakpoints?|'
                            r'LayoutBreakpoints?|WidthClass\w*)$')
TOKEN_CONST_RE = re.compile(r'(?:^|[;{}\s])(?:static\s+)?(?:const|final)\s+(?:double\s+|int\s+|num\s+)?'
                            r'([A-Za-z_]\w*)\s*=\s*' + CMP_NUM + r'\s*;')
TOKEN_CONST_NAME_RE = re.compile(r'(?i)(breakpoint|threshold|(compact|medium|expanded|tablet|desktop|phone|mobile|'
                                 r'handset|narrow|wide|large|small)\w*width|^k?(tablet|desktop|phone|mobile|'
                                 r'handset|compact|medium|expanded)$)')
TOKEN_DEPS = {'flutter_adaptive_scaffold', 'responsive_framework', 'responsive_builder', 'adaptive_breakpoints',
              'breakpoint', 'layout', 'flutter_breakpoints', 'adaptive_layout', 'responsive_sizer'}

DEVICE_ID_RE = re.compile(r'(?<![\w$.])(?:Device\s*\.\s*get\s*\(\s*\)\s*\.\s*(?:isTablet|isPhone|isIphoneX)|'
                          r'Device\s*\.\s*(?:screenType|deviceType)\b)|'
                          r'\.\s*(?:model|localizedModel|machine|name)\b[^;\n]{0,50}?(?:[\'"]\s*ipad|tablet[\'"])',
                          re.I)
DEVICE_VAR_RE = re.compile(r'(?<![\w$.])(?:get\s+|(?:final|var|late|bool|static|const)\s+(?:bool\s+)?)?'
                           r'(_?is(?:Tablet|Phone|Handset|IPad|Ipad|Foldable)|_?deviceType|_?formFactor)\s*(=>|=(?!=))')
DEVICE_SRC_RE = re.compile(r'\bPlatform\s*\.|\bdefaultTargetPlatform\b|\bTargetPlatform\s*\.|\.\s*platform\b|'
                           r'\bDeviceInfoPlugin\b|\.\s*(?:model|localizedModel|utsname|machine)\b|\bGetPlatform\b|'
                           r'\bkIsWeb\b|\bUniversalPlatform\b|\bDevice\s*\.')
SPACE_SRC_RE = re.compile(r'(?i)size|width|height|shortestside|constraints|mediaquery|breakpoint|formfactor|'
                          r'sizeclass|biggest|extent')

ORIENT_READ_RE = re.compile(r'(?<![\w$.])OrientationBuilder\s*\(|MediaQuery\s*\.\s*(?:maybeO|o)rientationOf\s*\(|'
                            r'MediaQuery\s*\.\s*(?:of|maybeOf)\s*\([^()]*\)\s*[?!]?\s*\.\s*orientation\b|'
                            r'(?<![\w$.])context\s*\.\s*(?:orientation|isLandscape|isPortrait)\b')

SIZE_READ_RE = re.compile(r'MediaQuery\s*\.\s*(?:maybe)?(?:[sS]izeOf|[wW]idthOf|[hH]eightOf|[oO]rientationOf|'
                          r'[dD]isplayFeaturesOf)\s*\(|'
                          r'MediaQuery\s*\.\s*(?:of|maybeOf)\s*\([^()]*\)\s*[?!]?\s*\.\s*(?:size|orientation|'
                          r'displayFeatures)\b|(?<![\w$.])View\s*\.\s*(?:of|maybeOf)\s*\(|\.\s*physicalSize\b|'
                          r'\bplatformDispatcher\s*\.\s*(?:views|implicitView)\b|'
                          r'(?<![\w$.])Get\s*\.\s*(?:width|height|size)\b')
SIZE_FIELD_RE = re.compile(r'\b(?:double|Size|bool|int|num)\??\s+(_?(?:screenWidth|screenHeight|screenSize|'
                           r'deviceWidth|deviceHeight|isTablet|isPhone|isWideScreen|isLargeScreen|isSmallScreen|'
                           r'isDesktopLayout|isMobileLayout|isTwoPane|useNavRail|showNavigationRail|viewportWidth))\b')

INTERACTIVE_RE = re.compile(r'\bon(?:Pressed|Tap|LongPress|Changed|Selected|DoubleTap)\s*:|'
                            r'(?<![\w$.])(?:IconButton|TextButton|ElevatedButton|FilledButton|OutlinedButton|InkWell|'
                            r'GestureDetector|PopupMenuButton|MenuAnchor|Checkbox|Switch|FloatingActionButton|'
                            r'CupertinoButton)\b')

DESKTOP_MIN_DART_RE = re.compile(r'\bsetMinimumSize\s*\(|\bminimumSize\s*:|\bsetMinWindowSize\s*\(|'
                                 r'\bsetWindowMinSize\s*\(|\bminSize\s*=|\bsetMinSize\s*\(|\bminWindowSize\b')
DESKTOP_MIN_NATIVE_RE = re.compile(r'\bminSize\b|contentMinSize|ptMinTrackSize|WM_GETMINMAXINFO|'
                                   r'gtk_widget_set_size_request|gtk_window_set_geometry_hints|GDK_HINT_MIN_SIZE')
DESKTOP_DART_RE = re.compile(r'\bTargetPlatform\s*\.\s*(?:macOS|windows|linux)\b|'
                             r'\bPlatform\s*\.\s*is(?:MacOS|Windows|Linux)\b|\bisDesktop\b|\bGetPlatform\s*\.\s*'
                             r'isDesktop\b|\bUniversalPlatform\s*\.\s*is(?:MacOS|Windows|Linux)\b')
DESKTOP_DEPS = {'window_manager', 'desktop_window', 'window_size', 'bitsdojo_window', 'macos_window_utils',
                'flutter_acrylic', 'tray_manager', 'system_tray', 'desktop_multi_window', 'menubar',
                'macos_ui', 'fluent_ui', 'yaru'}

VIEW_SET_RE = re.compile(r'(?:\.\s*view|\bview)\s*\.\s*(physicalSize|devicePixelRatio)\s*=(?!=)|'
                         r'\.\s*(physicalSizeTestValue|devicePixelRatioTestValue)\s*=(?!=)|'
                         r'\bsetSurfaceSize\s*\(\s*(?!null\s*\))')
VIEW_RESET_RE = re.compile(r'\.\s*(?:reset|resetPhysicalSize|resetDevicePixelRatio|clearPhysicalSizeTestValue|'
                           r'clearDevicePixelRatioTestValue|clearAllTestValues|resetTestValues)\b|'
                           r'\bsetSurfaceSize\s*\(\s*null\s*\)')


def path_tokens(rel):
    segs = rel.split('/')
    dirs = set(s.lower() for s in segs[:-1])
    base = segs[-1].lower()
    if base.endswith('.dart'):
        base = base[:-5]
    toks = set(re.split(r'[_.]', base))
    return dirs, toks


def platform_specific_path(rel):
    dirs, toks = path_tokens(rel)
    return bool(dirs & PLATFORM_PATH_DIRS) or bool(toks & PLATFORM_PATH_TOKENS)


def num(s):
    try:
        return float(s)
    except ValueError:
        return None


def fmt_num(v):
    return ('%d' % v) if v == int(v) else ('%g' % v)


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, root, files, tests, profile, clean, platforms, deps, only):
        self.root = root
        self.files = files
        self.tests = tests
        self.profile = profile
        self.clean = clean
        self.platforms = platforms
        self.deps = deps
        self.only = only
        self.findings = []
        self.suppressed = []
        self.web = 'web' in platforms
        self.desktop = sorted(p for p in ('macos', 'windows', 'linux') if p in platforms)
        self.touch = bool({'android', 'ios', 'web'} & set(platforms))
        self.stats = {'platform_checks': 0, 'width_comparisons': 0, 'layout_builders': 0, 'size_reads': 0,
                      'orientation_locks': 0, 'mouse_regions': 0, 'test_files': len(tests),
                      'test_view_changes': 0}
        self.guard_names = set()
        self.space_names = set()
        self.cond_io = set()
        self.token_names = []      # (name, rel)
        self.token_files = set()
        self.token_types = set()

    # -- reporting
    def add(self, df, rid, pos, evidence, note='', severity=None, line=None):
        ln = line or df.line_of(pos)
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
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    def token_home(self):
        return TOKEN_HOME.get(self.profile, TOKEN_HOME['unknown'])

    def logic_note(self):
        return LOGIC_NOTE.get(self.profile, LOGIC_NOTE['unknown'])

    def platform_note(self):
        p = PLATFORM_NOTE.get(self.profile, PLATFORM_NOTE['unknown'])
        if self.clean and self.profile != 'mvn':
            p += ' Clean: the source sits in data/datasources and the domain sees only the repository contract.'
        return p

    # -- structure helpers
    @staticmethod
    def class_kind(df, pos):
        cls = df.enclosing_class(pos)
        if cls is None:
            return None, None
        hdr = cls[3]
        if WIDGET_CLASS.search(hdr):
            return 'ui', cls
        if LOGIC_CLASS.search(hdr):
            return 'logic', cls
        if df.role == 'logic' and LOGIC_NAME.search(cls[0]):
            return 'logic', cls
        return 'plain', cls

    @staticmethod
    def openers(df, pos):
        """Enclosing (, [, { positions of pos, innermost first."""
        if df.brackets is None:
            df.brackets = match_pairs(df.masked, '[', ']')
        m = df.masked
        out = []
        for pairs in (df.parens, df.braces, df.brackets):
            for o, c in pairs.items():
                if o < pos < c and m[o] in '([{':
                    out.append(o)
        out.sort(reverse=True)
        return out

    @staticmethod
    def element_start(df, o, child):
        """Start of the element (argument, list item, statement) of opener o that contains child."""
        m = df.masked
        depth = 0
        i = child - 1
        while i > o:
            c = m[i]
            if c in ')]}':
                if c == '}' and depth == 0 and m[o] == '{':
                    return i + 1
                depth += 1
            elif c in '([{':
                depth -= 1
            elif depth == 0 and c in ',;':
                return i + 1
            i -= 1
        return o + 1

    def if_condition_before(self, df, o):
        """The condition text of an `if (...)` (or `if (...) ... else`) right before opener o, or None."""
        m = df.masked
        j = o - 1
        while j >= 0 and m[j] in ' \t\n':
            j -= 1
        if m[max(0, j - 2):j + 1] == '...':
            j -= 3
            while j >= 0 and m[j] in ' \t\n':
                j -= 1
        if j >= 3 and m[j - 3:j + 1] == 'else' and not _ident(m, j - 4):
            k = j - 4
            while k >= 0 and m[k] in ' \t\n':
                k -= 1
            if k >= 0 and m[k] in '})]':
                po = df.braces.get(k) if m[k] == '}' else (df.parens.get(k) if m[k] == ')' else None)
                if po is not None:
                    return self.if_condition_before(df, po) or ''
            return ''
        if j >= 0 and m[j] == ')':
            po = df.parens.get(j)
            if po is not None and re.search(r'\bif\s*$', m[max(0, po - 10):po]):
                return df.iview[po + 1:j]
        return None

    def guarded(self, df, pos, rx):
        """True when a condition matching rx guards pos: same expression, an enclosing if, or an early return."""
        m = df.iview
        ops = self.openers(df, pos)
        child = pos
        for o in ops:
            seg = m[self.element_start(df, o, child):child]
            if rx.search(seg):
                return True
            cond = self.if_condition_before(df, o)
            if cond and rx.search(cond):
                return True
            child = o
        fs = df.enclosing_callables(pos)
        for f in fs:
            body = m[f.bo:pos]
            for mm in re.finditer(r'\bif\s*\(([^;{}]*?)\)\s*\{?\s*(?:return|throw)\b', body):
                if rx.search(mm.group(1)):
                    return True
        return False

    def callers_guarded(self, df, pos):
        """The innermost named function around pos is only called from guarded places in this file."""
        fs = [f for f in df.enclosing_callables(pos) if f.name and f.name not in ('build', 'initState', 'main')]
        if not fs:
            return False
        f = fs[0]
        calls = [c.start() for c in re.finditer(r'(?<![\w$])%s\s*\(' % re.escape(f.name), df.masked)
                 if not (f.start <= c.start() <= f.bc)]
        return bool(calls) and all(self.guarded(df, c, self.guard_rx) for c in calls)

    # -- project facts
    def collect(self):
        for df in self.files:
            m = df.masked
            for mm in re.finditer(r'\bget\s+(\w+)\s*(=>|\{)', m):
                o = mm.end() - 1
                if mm.group(2) == '{':
                    c = df.braces.get(o)
                    body = m[o:c] if c else ''
                else:
                    body = m[o:expr_end(m, o + 1)]
                if 'kIsWeb' in body:
                    self.guard_names.add(mm.group(1))
                if SPACE_SRC_RE.search(body):
                    self.space_names.add(mm.group(1))
            for mm in re.finditer(r'(?:final|const|bool)\s+(\w+)\s*=([^;]*);', m):
                if 'kIsWeb' in mm.group(2):
                    self.guard_names.add(mm.group(1))
            # breakpoint tokens
            found = False
            for c in df.classes:
                if c[0] and TOKEN_CLASS_RE.match(c[0].lstrip('_')):
                    self.token_names.append((c[0], df.rel))
                    self.token_types.add(c[0])
                    found = True
            for mm in re.finditer(r'\benum\s+([A-Za-z_]\w*)', m):
                if TOKEN_CLASS_RE.match(mm.group(1).lstrip('_')):
                    self.token_names.append((mm.group(1), df.rel))
                    self.token_types.add(mm.group(1))
                    found = True
            for mm in TOKEN_CONST_RE.finditer(m):
                v = num(mm.group(2))
                if v is not None and BP_MIN <= v <= BP_MAX and TOKEN_CONST_NAME_RE.search(mm.group(1)):
                    self.token_names.append((mm.group(1), df.rel))
                    found = True
            if found:
                self.token_files.add(df.rel)
        self.token_deps = sorted(self.deps & TOKEN_DEPS)
        self.guard_rx = re.compile(r'\b(?:kIsWeb|kIsWasm%s)\b' % ''.join(
            '|' + re.escape(n) for n in sorted(self.guard_names)))

    def collect_conditional(self, rels):
        """Files picked by `if (dart.library.io)` conditional imports/exports (also from barrels)."""
        for rel in rels:
            try:
                with open(os.path.join(self.root, rel), encoding='utf-8', errors='replace') as fh:
                    text = fh.read()
            except OSError:
                continue
            if 'dart.library' not in text:
                continue
            for mm in COND_IMPORT_RE.finditer(text):
                t = mm.group(1)
                if t.startswith('package:'):
                    parts = t[len('package:'):].split('/', 1)
                    if len(parts) == 2:
                        self.cond_io.add('lib/' + parts[1])
                else:
                    self.cond_io.add(os.path.normpath(os.path.join(os.path.dirname(rel), t)).replace(os.sep, '/'))

    def run(self, rels=()):
        self.collect_conditional(rels)
        self.collect()
        for df in self.files:
            self.check_platform(df)
            self.check_orientation_lock(df)
            self.check_device_identity(df)
            self.check_orientation_layout(df)
            self.check_logic_size(df)
            self.check_hover(df)
            self.stats['layout_builders'] += len(re.findall(r'(?<![\w$.])LayoutBuilder\s*\(', df.masked))
            self.stats['size_reads'] += len(SIZE_READ_RE.findall(df.masked))
        self.check_breakpoints()
        self.check_desktop_window()
        for df in self.tests:
            self.check_test_view(df)

    # ADAPT-001 / ADAPT-002
    def check_platform(self, df):
        prefixes = None
        for mm in IO_IMPORT_RE.finditer(df.code):
            combin = mm.group(2) or ''
            if combin.startswith('show') and not re.search(r'\bPlatform\b', combin):
                continue
            if combin.startswith('hide') and re.search(r'\bPlatform\b', combin):
                continue
            prefixes = prefixes or set()
            prefixes.add(mm.group(1) or '')
        if not prefixes:
            return
        if df.rel in self.cond_io:
            return
        alts = []
        for p in prefixes:
            alts.append(r'(?<![\w$.])' + (re.escape(p) + r'\s*\.\s*' if p else '') + r'Platform\s*\.\s*(?:' +
                        PLATFORM_GETTERS + r')\b')
        rx = re.compile('|'.join(alts))
        m = df.masked
        seen = {}
        root_file = df.layer == 'app' or bool(re.search(r'(^|/)lib/(main[^/]*|bootstrap|app)\.dart$', df.rel))
        plat_path = platform_specific_path(df.rel)
        for mm in rx.finditer(m):
            pos = mm.start()
            self.stats['platform_checks'] += 1
            kind, cls = self.class_kind(df, pos)
            in_ui = kind == 'ui' or (kind is None and df.role in UI_ROLES and df.layer != 'app')
            in_logic = kind == 'logic'
            in_root = kind is None and root_file
            key = (cls[0] if cls else None, kind)
            if self.web and (in_ui or in_logic or in_root) and not plat_path and \
                    not self.guarded(df, pos, self.guard_rx) and not self.callers_guarded(df, pos):
                k = ('001',) + key
                if k in seen:
                    seen[k][1] += 1
                    continue
                where = ('%s (%s)' % (cls[0], 'widget' if in_ui else 'logic class')) if cls else \
                    ('the app root' if in_root else 'top-level UI code')
                note = ('%s reads %s, which throws UnsupportedError on the web, and no kIsWeb check guards it. '
                        'For look and feel use Theme.of(context).platform or defaultTargetPlatform (web-safe); '
                        'guard capability checks with kIsWeb first (kIsWeb || !Platform.isX is safe, the reverse '
                        'is not). %s' % (where, mm.group(0).replace(' ', ''), self.platform_note()))
                seen[k] = [len(self.findings), 1]
                self.add(df, 'ADAPT-001', pos, df.line_text(pos)[:120], note)
                continue
            if in_ui:
                k = ('002',) + key
                if k in seen:
                    seen[k][1] += 1
                    continue
                note = ('%s branches on %s. Use Theme.of(context).platform (follows ThemeData.platform and '
                        'debugDefaultTargetPlatformOverride, so tests and previews can switch it) or '
                        'defaultTargetPlatform; where the branch decides whether a native feature works, ask a '
                        'source instead. %s' % (cls[0] if cls else 'this widget code', mm.group(0).replace(' ', ''),
                                                self.platform_note()))
                seen[k] = [len(self.findings), 1]
                self.add(df, 'ADAPT-002', pos, df.line_text(pos)[:120], note)
        for k, (idx, n) in seen.items():
            if n > 1 and idx < len(self.findings) and self.findings[idx]['file'] == df.rel:
                self.findings[idx]['note'] = '%d uses in this %s; the first is shown. ' % (
                    n, 'class' if k[1] else 'file') + self.findings[idx]['note']

    # ADAPT-003
    def check_orientation_lock(self, df):
        m = df.masked
        for mm in ORIENT_LOCK_RE.finditer(m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            self.stats['orientation_locks'] += 1
            arg = df.code[po + 1:pc]
            lm = re.match(r'\s*(?:const\s+)?(?:<\s*DeviceOrientation\s*>\s*)?\[([^\]]*)\]\s*,?\s*$', arg)
            if not lm:
                continue
            vals = re.findall(r'DeviceOrientation\s*\.\s*(\w+)', lm.group(1))
            if not vals:
                continue
            kinds = set('portrait' if v.startswith('portrait') else 'landscape' for v in vals)
            if len(kinds) != 1:
                continue
            fs = [f for f in df.enclosing_callables(mm.start()) if f.name]
            fn = fs[-1].name if fs else None
            kind, cls = self.class_kind(df, mm.start())
            app_class = cls is not None and re.search(r'(?<![\w$.])(?:MaterialApp|CupertinoApp|WidgetsApp|'
                                                      r'GetMaterialApp)(?:\s*\.\s*router)?\s*\(', m[cls[1]:cls[2]])
            root_file = df.layer == 'app' or bool(re.search(r'(^|/)lib/(main[^/]*|bootstrap|app|init\w*)\.dart$',
                                                            df.rel))
            startup = (fn is not None and STARTUP_FN_RE.match(fn) and cls is None) or \
                (root_file and cls is None) or (app_class and fn in ('build', 'initState', None))
            if not startup:
                continue
            if self.guarded(df, mm.start(), SIZE_WORDS_RE):
                continue
            sev = 'medium' if {'android', 'ios'} & set(self.platforms) else 'info'
            self.add(df, 'ADAPT-003', mm.start(), df.line_text(mm.start())[:120],
                     'every screen is locked to %s in %s. Remove the app-wide lock and build layouts from the '
                     'available width; if one screen truly needs a fixed orientation (a camera, a game board), lock '
                     'it in that screen and restore DeviceOrientation.values on dispose, or lock only when the '
                     'shortest side is under 600 dp.%s' % (
                         kinds.pop(), ('%s()' % fn) if fn else 'the app root',
                         '' if sev == 'medium' else ' Graded info: the app has no android/ or ios/ folder.'),
                     severity=sev)

    # ADAPT-004
    def width_operand(self, df, pos, left):
        """Is the operand ending (left=True) or starting at pos a window/constraint width?"""
        m = df.iview
        if left:
            seg = m[max(0, pos - 160):pos]
            em = re.search(r'([A-Za-z_$][\w$]*(?:\s*\([^()]*(?:\([^()]*\))?[^()]*\))?(?:\s*[?!]?\s*\.\s*[A-Za-z_$][\w$]*'
                           r'(?:\s*\([^()]*(?:\([^()]*\))?[^()]*\))?)*)\s*$', seg)
        else:
            seg = m[pos:pos + 160]
            em = re.match(r'\s*([A-Za-z_$][\w$]*(?:\s*\([^()]*(?:\([^()]*\))?[^()]*\))?(?:\s*[?!]?\s*\.\s*[A-Za-z_$][\w$]*'
                          r'(?:\s*\([^()]*(?:\([^()]*\))?[^()]*\))?)*)', seg)
        if not em:
            return None
        expr = re.sub(r'\s+', '', em.group(1))
        if re.search(r'height|Height|\.dy$|\.y$', expr.split('.')[-1]):
            return None
        last = expr.split('.')[-1]
        if 'MediaQuery' in expr and re.search(r'(?i)width|size|shortestSide|longestSide', expr) and \
                not re.search(r'(?i)height', expr):
            return expr
        if re.search(r'\.(?:maxWidth|minWidth|crossAxisExtent)$', expr):
            return expr
        if re.search(r'\.(?:shortestSide|longestSide)$', expr):
            return expr if re.search(r'(?i)size|mediaquery|screen|window|view|display', expr) else None
        if re.search(r'^Get\.width$|^context\.(?:width|screenWidth)$', expr):
            return expr
        name = expr[:-len('.width')] if expr.endswith('.width') else expr
        if '.' in name or '(' in name:
            return None
        if expr.endswith('.width'):
            if not re.search(r'(?i)^_?(?:screen|window|device|viewport|app|view|available|layout|media|query)?size$',
                             name):
                return None
        elif not re.search(r'(?i)^_?(?:screen|window|device|viewport|available|layout|app|view|max|content|'
                           r'parent)?width$', name):
            return None
        if re.search(r'(?i)^_?(?:screen|window|device|viewport)', name):
            return expr
        for f in df.enclosing_callables(pos):
            body = m[f.bo:f.bc]
            am = re.search(r'(?<![\w$.])' + re.escape(name) + r'\s*=(?!=)\s*([^;]*)', body)
            if am and WIDTH_SOURCE_RE.search(am.group(1)):
                return expr
            for p in f.params:
                if p[0] == name and re.search(r'BoxConstraints|Size', p[1] or ''):
                    return expr
        return None

    def check_breakpoints(self):
        hits = []
        for df in self.files:
            if df.rel in self.token_files:
                continue
            m = df.iview
            for mm in CMP_RE.finditer(m):
                v = num(mm.group(2))
                if v is None or not (BP_MIN <= v <= BP_MAX):
                    continue
                if m[mm.start() - 1:mm.start()] in '<>=':
                    continue
                expr = self.width_operand(df, mm.start(), True)
                if expr:
                    hits.append((df, mm.start(), v, expr))
            for mm in CMP_REV_RE.finditer(m):
                v = num(mm.group(1))
                if v is None or not (BP_MIN <= v <= BP_MAX):
                    continue
                expr = self.width_operand(df, mm.end(), False)
                if expr:
                    hits.append((df, mm.start(), v, expr))
            for mm in CASE_RE.finditer(m):
                v = num(mm.group(2))
                if v is None or not (BP_MIN <= v <= BP_MAX):
                    continue
                ops = [o for o in self.openers(df, mm.start()) if m[o] == '{']
                if not ops:
                    continue
                o = ops[0]
                j = o - 1
                while j >= 0 and m[j] in ' \t\n':
                    j -= 1
                if j < 0 or m[j] != ')':
                    continue
                po = df.parens.get(j)
                if po is None or not re.search(r'\bswitch\s*$', m[max(0, po - 10):po]):
                    continue
                expr = self.width_operand(df, j, True)
                if expr:
                    hits.append((df, mm.start(), v, expr))
        self.stats['width_comparisons'] = len(hits)
        if not hits:
            return
        files = set(h[0].rel for h in hits)
        values = set(h[2] for h in hits)
        tokens = self.token_names
        if not tokens and not self.token_deps and len(files) < 2 and len(values) < 2:
            return
        seen = set()
        for df, pos, v, expr in hits:
            ln = df.line_of(pos)
            if (df.rel, ln) in seen:
                continue
            seen.add((df.rel, ln))
            if tokens:
                names = ', '.join(sorted(set('%s (%s)' % (n, r) for n, r in tokens[:3])))
                note = ('the project already defines breakpoint tokens: %s; compare against them instead of %s. ' %
                        (names, fmt_num(v)))
            elif self.token_deps:
                note = ('the project depends on %s; use its breakpoints instead of %s. ' %
                        (', '.join(self.token_deps), fmt_num(v)))
            else:
                note = ('%d width comparisons with %d different literal breakpoints (%s) in %d files and no shared '
                        'size classes. ' % (len(hits), len(values), ', '.join(fmt_num(x) for x in sorted(values)),
                                            len(files)))
            note += '%s Use LayoutBuilder constraints for the space a widget gets, MediaQuery.sizeOf(context) for ' \
                    'the window.' % self.token_home()
            self.add(df, 'ADAPT-004', pos, df.line_text(pos)[:120], note)

    # ADAPT-005
    def check_device_identity(self, df):
        m = df.code
        done = set()
        for mm in DEVICE_VAR_RE.finditer(m):
            o = mm.end()
            rhs = m[o:expr_end(m, o)]
            if not DEVICE_SRC_RE.search(rhs) or SPACE_SRC_RE.search(rhs):
                continue
            if any(re.search(r'\b%s\b' % re.escape(n), rhs) for n in self.space_names) or \
                    re.search(r'(?<![\w$.(])context\s*\.\s*(?!mounted\b)\w+', rhs):
                continue        # combined with a project getter that measures the space (context.isMobile)
            ln = df.line_of(mm.start())
            done.add(ln)
            self.add(df, 'ADAPT-005', mm.start(), df.line_text(mm.start())[:120],
                     '%s is derived from the platform or device model (%s), not from the available space. Replace '
                     'it with a size class from the window width (MediaQuery.sizeOf(context).width) or with '
                     'LayoutBuilder constraints; keep platform checks for idioms only. %s' % (
                         mm.group(1), ' '.join(rhs.split())[:60], self.token_home()))
        for mm in DEVICE_ID_RE.finditer(m):
            ln = df.line_of(mm.start())
            if ln in done:
                continue
            done.add(ln)
            self.add(df, 'ADAPT-005', mm.start(), df.line_text(mm.start())[:120],
                     'the device type or model (%s) decides the layout. Use the window size class instead; an iPad '
                     'in Split View or Slide Over is phone-sized. %s' % (' '.join(mm.group(0).split())[:60],
                                                                         self.token_home()))

    # ADAPT-006
    def check_orientation_layout(self, df):
        m = df.masked
        reported = set()
        for mm in ORIENT_READ_RE.finditer(m):
            pos = mm.start()
            kind, cls = self.class_kind(df, pos)
            if kind != 'ui' and not (kind is None and df.role in UI_ROLES):
                continue
            tok = mm.group(0)
            if 'OrientationBuilder' not in tok:
                # the read must decide something: a comparison, a switch or a ternary on it
                tail = m[mm.end():mm.end() + 120]
                head = m[max(0, pos - 160):pos]
                stmt_ok = re.match(r'\s*(?:==|!=)\s*Orientation\s*\.', tail) or \
                    re.search(r'Orientation\s*\.\s*\w+\s*(?:==|!=)\s*$', head) or \
                    re.match(r'\s*\?', tail) or re.search(r'\bswitch\s*\(\s*$', head)
                if not stmt_ok:
                    am = re.search(r'(?:final|var|Orientation|bool)\s+(\w+)\s*=\s*$', head)
                    if am:
                        rest = m[mm.end():(cls[2] if cls else len(m))]
                        stmt_ok = re.search(r'\b%s\s*(?:==|!=|\?)' % re.escape(am.group(1)), rest) or \
                            re.search(r'\bif\s*\(\s*!?\s*%s\b' % re.escape(am.group(1)), rest)
                if not stmt_ok:
                    continue
            key = (cls[0] if cls else None)
            if key in reported:
                continue
            reported.add(key)
            self.add(df, 'ADAPT-006', pos, df.line_text(pos)[:120],
                     '%s picks its layout from %s. Choose by width instead: LayoutBuilder (constraints.maxWidth) '
                     'for this widget\'s space, or a size class from MediaQuery.sizeOf(context).width for the '
                     'window. Orientation stays fine for things that really follow the device rotation (a camera '
                     'preview). %s' % (cls[0] if cls else 'this widget', ' '.join(tok.split()).rstrip('('),
                                       self.token_home()))

    # ADAPT-007
    def check_logic_size(self, df):
        m = df.masked
        for c in df.classes:
            name = c[0]
            if not name:
                continue
            kind, _ = self.class_kind(df, c[1] + 1)
            if kind != 'logic' or LAYOUT_CLASS_NAME.search(name):
                continue
            body = m[c[1]:c[2]]
            ev = SIZE_READ_RE.search(body) or SIZE_FIELD_RE.search(body)
            if not ev and self.token_types:
                ev = re.search(r'\b(?:%s)\??\s+_?\w+\s*[;=,)]' % '|'.join(re.escape(t) for t in
                                                                         sorted(self.token_types)), body)
            if not ev:
                continue
            pos = c[1] + ev.start()
            self.add(df, 'ADAPT-007', pos, df.line_text(pos)[:120],
                     '%s holds layout knowledge (%s). %s' % (name, ' '.join(ev.group(0).split())[:50],
                                                             self.logic_note()))

    # ADAPT-008
    def check_hover(self, df):
        m = df.masked
        for mm in re.finditer(r'(?<![\w$.])MouseRegion\s*\(', m):
            self.stats['mouse_regions'] += 1
            if not self.touch and self.platforms:
                continue
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            kind, cls = self.class_kind(df, mm.start())
            if cls is None:
                continue
            args = m[po:pc]
            names = None
            for ev in ('onEnter', 'onExit', 'onHover'):
                am = re.search(r'\b%s\s*:' % ev, args)
                if not am:
                    continue
                e = expr_end(args, am.end())
                found = set(re.findall(r'(?<![\w$.])(?:this\s*\.\s*)?(_?\w+)\s*=(?!=)\s*(?:true|false|!)', args[am.end():e]))
                names = found if names is None else names | found
            if not names:
                continue
            body = m[cls[1]:cls[2]]
            for var in sorted(names):
                outside = False
                for am in re.finditer(r'(?<![\w$.])(?:this\s*\.\s*)?%s\s*=(?!=)' % re.escape(var), body):
                    p = cls[1] + am.start()
                    if not (po < p < pc):
                        # an assignment outside the MouseRegion (a field initialiser does not count)
                        pre = body[max(0, am.start() - 30):am.start()]
                        if re.search(r'\bbool\s*\??\s*$|\b(?:var|late|final)\s+$', pre):
                            continue
                        outside = True
                        break
                if outside:
                    continue
                gate = None
                for gm in re.finditer(r'\bif\s*\(\s*(?:widget\s*\.\s*\w+\s*&&\s*)?%s\s*(?:&&[^)]*)?\)' % re.escape(var),
                                      body):
                    s = cls[1] + gm.end()
                    e = expr_end(m, s)
                    if INTERACTIVE_RE.search(m[s:e]):
                        gate = cls[1] + gm.start()
                        break
                if gate is None:
                    for gm in re.finditer(r'(?<![\w$.!])%s\s*\?' % re.escape(var), body):
                        s = cls[1] + gm.end()
                        e = expr_end(m, s)
                        branch = m[s:e]
                        if INTERACTIVE_RE.search(branch.split(':')[0] if ':' in branch else branch) and \
                                re.search(r':\s*(?:null|const\s+SizedBox(?:\.shrink)?\s*\(\s*\)|SizedBox\s*'
                                          r'(?:\.shrink)?\s*\(\s*\)|Container\s*\(\s*\))', branch):
                            gate = cls[1] + gm.start()
                            break
                if gate is None:
                    gm = re.search(r'\bvisible\s*:\s*%s\b' % re.escape(var), body)
                    if gm:
                        s = cls[1] + gm.start()
                        ops = [o for o in self.openers(df, s) if m[o] == '(']
                        if ops:
                            e = df.parens.get(ops[0]) or s
                            if INTERACTIVE_RE.search(m[ops[0]:e]):
                                gate = s
                if gate is None:
                    continue
                self.add(df, 'ADAPT-008', gate, df.line_text(gate)[:120],
                         '%s shows an action only while %s is true, and only MouseRegion sets it. Keep the action '
                         'visible on touch platforms (switch on Theme.of(context).platform or the input), or also '
                         'set %s from a FocusableActionDetector/onFocusChange and a long press, so keyboard and '
                         'touch users can reach it.' % (cls[0], var, var))
                break

    # ADAPT-009
    def check_desktop_window(self):
        if not self.desktop:
            return
        intent = bool(self.deps & DESKTOP_DEPS) or \
            any(DESKTOP_DART_RE.search(df.masked) for df in self.files)
        if not intent:
            return
        if any(DESKTOP_MIN_DART_RE.search(df.masked) for df in self.files):
            return
        native = []
        for pat in ('macos/Runner/*.swift', 'macos/Runner/Base.lproj/*.xib', 'windows/runner/*.cpp',
                    'windows/runner/*.h', 'linux/*.cc', 'linux/runner/*.cc'):
            native.extend(glob.glob(os.path.join(self.root, pat)))
        for p in native:
            try:
                with open(p, encoding='utf-8', errors='replace') as fh:
                    if DESKTOP_MIN_NATIVE_RE.search(fh.read()):
                        return
            except OSError:
                continue
        target = None
        for df in self.files:
            if re.search(r'(^|/)lib/main\.dart$', df.rel):
                target = df
                break
        if target is None:
            for df in self.files:
                if re.search(r'(^|/)lib/main[^/]*\.dart$', df.rel) or df.layer == 'app':
                    target = df
                    break
        if target is None:
            return
        rm = re.search(r'(?<![\w$.])runApp\s*\(', target.masked)
        pos = rm.start() if rm else 0
        self.add(target, 'ADAPT-009', pos, target.line_text(pos)[:120],
                 'the app builds for %s and no minimum window size is set in Dart or in the runner. With '
                 'window_manager: await windowManager.ensureInitialized(); await windowManager.setMinimumSize('
                 'const Size(360, 480)); (desktop_window: DesktopWindow.setMinWindowSize). Pick the smallest size '
                 'your compact layout handles.' % ', '.join(self.desktop))

    # ADAPT-010
    def check_test_view(self, df):
        m = df.masked
        file_reset = False
        for tm in re.finditer(r'(?<![\w$.])(?:tearDown|tearDownAll)\s*\(', m):
            pc = df.parens.get(tm.end() - 1)
            if pc and VIEW_RESET_RE.search(m[tm.end():pc]):
                file_reset = True
        done = set()
        for mm in VIEW_SET_RE.finditer(m):
            pos = mm.start()
            self.stats['test_view_changes'] += 1
            if file_reset:
                continue
            fs = df.enclosing_callables(pos)
            if any(VIEW_RESET_RE.search(m[f.bo:f.bc]) for f in fs):
                continue
            outer = fs[-1] if fs else None
            if outer is not None and outer.name and outer.name not in ('main', 'testWidgets'):
                # a helper: the callers may reset after calling it
                callers = [c for c in re.finditer(r'(?<![\w$.])%s\s*\(' % re.escape(outer.name), m)
                           if not (outer.ps <= c.start() <= outer.bc)]
                if any(any(VIEW_RESET_RE.search(m[g.bo:g.bc]) for g in df.enclosing_callables(c.start()))
                       for c in callers):
                    continue
            key = outer.bo if outer else -1
            if key in done:
                continue
            done.add(key)
            what = mm.group(1) or mm.group(2) or 'setSurfaceSize'
            dep = ' window.%s is deprecated; set tester.view.%s instead.' % (
                what, 'physicalSize' if what.startswith('physical') else 'devicePixelRatio') \
                if mm.group(2) else ''
            fix = 'addTearDown(() => tester.binding.setSurfaceSize(null));' if what == 'setSurfaceSize' else \
                'addTearDown(tester.view.reset);'
            self.add(df, 'ADAPT-010', pos, df.line_text(pos)[:120],
                     'this test changes %s and never resets it. Add %s right after the change.%s Run the layout '
                     'tests once per size class (for example 390x844, 800x1280 and 1440x900 logical pixels).' % (
                         what, fix, dep))

def find_arch_check():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.normpath(os.path.join(here, '..', '..', 'flutter-architecture', 'scripts', 'arch_check.py'))
    return p if os.path.isfile(p) else None


def _fps_arch_json(root, profile):
    """Reuse an arch_check --json document that review.sh computed once (FPS_ARCH_JSON, CONTRACTS §20).

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
    if re.search(r'(^|/)lib/main[^/]*\.dart$', rel) or any(s in ('di', 'injection') for s in segs):
        return 'app', 'other'
    if any(s in ('notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
                 'cubit', 'cubits', 'controller', 'controllers') for s in segs) or \
            re.search(r'_(notifier|view_model|viewmodel|bloc|cubit|controller|store)\.dart$', base):
        return 'presentation', 'logic'
    if any(s in ('view', 'views', 'screens', 'pages', 'ui') for s in segs) or \
            re.search(r'_(screen|page|view)\.dart$', base):
        return 'presentation', 'view'
    if any(s in ('widget', 'widgets', 'presentation') for s in segs):
        return 'presentation', 'widget'
    if 'domain' in segs:
        return 'domain', 'other'
    if any(s in ('sources', 'datasources', 'data_sources', 'local', 'remote', 'api') for s in segs) or \
            re.search(r'_(source|api|client)\.dart$', base):
        return 'data', 'source'
    if 'repositories' in segs or base.endswith('_repository_impl.dart') or base.endswith('_repository.dart'):
        return 'data', 'repository-impl'
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
    sys.stderr.write('check_adaptive.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_adaptive.py <project-root> [--json] [--files <list>] '
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


def pubspec_deps(pubspec):
    deps = set()
    section = None
    for line in pubspec.split('\n'):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if re.match(r'^\S', line):
            section = line.split(':')[0].strip()
            continue
        mm = re.match(r'^  ([A-Za-z_]\w*)\s*:', line)
        if mm and section in ('dependencies', 'dev_dependencies', 'dependency_overrides'):
            deps.add(mm.group(1))
    return deps





def walk_dart(root, top, test_only=False):
    out = []
    base = os.path.join(root, top)
    if not os.path.isdir(base):
        return out
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if not d.startswith('.') and d not in ('generated', 'build'))
        for fn in sorted(fns):
            if fn.endswith('.dart') and (not test_only or fn.endswith('_test.dart')):
                out.append(os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/'))
    return out


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
    deps = pubspec_deps(pubspec)
    only = read_files_arg(root, opts['files']) if opts['files'] else None
    platforms = [p for p in ('android', 'ios', 'web', 'macos', 'windows', 'linux')
                 if os.path.isdir(os.path.join(root, p))]

    rels = walk_dart(root, 'lib')
    skipped = {'generated': 0, 'barrel': 0}
    kept = []
    for rel in rels:
        if GENERATED_RE.search(rel):
            skipped['generated'] += 1
        else:
            kept.append(rel)
    rels = kept

    arch, classification = (None, 'no lib/ directory') if not rels else run_arch_check(root, opts['profile'])
    arch_files = {}
    if arch and isinstance(arch.get('files'), list):
        for f in arch['files']:
            if isinstance(f, dict) and f.get('file'):
                arch_files[f['file']] = f
    use_arch = bool(arch_files)

    files = []
    for rel in rels:
        if use_arch and rel not in arch_files:
            skipped['generated'] += 1      # arch_check decides what is generated (CONTRACTS §18)
            continue
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if GENERATED_HEADER.search(df.raw[:800]):
            skipped['generated'] += 1
            continue
        a = arch_files.get(rel)
        if a:
            df.layer, df.role = a.get('layer') or 'other', a.get('role') or 'other'
        else:
            df.layer, df.role = classify_fallback(rel)
        if df.role in ('barrel', 'di'):
            skipped['barrel'] += 1
            continue
        files.append(df)

    tests = []
    if rels:
        for rel in walk_dart(root, 'test', True) + walk_dart(root, 'integration_test', True):
            try:
                df = DartFile(root, rel)
            except OSError:
                continue
            df.layer, df.role = 'test', 'test'
            tests.append(df)

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(pubspec, rels), 'fallback detection from pubspec and folders'
    aprof = arch['profile'] if arch and isinstance(arch.get('profile'), dict) else {}
    clean = bool(aprof.get('clean_architecture'))
    if not arch:
        clean = any('/domain/' in r for r in rels) and any('/data/' in r for r in rels) and \
            any(('/usecases/' in r or '/use_cases/' in r or '/entities/' in r) for r in rels)

    ck = Checker(root, files, tests, profile, clean, platforms, deps, only)
    if files:
        ck.run(rels)
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))

    stats = dict(ck.stats)
    stats['files'] = len(files)
    stats['skipped_generated'] = skipped['generated']
    stats['skipped_barrels'] = skipped['barrel']
    stats['platforms'] = platforms
    stats['breakpoint_tokens'] = sorted(set(n for n, _ in ck.token_names))
    stats['breakpoint_packages'] = sorted(deps & TOKEN_DEPS)
    stats['web_guards'] = sorted(ck.guard_names)
    stats['reported_scope'] = 'files list (%d)' % len(only) if only is not None else 'all'
    report = {
        'schema': SCHEMA, 'root': root, 'package': package,
        'profile': {'presentation': profile, 'source': psource, 'clean_architecture': clean},
        'classification': classification,
        'stats': stats,
        'findings': findings,
        'suppressed': suppressed,
    }
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2) + '\n')
        return 0

    toks = stats['breakpoint_tokens'] + stats['breakpoint_packages']
    out = ['== ADAPTIVE LAYOUT',
           '  profile: %s%s (%s)' % (profile, ' + clean' if clean else '', psource),
           '  classification: %s' % classification,
           '  scanned: %d files (%d generated skipped), %d test files; platforms: %s; breakpoint tokens: %s; '
           '%d LayoutBuilder, %d size reads, %d width comparisons, %d dart:io Platform checks' % (
               len(files), skipped['generated'], len(tests), ', '.join(platforms) or 'none found',
               ', '.join(toks[:4]) + (' ...' if len(toks) > 4 else '') if toks else 'none',
               stats['layout_builders'], stats['size_reads'], stats['width_comparisons'],
               stats['platform_checks'])]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no adaptive layout findings')
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
