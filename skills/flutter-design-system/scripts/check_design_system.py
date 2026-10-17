#!/usr/bin/env python3
"""check_design_system.py: find design-system drift in a Flutter project (read-only).

Usage:
  python3 -I check_design_system.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (token scales, theme registrations and
             ThemeExtensions are found across files); only findings in the listed files
             are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  DS-001 raw-color-in-widget              DS-007 theme-extension-mutable
  DS-002 raw-text-style-in-widget         DS-008 theme-mode-without-dark-theme
  DS-003 magic-spacing                    DS-009 brightness-branch-in-widget
  DS-004 magic-radius                     DS-010 fresh-theme-in-subtree
  DS-005 theme-extension-not-registered   DS-011 visual-token-in-logic
  DS-006 theme-extension-lerp-missing     DS-012 google-fonts-runtime-fetching

The checker is app-aware: DS-003/004 only fire when the project has its own spacing or
radius scale, and DS-001/002 drop to info when the project has no theme at all.
Literal rules report one finding per file (the first hit, with a count).

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so.

Suppression (in the analysed code):
  // ds-ignore: DS-001 <reason>        on the reported line or the line above
  // ds-ignore-file: DS-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/design-system@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

RULES = {
    'DS-001': ('raw-color-in-widget', 'low',
               'A widget hard-codes a colour (Color(0x...), Color.fromARGB, Colors.<name>) instead of reading a '
               'role from the theme, so it ignores dark mode, high contrast and rebrands.'),
    'DS-002': ('raw-text-style-in-widget', 'low',
               'A widget builds a TextStyle with a literal fontSize instead of using the textTheme (or the '
               'project\'s type tokens), so type drifts from the scale and ignores theme changes.'),
    'DS-003': ('magic-spacing', 'low',
               'The project has a spacing scale, but this widget uses literal padding/gap numbers. Use the '
               'scale so spacing stays consistent and can change in one place.'),
    'DS-004': ('magic-radius', 'low',
               'The project has a radius scale, but this widget uses a literal corner radius. Use the scale '
               '(or the component theme\'s shape).'),
    'DS-005': ('theme-extension-not-registered', 'high',
               'A ThemeExtension is registered in one theme but not the other (or in none), so '
               'Theme.of(context).extension<T>() returns null there. With `!` that is a crash the first '
               'time the app runs in that mode.'),
    'DS-006': ('theme-extension-lerp-missing', 'low',
               'A ThemeExtension\'s lerp() never interpolates its values, so animated theme changes (light/dark '
               'switch, AnimatedTheme) jump instead of fading.'),
    'DS-007': ('theme-extension-mutable', 'medium',
               'A ThemeExtension has a mutable field. Theme data is compared and lerped by value; mutating it '
               'changes every widget that already read it, without a rebuild.'),
    'DS-008': ('theme-mode-without-dark-theme', 'medium',
               'The app sets themeMode but passes no darkTheme, so choosing dark (or system dark) still shows '
               'the light theme.'),
    'DS-009': ('brightness-branch-in-widget', 'low',
               'A widget branches on brightness to pick colours. Put both values in the theme (ColorScheme or '
               'a ThemeExtension with light and dark instances) and read one role.'),
    'DS-010': ('fresh-theme-in-subtree', 'medium',
               'A widget wraps its subtree in Theme(data: ThemeData(...)) built from scratch, which throws away '
               'the app\'s colour scheme, text theme and extensions for everything below it.'),
    'DS-011': ('visual-token-in-logic', 'medium',
               'A logic or state class holds a visual value (Color, TextStyle, IconData...). Expose a semantic '
               'value (an enum such as Severity.warning) and let the view map it to theme tokens.'),
    'DS-012': ('google-fonts-runtime-fetching', 'low',
               'google_fonts downloads fonts at runtime by default: release builds call fonts.gstatic.com '
               '(a privacy and offline problem). Bundle the font files and set '
               'GoogleFonts.config.allowRuntimeFetching = false.'),
}

FIX_BY_PROFILE = {
    'DS-008': {
        'mvn': 'MVN: add darkTheme: AppTheme.dark and feed themeMode from ref.watch(themeModeProvider) (a notifier over a settings use case)',
        'riverpod': 'Riverpod: add darkTheme: AppTheme.dark and feed themeMode from ref.watch(themeModeProvider)',
        'mvvm': 'MVVM: add darkTheme: AppTheme.dark and feed themeMode from a settings view model (ListenableBuilder)',
        'bloc': 'Bloc: add darkTheme: AppTheme.dark and feed themeMode from BlocBuilder<ThemeCubit, ThemeMode>',
        'provider': 'Provider: add darkTheme: AppTheme.dark and feed themeMode from context.watch<SettingsModel>().themeMode',
        'getx': 'GetX: add darkTheme: AppTheme.dark to GetMaterialApp; Get.changeThemeMode() then switches it',
        'mvc': 'MVC: add darkTheme: AppTheme.dark and feed themeMode from the settings controller',
        'setstate': 'add darkTheme: AppTheme.dark; keep the ThemeMode in the app State and pass it down',
    },
    'DS-009': {
        'mvn': 'MVN: put the light and dark values in a ThemeExtension registered in both themes; the view reads context.appColors.x',
        'mvvm': 'MVVM: put both values in a ThemeExtension; the view reads context.appColors.x, the view model never sees colours',
        'bloc': 'Bloc: put both values in a ThemeExtension; BlocBuilder widgets read context.appColors.x',
        'getx': 'GetX: put both values in a ThemeExtension (not Get.isDarkMode checks); widgets read context.appColors.x',
    },
    'DS-011': {
        'mvn': 'MVN: the sealed state carries an enum (e.g. Severity.warning); the view switches it to context.colorScheme roles',
        'riverpod': 'Riverpod: the provider exposes an enum or a domain value; the widget maps it to theme roles',
        'mvvm': 'MVVM: the view model exposes an enum or a domain value; the view maps it to theme roles',
        'bloc': 'Bloc: the state carries a status enum; BlocBuilder maps it to theme roles in the widget',
        'provider': 'Provider: the model exposes an enum or a domain value; the widget maps it to theme roles',
        'getx': 'GetX: the controller exposes Rx<Severity>; Obx maps it to theme roles in the widget',
        'mvc': 'MVC: the controller exposes an enum; the view maps it to theme roles',
        'setstate': 'keep visual values in widgets; models expose an enum or a domain value',
    },
    'DS-001': {
        'getx': 'GetX: read Theme.of(context)/context.theme roles (not Get.isDarkMode ? a : b)',
    },
}
# DS-011 is a pattern violation where logic/state is a separate testable layer; lower elsewhere
DS011_LOW_PROFILES = ('getx', 'setstate', 'unknown', 'mvc')

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*|\.tailor)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
SUPPRESS_RE = re.compile(r'ds-ignore(-file)?\s*:\s*((?:DS-\d{3})(?:\s*,\s*DS-\d{3})*)\s*(.*)')

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
                      r'(?:const\s+)?([A-Za-z_]\w*)?(?:[^{;()]|\((?:[^()]|\([^()]*\))*\))*?\{')   # Dart primary constructors too
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


# ---------------------------------------------------------------------------------------- design-system model

THEME_PATH_RE = re.compile(r'(?i)(theme|colou?r|palette|style|token|typograph|dimens|spacing|design_tokens)')
TOKEN_CLASS_RE = re.compile(r'(?:Colou?rs?|Palette|Tokens?|Themes?|Styles?|Typography|Spacings?|Dimens|Insets|'
                            r'Radii|Radius|Corners|Shapes|Brand|Gaps|Elevations?|Durations?|Motion|Sizes)$')
THEME_CTOR_RE = re.compile(r'(?<![\w$.])(?:const\s+)?((?:ThemeData|ColorScheme|TextTheme|CupertinoThemeData|'
                           r'CupertinoTextThemeData|[A-Z]\w*Theme(?:Data)?))\s*(?:\.\s*\w+\s*)?\(')
APP_RE = re.compile(r'(?<![\w$.])(?:const\s+)?(MaterialApp|GetMaterialApp|CupertinoApp|WidgetsApp)'
                    r'(?:\s*\.\s*router)?\s*\(')
WIDGET_CLASS_RE = re.compile(r'\bextends\s+(?:\w+\s*\.\s*)?(?:StatelessWidget|StatefulWidget|ConsumerWidget|'
                             r'ConsumerStatefulWidget|HookWidget|HookConsumerWidget|StatelessHookWidget|GetView|'
                             r'GetWidget|State\s*<|ConsumerState\s*<|\w*Widget\b)')
EXT_CLASS_RE = re.compile(r'\bextends\s+ThemeExtension\s*<\s*(\w+)\s*>')
ENUM_RE = re.compile(r'\benum\s+([A-Za-z_]\w*)[^{;]*\{')

COLOR_RE = re.compile(r'(?<![\w$.])(?:const\s+)?(?:Color\s*\(\s*0[xX][0-9A-Fa-f]+|'
                      r'Color\s*\.\s*(?:fromARGB|fromRGBO|from)\s*\(|Colors\s*\.\s*([a-zA-Z]\w*))')
NUM = r'-?\d+(?:\.\d+)?'
NUM_RE = re.compile(r'^\s*(' + NUM + r')\s*$')
TEXTSTYLE_RE = re.compile(r'(?<![\w$.])(?:const\s+)?(TextStyle|GoogleFonts\s*\.\s*\w+)\s*\(')
INSETS_RE = re.compile(r'(?<![\w$.])(?:const\s+)?EdgeInsets(?:Directional)?\s*\.\s*(?:all|symmetric|only|fromLTRB|'
                       r'fromSTEB)\s*\(')
SIZEDBOX_RE = re.compile(r'(?<![\w$.])(?:const\s+)?SizedBox\s*\(')
GAP_RE = re.compile(r'(?<![\w$.])(?:const\s+)?(?:Gap|SliverGap)\s*\(\s*(' + NUM + r')\s*\)')
SPACING_ARG_RE = re.compile(r'(?<![\w$.])(spacing|runSpacing|mainAxisSpacing|crossAxisSpacing)\s*:\s*(' + NUM +
                            r')\s*[,)]')
RADIUS_RE = re.compile(r'(?<![\w$])(?:const\s+)?(?:BorderRadius(?:Directional)?|Radius)\s*\.\s*circular\s*\(\s*(' +
                       NUM + r')\s*\)')
BRIGHTNESS_RE = re.compile(
    r'(?:Theme\s*\.\s*of\s*\(\s*\w+\s*\)|(?<![\w$.])theme|(?<![\w$.])colorScheme|\.\s*colorScheme|'
    r'(?<![\w$.])context\s*\.\s*theme)\s*\.\s*brightness\b|(?<![\w$])Get\s*\.\s*isDarkMode\b|'
    r'(?<![\w$.])context\s*\.\s*isDarkMode\b|'
    r'(?P<platform>MediaQuery\s*\.\s*platformBrightnessOf\s*\(|\.\s*platformBrightness\b)')
VISUAL_TYPE_RE = re.compile(r'^(?:List\s*<\s*)?(Color|MaterialColor|MaterialAccentColor|TextStyle|IconData|Gradient|'
                            r'LinearGradient|RadialGradient|BoxDecoration|BoxShadow|ShapeBorder)\s*>?\??$')
SCALE_NAMES = {'xxxs', 'xxs', 'xs', 's', 'sm', 'small', 'm', 'md', 'medium', 'l', 'lg', 'large', 'xl', 'xxl', 'xxxl',
               'tiny', 'huge', 'none', 'x1', 'x2', 'x3', 'x4', 'x5', 'x6', 'half', 'base', 'normal', 'big'}
SPACING_NAME_RE = re.compile(r'(?i)(spac|gap|inset|padding|margin|dimen|gutter|layout)')
RADIUS_NAME_RE = re.compile(r'(?i)(radi|corner|rounded|shape)')
NOT_SCALE_NAME_RE = re.compile(r'(?i)(duration|time|motion|elevation|opacity|alpha|font|text|icon|breakpoint|border|'
                               r'stroke|line|width|avatar|'
                               r'z(index)?$|weight)')


ARTWORK_PATH_RE = re.compile(r'(?i)(illustration|artwork|painters?/|_painter\.dart$)')
BW_RE = re.compile(r'^(?:white|black)\d*$')
BW_HEX_RE = re.compile(r'(?:const\s+)?Color\s*\(\s*0[xX][0-9A-Fa-f]{2}(?:000000|[Ff]{6})\s*\)')
SHADOW_CALLS = ('Shadow', 'BoxShadow')
SHADOW_ARGS = ('shadowColor', 'barrierColor', 'scrimColor', 'shadow', 'shadows', 'modalBarrierColor')


def context_at(df, pos):
    """(callee, argument name) of the innermost call whose parentheses enclose pos."""
    m = df.masked
    depth, i, arg = 0, pos - 1, None
    lo = max(0, pos - 3000)
    while i >= lo:
        ch = m[i]
        if ch in ')]}':
            depth += 1
        elif ch in '([{':
            if depth == 0:
                if arg is None:
                    am = re.match(r'\s*([A-Za-z_$][\w$]*)\s*:', m[i + 1:pos])
                    arg = am.group(1) if am else ''
                if ch != '(':
                    return '', arg
                cm = re.search(r'([A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>\s*)?$', m[max(0, i - 80):i])
                return (cm.group(1) if cm else ''), arg
            depth -= 1
        elif ch == ',' and depth == 0 and arg is None:
            am = re.match(r'\s*([A-Za-z_$][\w$]*)\s*:', m[i + 1:pos])
            arg = am.group(1) if am else ''
        i -= 1
    return '', arg or ''


def in_spans(spans, pos):
    for s, e in spans:
        if s <= pos < e:
            return True
    return False


def class_members(df, o, c):
    """Class-level declarations of the class whose body is masked[o..c]: list of dicts
    {pos, text, static, final, late, const, kind ('field'|'getter'|'method'), type, name, init}."""
    m = df.masked
    out = []
    depth_b = depth_p = 0
    seg_start = o + 1
    i = o + 1

    def flush(s, e):
        raw = m[s:e]
        lead = len(raw) - len(raw.lstrip())
        txt = ' '.join(raw.split())
        if not txt:
            return
        txt = re.sub(r'^(?:@\w+(?:\s*\([^()]*\))?\s*)+', '', txt)
        pos = s + lead
        d = {'pos': pos, 'text': txt}
        gm = re.match(r'^(static\s+)?(?:external\s+)?([\w$<>?,\s.]+?)\s+get\s+([A-Za-z_$][\w$]*)', txt)
        if gm:
            d.update(kind='getter', static=bool(gm.group(1)), type=gm.group(2).strip(), name=gm.group(3),
                     final=True, late=False, const=False, init=None)
            out.append(d)
            return
        head = txt.split('=', 1)[0]
        if '(' in head or txt.startswith(('factory ', 'operator ')):
            mm = re.match(r'^(static\s+)?([\w$<>?,\s.]+?)\s+([A-Za-z_$][\w$]*)\s*(?:<[^()]*>)?\s*\(', txt)
            if mm and mm.group(2).split()[-1] not in ('new', 'return'):
                d.update(kind='method', static=bool(mm.group(1)), type=mm.group(2).strip(), name=mm.group(3),
                         final=True, late=False, const=False, init=None)
                out.append(d)
            return
        fm = re.match(r'^(static\s+)?(late\s+)?(final\s+|const\s+|var\s+)?(covariant\s+)?'
                      r'(?:([A-Za-z_$][\w$<>?,\s.]*?)\s+)?([A-Za-z_$][\w$]*)\s*(?:=\s*(.*))?$', txt, re.S)
        if fm and fm.group(6) not in ('return', 'super', 'this'):
            mod = (fm.group(3) or '').strip()
            d.update(kind='field', static=bool(fm.group(1)), late=bool(fm.group(2)), final=mod == 'final',
                     const=mod == 'const', var=mod == 'var', type=(fm.group(5) or '').strip(), name=fm.group(6),
                     init=fm.group(7))
            if d['type'] or mod or d['init'] is not None:
                out.append(d)

    while i < c:
        ch = m[i]
        if ch == '(':
            depth_p += 1
        elif ch == ')':
            depth_p -= 1
        elif ch == '{':
            depth_b += 1
        elif ch == '}':
            depth_b -= 1
            if depth_b == 0 and depth_p == 0:
                nxt = re.match(r'\s*[;,)]', m[i + 1:i + 8])
                if not nxt:
                    flush(seg_start, i + 1)
                    seg_start = i + 1
        elif ch == ';' and depth_b == 0 and depth_p == 0:
            flush(seg_start, i)
            seg_start = i + 1
        i += 1
    flush(seg_start, c)
    return out


def numeric_value(member):
    """The literal number a token member stands for (8 in `= 8`, `= 8.0 * _scale`, `=> 8`), else None."""
    init = member.get('init')
    if member['kind'] == 'getter':
        gm = re.search(r'=>\s*(' + NUM + r')\b', member['text'])
        return float(gm.group(1)) if gm else None
    if init is None:
        return None
    mm = re.match(r'\s*(?:const\s+)?(' + NUM + r')\s*(?:\*\s*[\w$.]+\s*)?$', init)
    return float(mm.group(1)) if mm else None


class Model(object):
    """Project-wide facts: token scales, theme constructions, ThemeExtensions."""

    def __init__(self, files, pubspec):
        self.files = files
        self.pubspec = pubspec
        self.ext_classes = {}        # name -> (df, pos, open, close)
        self.themes = []             # dicts: df, pos, brightness, ext (set or None if unresolved), label
        self.spacing_scales = []     # (class name, file, values)
        self.radius_scales = []
        self.token_classes = 0
        self.has_theme = False
        self.has_design_system = False
        self.ext_reads = {}          # name -> [(df, pos, bang)]
        self.user_theme_mode = False

    def build(self):
        for df in self.files:
            self._file(df)
        for df in self.files:
            self._themes(df)
        self.has_design_system = bool(self.ext_classes or self.token_classes or self.spacing_scales or
                                      any(t['rich'] for t in self.themes) or
                                      any(THEME_PATH_RE.search(df.rel) and re.search(
                                          r'\b(?:ThemeData|ColorScheme)\b', df.masked) for df in self.files))

    def _file(self, df):
        m = df.masked
        df.is_theme_file = bool(THEME_PATH_RE.search(df.rel))
        df.exempt = []                       # spans where literals are definitions, not uses
        df.ext_spans = []
        df.token_spans = []
        df.widget_spans = []
        if re.search(r'(?<![\w$.])(?:ThemeData|ColorScheme|CupertinoThemeData)\s*(?:\.\s*\w+\s*)?\(', m) or \
                EXT_CLASS_RE.search(m):
            self.has_theme = True
        for name, o, c, header in df.classes:
            em = EXT_CLASS_RE.search(header)
            is_ext = bool(em and not re.search(r'\babstract\b', header.split('class')[0]))
            if is_ext:
                self.ext_classes[name] = (df, o - len(header) + 1, o, c)    # header start, body open/close
                df.ext_spans.append((o, c))
                df.exempt.append((o, c))
            elif re.search(r'\bextends\s+(?:CustomPainter|CustomClipper|ShapeBorder|OutlinedBorder)\b', header):
                df.exempt.append((o, c))         # painting code: colours and sizes are geometry, not theme
                continue
            elif WIDGET_CLASS_RE.search(header):
                df.widget_spans.append((o, c))
                continue
            elif name and TOKEN_CLASS_RE.search(name.lstrip('_')):
                df.token_spans.append((o, c))
                df.exempt.append((o, c))
                self.token_classes += 1
            if not name:
                continue
            self._scale(df, name, o, c, is_ext)
        # top-level spacing constants: const kSpacingSm = 8.0;
        public_tokens = df.is_theme_file or not WIDGET_CLASS_RE.search(m)
        tl = [] if not public_tokens else re.findall(r'^(?:const|final)\s+(?:double\s+|int\s+)?(k?[A-Za-z]\w*(?:[Ss]pac|[Gg]ap|[Pp]adding|[Ii]nset|'
                        r'[Mm]argin)\w*)\s*=\s*' + NUM + r'\s*;', m, re.M)
        if len(tl) >= 3:
            self.spacing_scales.append(('top-level constants', df.rel, []))
        tr = [] if not public_tokens else re.findall(r'^(?:const|final)\s+(?:double\s+|int\s+)?(k?[A-Za-z]\w*[Rr]adi\w*)\s*=\s*' + NUM + r'\s*;', m, re.M)
        if len(tr) >= 3:
            self.radius_scales.append(('top-level constants', df.rel, []))
        # spans of theme constructors and theme: arguments
        for mm in THEME_CTOR_RE.finditer(m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is not None:
                df.exempt.append((mm.start(), pc + 1))
        for mm in APP_RE.finditer(m):
            po = mm.end() - 1
            args, pc = arg_map(df, po)
            for k in ('theme', 'darkTheme', 'highContrastTheme', 'highContrastDarkTheme'):
                if k in args:
                    df.exempt.append(args[k])
        for mm in re.finditer(r'\.\s*extension\s*<\s*(\w+)\s*>\s*\(\s*\)\s*(!)?', m):
            self.ext_reads.setdefault(mm.group(1), []).append((df, mm.start(), bool(mm.group(2))))
        # semantic mappings: Color colorFor(Severity s) => switch ..., Color get toColor { ... }
        for mm in re.finditer(r'(?<![\w$.<])(?:Color|MaterialColor|Gradient|LinearGradient)\??\s+(?:get\s+)?[A-Za-z_$][\w$]*'
                              r'\s*(?:\([^(){};]*\))?\s*(?:\{|=>)', m):
            bo = mm.end() - 1 if m[mm.end() - 1] == '{' else mm.end() - 2
            if m[bo] == '{':
                bc = df.braces.get(bo)
            else:
                bc = expr_end(m, bo + 2)
            if bc is not None:
                df.exempt.append((bo, bc + 1))
        # palette definitions outside functions: static const red = Color(0xFF...);
        for mm in re.finditer(r'(?m)^[ \t]*(?:static\s+)?(?:const|final|late\s+final)\s+(?:[\w<>?]+\s+)?\w+\s*=\s*'
                              r'(?:const\s+)?(?:Color\b|Colors\s*\.|Material(?:Accent)?Color\s*\(|TextStyle\s*\(|GoogleFonts\s*\.)', m):
            if df.enclosing_func(mm.start()) is None:
                end = expr_end(m, mm.end())
                df.exempt.append((mm.start(), end + 1))

    def _scale(self, df, name, o, c, is_ext):
        """Record a spacing or radius scale: >= 3 distinct literal steps (or >= 3 typed fields in a ThemeExtension)."""
        members = class_members(df, o, c)
        nums = [(mb['name'], numeric_value(mb)) for mb in members if mb['kind'] in ('field', 'getter')]
        nums = [(n, v) for n, v in nums if v is not None]
        typed = [mb['name'] for mb in members if is_ext and mb['kind'] == 'field' and not mb['static'] and
                 re.match(r'^(?:double|int|num)\??$', mb['type'] or '')]
        plain = name.lstrip('_')
        if NOT_SCALE_NAME_RE.search(plain):
            return

        def steps(pairs):
            return len(set(v for _, v in pairs if 0 < v <= 64))     # a scale has small steps, not screen sizes
        if RADIUS_NAME_RE.search(plain):
            if steps(nums) >= 3 or len(typed) >= 3:
                self.radius_scales.append((name, df.rel, sorted(set(v for _, v in nums))))
            return
        radius_named = [(n, v) for n, v in nums if re.search(r'(?i)radi', n)]
        if steps(radius_named) >= 3:
            self.radius_scales.append((name, df.rel, sorted(set(v for _, v in radius_named))))
        spacing_named = [(n, v) for n, v in nums if SPACING_NAME_RE.search(n)]
        scale_named = [(n, v) for n, v in nums if n.lower().lstrip('_') in SCALE_NAMES]
        typed_named = [n for n in typed if SPACING_NAME_RE.search(n) or n.lower() in SCALE_NAMES]
        if (SPACING_NAME_RE.search(plain) and (steps(nums) >= 3 or len(typed) >= 3)) or \
                steps(spacing_named) >= 3 or (steps(scale_named) >= 4 and not radius_named) or len(typed_named) >= 4:
            self.spacing_scales.append((name, df.rel, sorted(set(v for _, v in nums))))

    def _themes(self, df):
        m, code = df.masked, df.code
        for mm in re.finditer(r'(?<![\w$.])(?:const\s+)?ThemeData\s*(?:\.\s*(light|dark|from|raw|fallback)\s*)?\(', m):
            po = mm.end() - 1
            args, pc = arg_map(df, po)
            if pc == po:
                continue
            callee, arg = context_at(df, mm.start())
            if arg == 'data' and callee in ('Theme', 'AnimatedTheme'):
                continue                        # a local override, not one of the app's themes
            ext = None
            if 'extensions' in args:
                ext = self._resolve_ext(code[args['extensions'][0]:args['extensions'][1]])
            else:
                # ThemeData.light().copyWith(extensions: [...]) on the same expression
                tail = re.match(r'\s*\.\s*copyWith\s*\(', m[pc + 1:pc + 40])
                if tail:
                    a2, _ = arg_map(df, pc + 1 + tail.end() - 1)
                    if 'extensions' in a2:
                        ext = self._resolve_ext(code[a2['extensions'][0]:a2['extensions'][1]])
                if ext is None:
                    ext = set()
            body = code[po:pc]
            rich = any(k in args for k in ('textTheme', 'extensions')) or \
                len([k for k in args if k.endswith('Theme')]) >= 2 or \
                bool(re.search(r'colorScheme\s*:\s*(?:const\s+)?(?!ColorScheme\s*\.\s*fromSeed)\S', body))
            self.themes.append({'df': df, 'pos': mm.start(), 'brightness': self._brightness(df, mm, args, body),
                                'ext': ext, 'rich': rich, 'span': (po, pc)})
        # extensions: added later through someTheme.copyWith(extensions: ...): brightness unknown
        inside = [t['span'] for t in self.themes if t['df'] is df]
        for em in re.finditer(r'(?<![\w$.])extensions\s*:', m):
            if in_spans(inside, em.start()) or any(s < em.start() <= e for s, e in inside):
                continue
            v0 = em.end()
            v1 = expr_end(m, v0)
            self.themes.append({'df': df, 'pos': em.start(), 'brightness': 'unknown',
                                'ext': self._resolve_ext(code[v0:v1]), 'rich': True, 'span': (v0, v1)})

    @staticmethod
    def _resolve_ext(txt):
        """Type names in an extensions: [...] list, or None when an element can't be resolved statically."""
        t = txt.strip()
        t = re.sub(r'^(?:const\s+)?(?:<[^\[]*>\s*)?', '', t)
        if not t.startswith('[') or not t.endswith(']'):
            return None
        inner = t[1:-1]
        parts, depth, cur = [], 0, ''
        for ch in inner:
            if ch in '([{<':
                depth += 1
            elif ch in ')]}>':
                depth -= 1
            if ch == ',' and depth == 0:
                parts.append(cur)
                cur = ''
            else:
                cur += ch
        parts.append(cur)
        out = set()
        for p in parts:
            p = p.strip()
            if not p:
                continue
            em = re.match(r'^(?:const\s+)?([A-Z]\w*)\b', p)
            if not em:
                return None
            out.add(em.group(1))
        return out

    @staticmethod
    def _brightness(df, mm, args, body):
        if mm.group(1) in ('light', 'dark'):
            return mm.group(1)
        bv = df.code[args['brightness'][0]:args['brightness'][1]].strip() if 'brightness' in args else ''
        if bv:
            if re.match(r'^Brightness\s*\.\s*dark$', bv):
                return 'dark'
            if re.match(r'^Brightness\s*\.\s*light$', bv):
                return 'light'
            return 'param'
        if 'colorScheme' in args:
            cs = df.code[args['colorScheme'][0]:args['colorScheme'][1]]
            if re.search(r'Brightness\s*\.\s*dark|ColorScheme\s*\.\s*dark\b|[Dd]ark', cs):
                return 'dark'
            if re.search(r'Brightness\s*\.\s*light|ColorScheme\s*\.\s*light\b|[Ll]ight', cs):
                return 'light'
            if re.search(r'\bbrightness\s*:\s*\w', cs) or re.match(r'^\s*[a-z_]\w*\s*$', cs):
                return 'param'
        before = df.masked[max(0, mm.start() - 160):mm.start()]
        nm = re.search(r'([A-Za-z_$][\w$]*)\s*(?:\([^()]*\)\s*)?(?:=>|=|\{\s*return)\s*(?:const\s+)?$', before)
        f = df.enclosing_func(mm.start())
        names = ' '.join(x for x in (nm.group(1) if nm else '', f[0] if f else '') if x)
        if re.search(r'(?i)dark|night', names):
            return 'dark'
        if re.search(r'(?i)light|day', names):
            return 'light'
        return 'unknown'


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, files, profile, model):
        self.files = files
        self.profile = profile
        self.model = model
        self.findings = []
        self.suppressed = []
        self.stats = {'literal_colors': 0, 'raw_text_styles': 0, 'spacing_literals': 0, 'radius_literals': 0,
                      'theme_extensions': len(model.ext_classes), 'themes': len(model.themes),
                      'spacing_scale': ', '.join(sorted(set('%s (%s)' % (n, f) for n, f, _ in model.spacing_scales))),
                      'radius_scale': ', '.join(sorted(set('%s (%s)' % (n, f) for n, f, _ in model.radius_scales))),
                      'design_system': model.has_design_system, 'has_theme': model.has_theme}

    # -- reporting
    def add(self, df, rid, pos, evidence, note='', severity=None):
        ln = df.line_of(pos)
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
        prof = FIX_BY_PROFILE.get(rid, {}).get(self.profile, '')
        if prof:
            note = (note + '; ' + prof) if note else prof
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    def add_grouped(self, df, rid, hits, note_fmt, severity=None):
        """One finding per file: the first hit not suppressed, with the count of the rest."""
        kept = []
        for pos, ev in hits:
            ln = df.line_of(pos)
            reason = df.suppress_file.get(rid)
            if reason is None:
                for l in (ln, ln - 1):
                    if rid in df.suppress_line.get(l, {}):
                        reason = df.suppress_line[l][rid]
                        break
            if reason is not None:
                self.suppressed.append({'id': rid, 'file': df.rel, 'line': ln, 'reason': reason})
            else:
                kept.append((pos, ev))
        if not kept:
            return
        pos, ev = kept[0]
        more = len(kept) - 1
        note = note_fmt % {'n': len(kept)} if note_fmt else ''
        if more:
            ev = '%s   (+%d more in this file)' % (ev, more)
        self._add_raw(df, rid, pos, ev, note, severity)

    def _add_raw(self, df, rid, pos, ev, note, severity):
        prof = FIX_BY_PROFILE.get(rid, {}).get(self.profile, '')
        if prof:
            note = (note + '; ' + prof) if note else prof
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': severity or RULES[rid][1],
                              'file': df.rel, 'line': df.line_of(pos), 'evidence': ev, 'message': RULES[rid][2],
                              'note': note})

    @staticmethod
    def is_ui(df):
        if df.role in ('logic', 'state', 'event', 'barrel', 'di'):
            return False
        if df.layer in ('domain', 'data'):
            return False
        return df.role in ('view', 'widget') or bool(df.widget_spans)

    def run(self):
        for df in self.files:
            ui = self.is_ui(df) and not df.is_theme_file and not ARTWORK_PATH_RE.search(df.rel)
            if ui:
                self.check_colors(df)
                self.check_text_styles(df)
                if self.model.spacing_scales:
                    self.check_spacing(df)
                if self.model.radius_scales:
                    self.check_radius(df)
                self.check_brightness(df)
            if self.is_ui(df):
                self.check_fresh_theme(df)
            if df.role in ('logic', 'state'):
                self.check_logic_tokens(df)
            self.check_apps(df)
        self.check_extensions()
        self.check_google_fonts()

    @staticmethod
    def _call_has(df, pos, argname):
        m = df.masked
        depth, i = 0, pos - 1
        while i >= max(0, pos - 3000):
            if m[i] in ')]}':
                depth += 1
            elif m[i] in '([{':
                if depth == 0:
                    if m[i] != '(':
                        return False
                    args, _ = arg_map(df, i)
                    return argname in args
                depth -= 1
            i -= 1
        return False

    def _literal_ok(self, df, pos):
        return in_spans(df.exempt, pos)

    # -- DS-001 raw colours
    def check_colors(self, df):
        m = df.masked
        hits, strong, bw_pos = [], 0, set()
        for mm in COLOR_RE.finditer(m):
            name = mm.group(1)
            if name == 'transparent' or self._literal_ok(df, mm.start()):
                continue
            if re.match(r'(?:const\s+)?Color\s*\(\s*0[xX]00[0-9A-Fa-f]{6}\s*\)', m[mm.start():mm.start() + 30]):
                continue                        # fully transparent
            callee, arg = context_at(df, mm.start())
            bw = bool(name and BW_RE.match(name)) or bool(BW_HEX_RE.match(m, mm.start()))
            if bw and (callee in SHADOW_CALLS or arg in SHADOW_ARGS):
                continue                        # shadows and scrims are black/white by nature
            if re.search(r'extension\s*<[^;]*\?\?\s*$', m[max(0, mm.start() - 200):mm.start()]):
                continue                        # fallback after a nullable ThemeExtension read
            if arg == 'color' and self._call_has(df, mm.start(), 'colorBlendMode'):
                continue                        # an image tint, not a surface colour
            end = mm.end()
            if name is None:
                po = m.find('(', mm.start())
                end = df.parens.get(po, po) + 1
                ctor = m[mm.start():po].rstrip()
                if ctor.endswith(('fromARGB', 'fromRGBO', 'from')):
                    vals = [m[a:b].strip() for _, a, b in split_args(df, po)[0]]
                    if not all(NUM_RE.match(v) for v in vals if v):
                        continue                # computed from variables: colour maths, not a literal
                    rgb = vals[1:4] if ctor.endswith('fromARGB') else vals[:3]
                    if len(set(rgb)) == 1 and rgb[0] in ('0', '255'):
                        bw = True                # black or white with alpha: a scrim or overlay
            else:
                sm = re.match(r'\s*(?:\.\s*shade\d+|\[\s*\d+\s*\])', m[end:end + 20])
                if sm:
                    end += sm.end()
            ev = ' '.join(df.code[mm.start():end].split())
            hits.append((mm.start(), ev))
            if bw:
                bw_pos.add(mm.start())
            else:
                strong += 1
        self.stats['literal_colors'] += len(hits)
        if not hits:
            return
        if not self.model.has_design_system:
            sev, note = 'info', 'no theme tokens in this project yet; graded info. '
        elif not strong:
            sev, note = 'info', 'only Colors.white/black (often over images); graded info. '
        else:
            sev, note = None, ''
            hits.sort(key=lambda h: (h[0] in bw_pos, h[0]))      # lead with a non-black/white hit
        note += 'use Theme.of(context).colorScheme.<role> or the project\'s ThemeExtension tokens'
        self.add_grouped(df, 'DS-001', hits, note, severity=sev)

    # -- DS-002 raw TextStyle(fontSize: n)
    def check_text_styles(self, df):
        m = df.masked
        hits = []
        for mm in TEXTSTYLE_RE.finditer(m):
            if self._literal_ok(df, mm.start()):
                continue
            po = mm.end() - 1
            args, pc = arg_map(df, po)
            if 'fontSize' not in args:
                continue
            v = m[args['fontSize'][0]:args['fontSize'][1]]
            if not NUM_RE.match(v):
                continue
            callee, arg = context_at(df, mm.start())
            if callee == 'Text' and arg == 'style':
                seg = df.code[max(0, mm.start() - 400):mm.start()]
                lit = re.search(r'Text\s*\(\s*([\'"])(.*?)\1\s*,\s*(?:\w+\s*:[^,]*,\s*)*style\s*:\s*(?:const\s+)?$', seg, re.S)
                if lit and not re.search(r'[A-Za-z0-9]', lit.group(2)):
                    continue                    # an emoji or glyph sized like an icon
            hits.append((mm.start(), '%s(fontSize: %s, ...)' % (mm.group(1).replace(' ', ''), v.strip())))
        self.stats['raw_text_styles'] += len(hits)
        if hits:
            sev = None if self.model.has_design_system else 'info'
            self.add_grouped(df, 'DS-002', hits,
                             'use Theme.of(context).textTheme.<style> (copyWith for colour/weight only)', severity=sev)

    # -- DS-003 magic spacing
    def check_spacing(self, df):
        m = df.masked
        hits = []

        def big(v):
            return abs(float(v)) > 2
        for mm in INSETS_RE.finditer(m):
            if self._literal_ok(df, mm.start()):
                continue
            po = mm.end() - 1
            args, pc = split_args(df, po)
            vals = [m[s:e].strip() for _, s, e in args]
            lits = [v for v in vals if NUM_RE.match(v) and big(v)]
            if lits:
                hits.append((mm.start(), ' '.join(df.code[mm.start():pc + 1].split())[:90]))
        for mm in SIZEDBOX_RE.finditer(m):
            if self._literal_ok(df, mm.start()):
                continue
            po = mm.end() - 1
            args, pc = arg_map(df, po)
            if 'child' in args or ('height' in args) == ('width' in args):
                continue
            k = 'height' if 'height' in args else 'width'
            v = m[args[k][0]:args[k][1]]
            if NUM_RE.match(v) and big(v):
                hits.append((mm.start(), 'SizedBox(%s: %s)' % (k, v.strip())))
        for rx in (GAP_RE, SPACING_ARG_RE):
            for mm in rx.finditer(m):
                if self._literal_ok(df, mm.start()):
                    continue
                v = mm.group(mm.lastindex)
                if big(v):
                    ev = ' '.join(df.code[mm.start():mm.end()].split())
                    hits.append((mm.start(), ev[:-1].rstrip() if rx is SPACING_ARG_RE else ev))
        hits.sort()
        self.stats['spacing_literals'] += len(hits)
        if hits:
            n, f, _ = self.model.spacing_scales[0]
            self.add_grouped(df, 'DS-003', hits, 'the project\'s scale is %s in %s' % (n, f))

    # -- DS-004 magic radius
    def check_radius(self, df):
        m = df.masked
        hits = []
        for mm in RADIUS_RE.finditer(m):
            if self._literal_ok(df, mm.start()):
                continue
            if not 0 < abs(float(mm.group(1))) < 99:
                continue                        # 99/999/1000 is the pill idiom (StadiumBorder), not a step
            hits.append((mm.start(), ' '.join(df.code[mm.start():mm.end()].split())))
        self.stats['radius_literals'] += len(hits)
        if hits:
            n, f, _ = self.model.radius_scales[0]
            self.add_grouped(df, 'DS-004', hits, 'the project\'s radius scale is %s in %s' % (n, f))

    # -- DS-009 brightness branches
    def check_brightness(self, df):
        m = df.masked
        if APP_RE.search(m):
            return                              # the app root resolves ThemeMode.system itself
        hits, platform = [], False
        for mm in BRIGHTNESS_RE.finditer(m):
            if in_spans(df.exempt, mm.start()):
                continue
            if not self._branches(df, mm):
                continue                        # forwarded to a style factory or a package, not branched on
            if mm.group('platform'):
                platform = True
            ev = df.lines[df.line_of(mm.start()) - 1].strip()
            hits.append((mm.start(), ev[:110]))
        if hits:
            sev = 'medium' if platform and self.model.user_theme_mode else None
            note = 'platform brightness ignores the in-app ThemeMode setting' if sev else ''
            self.add_grouped(df, 'DS-009', hits, note, severity=sev)

    @staticmethod
    def _branches(df, mm):
        m = df.masked
        if 'isDarkMode' in mm.group(0):
            return True
        after = m[mm.end():mm.end() + 40]
        before = m[max(0, mm.start() - 60):mm.start()]
        if re.match(r'\s*(?:\)\s*)?(?:[!=]=|\?(?![?.]))', after) or re.search(r'[!=]=\s*$', before) or \
                re.search(r'switch\s*\(\s*$', before):
            return True
        am = re.search(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*=\s*$', before)
        if am and re.match(r'\s*;', after):
            var = re.escape(am.group(1))
            f = df.enclosing_func(mm.start())
            lo, hi = (f[2], f[3]) if f else (mm.end(), min(len(m), mm.end() + 2000))
            body = m[mm.end():hi]
            return bool(re.search(r'(?<![\w$.])%s\s*(?:[!=]=|\?(?![?.]))|[!=]=\s*%s\b|switch\s*\(\s*%s\s*\)|'
                                  r'(?<![\w$.])%s\s*\)\s*\{' % (var, var, var, var), body))
        return False

    # -- DS-010 Theme(data: ThemeData(...)) from scratch below the app
    def check_fresh_theme(self, df):
        m, code = df.masked, df.code
        app_spans = []
        for mm in APP_RE.finditer(m):
            pc = df.parens.get(mm.end() - 1)
            if pc is not None:
                app_spans.append((mm.start(), pc))
        for mm in re.finditer(r'(?<![\w$.])(?:const\s+)?Theme\s*\(', m):
            if in_spans(app_spans, mm.start()):
                continue
            args, pc = arg_map(df, mm.end() - 1)
            if 'data' not in args:
                continue
            v = code[args['data'][0]:args['data'][1]]
            if not re.match(r'\s*(?:const\s+)?ThemeData\s*(?:\.\s*(?:light|dark|from)\s*)?\(', v):
                continue
            if re.search(r'Theme\s*\.\s*of\s*\(|\bcontext\b|\btheme\b|copyWith|colorScheme\s*:\s*[a-z_]', v):
                continue
            self.add(df, 'DS-010', mm.start(), ' '.join(code[mm.start():args['data'][0] + 30].split()) + '...',
                     note='derive it instead: Theme(data: Theme.of(context).copyWith(...))')

    # -- DS-011 Color/TextStyle/IconData in logic or state
    def check_logic_tokens(self, df):
        if df.is_theme_file:
            return
        m = df.masked
        spans = [(name, o, c, header) for name, o, c, header in df.classes]
        for em in ENUM_RE.finditer(m):
            o = em.end() - 1
            c = df.braces.get(o)
            if c is not None:
                spans.append((em.group(1), o, c, em.group(0)))
        hits, names = [], []
        for name, o, c, header in spans:
            if not name or re.search(r'(?i)theme|colou?r|palette|style|appearance|brand', name):
                continue
            if WIDGET_CLASS_RE.search(header) or EXT_CLASS_RE.search(header) or \
                    re.search(r'\bextends\s+(?:CustomPainter|CustomClipper)\b', header):
                continue
            if any(o2 < o and c < c2 for _, o2, c2, _ in spans):
                continue
            if header.lstrip().startswith('extension'):
                continue
            for mb in class_members(df, o, c):
                t = (mb.get('type') or '').strip()
                if mb['kind'] == 'field' and not t and mb.get('init'):
                    im = re.match(r'\s*(?:const\s+)?(Colors\s*\.|Color\s*\(|TextStyle\s*\(|Icons\s*\.)', mb['init'])
                    if im and not mb['static']:
                        t = {'Colors': 'Color', 'Color': 'Color', 'TextStyle': 'TextStyle',
                             'Icons': 'IconData'}[re.match(r'\w+', im.group(1)).group(0)]
                if mb['static'] or mb['kind'] == 'method':
                    continue                    # constants and pure helpers are not state
                if VISUAL_TYPE_RE.match(t):
                    hits.append((mb['pos'], '%s.%s: %s' % (name, mb['name'], t)))
                    names.append('%s %s' % (VISUAL_TYPE_RE.match(t).group(1), mb['name']))
        if hits:
            sev = 'low' if self.profile in DS011_LOW_PROFILES else 'medium'
            self.add_grouped(df, 'DS-011', hits, '', severity=sev)

    # -- DS-008 themeMode without darkTheme (also records whether ThemeMode is user-controlled)
    def check_apps(self, df):
        m, code = df.masked, df.code
        for mm in APP_RE.finditer(m):
            if mm.group(1) in ('CupertinoApp', 'WidgetsApp'):
                continue
            args, pc = arg_map(df, mm.end() - 1)
            if pc == mm.end() - 1 or 'themeMode' not in args:
                continue
            tm = ' '.join(code[args['themeMode'][0]:args['themeMode'][1]].split())
            if 'darkTheme' in args:
                continue
            if re.match(r'^(?:ThemeMode)?\s*\.\s*light$', tm):
                continue
            self.add(df, 'DS-008', mm.start(), '%s(themeMode: %s, ...) without darkTheme' % (mm.group(1), tm))

    def scan_theme_mode(self):
        for df in self.files:
            for mm in APP_RE.finditer(df.masked):
                args, pc = arg_map(df, mm.end() - 1)
                if 'themeMode' in args:
                    tm = ' '.join(df.code[args['themeMode'][0]:args['themeMode'][1]].split())
                    if not re.match(r'^(?:ThemeMode)?\s*\.\s*(?:light|dark|system)$', tm):
                        self.model.user_theme_mode = True

    # -- DS-005/006/007 ThemeExtensions
    def check_extensions(self):
        themes = self.model.themes
        light = [t for t in themes if t['brightness'] == 'light']
        dark = [t for t in themes if t['brightness'] == 'dark']
        ambiguous = [t for t in themes if t['brightness'] in ('unknown', 'param')]
        unresolved = any(t['ext'] is None for t in themes)
        for name in sorted(self.model.ext_classes):
            df, hpos, o, c = self.model.ext_classes[name]
            reads = self.model.ext_reads.get(name, [])
            bang = [r for r in reads if r[2]]
            members = class_members(df, o, c)
            inst = [mb for mb in members if mb['kind'] == 'field' and not mb['static']]
            header = df.masked[hpos:o]
            for pm in re.finditer(r'\b(final|var)\s+[\w$<>?,. ]+?\s+([A-Za-z_$][\w$]*)\s*[,})=]', header):
                inst.append({'kind': 'field', 'static': False, 'final': pm.group(1) == 'final', 'const': False,
                             'name': pm.group(2), 'pos': hpos + pm.start()})     # primary constructor fields
            # DS-007 mutable fields
            mut = [mb for mb in inst if not mb['final'] and not mb['const']]
            if mut:
                self.add(df, 'DS-007', mut[0]['pos'], '%s.%s is not final' % (name, mut[0]['name']),
                         note='make every field final and the constructor const; change values through copyWith')
            # DS-006 lerp that never interpolates
            lerp = df.func_named('lerp', (name, o, c, ''))
            if lerp and inst:
                body = df.masked[lerp[2]:lerp[3] + 1]
                if not re.search(r'(?<![\w$])(?:[\w$]+\s*\.\s*)?lerp\w*\s*[(<]|(?<![\w$])\w+[Ll]erp\w*\s*\(', body):
                    self.add(df, 'DS-006', lerp[1], '%s.lerp(...) returns without interpolating' % name,
                             note='return %s(field: Color.lerp(field, other.field, t), ...) for every field' % name)
            # DS-005 registration
            if not themes or unresolved:
                continue
            reg = [t for t in themes if name in t['ext']]
            if not reg:
                if bang and not any(name in (t['ext'] or ()) for t in themes):
                    rdf, rpos, _ = bang[0]
                    self.add(rdf, 'DS-005', rpos, 'extension<%s>()! but %s is in no ThemeData extensions' %
                             (name, name), note='register %s in every ThemeData(extensions: [...]) the app uses' % name,
                             severity='high')
                continue
            if any(t['brightness'] in ('param', 'unknown') for t in reg):
                continue
            if not light or not dark or ambiguous and not (light and dark):
                continue
            reg_b = set(t['brightness'] for t in reg)
            for missing_b, pool in (('dark', dark), ('light', light)):
                if missing_b in reg_b:
                    continue
                t = pool[0]
                where = reg[0]
                sev = 'high' if bang else 'medium'
                self.add(t['df'], 'DS-005', t['pos'],
                         '%s ThemeData without %s (registered in the %s theme at %s:%d)' %
                         (missing_b, name, where['brightness'], where['df'].rel, where['df'].line_of(where['pos'])),
                         note=('read with extension<%s>()! at %s:%d, so %s mode crashes' %
                               (name, bang[0][0].rel, bang[0][0].line_of(bang[0][1]), missing_b)) if bang else
                         'extension<%s>() is null in %s mode' % (name, missing_b), severity=sev)

    # -- DS-012 google_fonts runtime fetching
    def check_google_fonts(self):
        if not re.search(r'(?m)^\s+google_fonts\s*:', self.model.pubspec):
            return
        first = None
        for df in self.files:
            if re.search(r'allowRuntimeFetching\s*=\s*false', df.masked):
                return
            mm = re.search(r'(?<![\w$.])GoogleFonts\s*\.\s*(?!config\b)\w+', df.masked)
            if mm and first is None:
                first = (df, mm.start(), mm.group(0))
        if first:
            self.add(first[0], 'DS-012', first[1], '%s(...) with runtime fetching enabled' % first[2],
                     note='add the .ttf files under assets (google_fonts/) and set '
                          'GoogleFonts.config.allowRuntimeFetching = false in main() before runApp')


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
    if any(s in ('state', 'states') for s in segs) or re.search(r'_state\.dart$', base):
        return 'presentation', 'state'
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
    sys.stderr.write('check_design_system.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_design_system.py <project-root> [--json] [--files <list>] '
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


SKIP_ROLES = ('barrel', 'di')


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
    for rel in rels:
        a = arch_files.get(rel)
        if arch_files and a is None:
            continue                     # arch_check skipped it (generated, l10n output, ...)
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if re.search(r'GENERATED CODE - DO NOT MODIFY', df.raw[:400]):
            continue
        if a:
            df.layer, df.role = a.get('layer') or 'other', a.get('role') or 'other'
        else:
            df.layer, df.role = classify_fallback(rel)
        if df.role in SKIP_ROLES:
            continue
        files.append(df)

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(pubspec, rels), 'fallback detection from pubspec and folders'

    model = Model(files, pubspec)
    model.build()
    ck = Checker(files, profile, model)
    if files:
        ck.scan_theme_mode()
        ck.run()
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))

    stats = dict(ck.stats)
    stats['files'] = len(files)
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
    out = ['== DESIGN SYSTEM',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  scanned: %d files, %d themes, %d theme extensions, design tokens: %s' %
           (len(files), stats['themes'], stats['theme_extensions'], 'yes' if stats['design_system'] else 'no'),
           '  scales: spacing %s; radius %s' % (stats['spacing_scale'] or 'none', stats['radius_scale'] or 'none')]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no design system findings')
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
