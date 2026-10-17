#!/usr/bin/env python3
"""check_accessibility.py: find accessibility gaps in a Flutter project (read-only).

Usage:
  python3 -I check_accessibility.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (wrapper widgets and colour constants
             are found across files); only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  A11Y-001 icon-button-without-label        A11Y-007 secret-in-semantics
  A11Y-002 tappable-without-label           A11Y-008 low-contrast-color-scheme
  A11Y-003 image-without-semantics          A11Y-009 exclude-semantics-hides-control
  A11Y-004 text-scaling-disabled            A11Y-010 multiple-autofocus
  A11Y-005 tap-target-too-small             A11Y-011 announcement-in-logic
  A11Y-006 fixed-height-around-text

A "label" is any of: a tooltip, a semanticLabel / semanticsLabel on the icon or image,
an enclosing Semantics(label: ...), Tooltip(...) or MergeSemantics(...) in the same
widget expression, or a project wrapper widget that forwards one of those.

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so.

Suppression (in the analysed code):
  // a11y-ignore: A11Y-003 <reason>        on the reported line, the line above, or inside the call
  // a11y-ignore-file: A11Y-003 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/accessibility@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

RULES = {
    'A11Y-001': ('icon-button-without-label', 'medium',
                 'An icon-only button has no tooltip and no semantic label: TalkBack and VoiceOver announce it as '
                 '"button" and nothing else. Add tooltip: (it is also the long-press hint and the semantic label).'),
    'A11Y-002': ('tappable-without-label', 'medium',
                 'A GestureDetector/InkWell/CupertinoButton wraps only an icon or image and has no label, so a screen '
                 'reader finds an unnamed (or no) control. Wrap it in Semantics(button: true, label: ...) or use '
                 'IconButton(tooltip: ...).'),
    'A11Y-003': ('image-without-semantics', 'low',
                 'An image has neither semanticLabel nor excludeFromSemantics: true. Say what it shows, or mark it '
                 'decorative so the screen reader skips it.'),
    'A11Y-004': ('text-scaling-disabled', 'medium',
                 'The user\'s font-size setting is switched off or capped (TextScaler.noScaling, textScaleFactor: 1, '
                 'a clamp at or below 1.3). Low-vision users then cannot read the text; let it scale and fix the '
                 'layouts that overflow instead.'),
    'A11Y-005': ('tap-target-too-small', 'low',
                 'A control\'s touch target is smaller than 48x48 dp (Android) / 44x44 pt (iOS), so it is hard to hit '
                 'for users with motor impairments.'),
    'A11Y-006': ('fixed-height-around-text', 'low',
                 'Text sits in a box with a fixed small height, so it clips or overflows at large text scale '
                 '(test at 200%). Use a minimum height (ConstrainedBox / minHeight) or padding instead.'),
    'A11Y-007': ('secret-in-semantics', 'high',
                 'A secret (password, PIN, OTP, token, CVV) is put into the semantics tree or announced: screen '
                 'readers speak it aloud and accessibility services can read it. Describe the state, never the value.'),
    'A11Y-008': ('low-contrast-color-scheme', 'medium',
                 'A ColorScheme on-colour pair is below the WCAG AA contrast ratio of 4.5:1 for text, so text and icons '
                 'drawn with it are hard to read.'),
    'A11Y-009': ('exclude-semantics-hides-control', 'medium',
                 'ExcludeSemantics (or excludeFromSemantics: true on a gesture) hides an interactive control from '
                 'screen readers and switch access, so it cannot be reached at all.'),
    'A11Y-010': ('multiple-autofocus', 'low',
                 'More than one widget in the same screen asks for autofocus: only one can win, the order is '
                 'unpredictable, and screen-reader focus jumps unexpectedly.'),
    'A11Y-011': ('announcement-in-logic', 'medium',
                 'A screen-reader announcement is made from a logic or state class. Announcements need localised text '
                 'and a TextDirection, which belong to the view: emit a one-time effect and announce it from a '
                 'listener in the view.'),
}

ANNOUNCE_FIX = {
    'mvn': 'MVN: emit a sealed effect (or a status) from the notifier and call SemanticsService.announce in a '
           'ref.listen in the view, with the localised text',
    'riverpod': 'Riverpod: expose the status from the provider and announce from ref.listen in the widget',
    'mvvm': 'MVVM: let the view model expose the result (Command completed/error) and announce from the view\'s '
            'command listener',
    'bloc': 'Bloc: emit a status in the state and announce from a BlocListener in the view',
    'provider': 'Provider: expose a status on the model and announce from a listener added in the widget State',
    'getx': 'GetX: expose an Rx status and announce from ever()/a worker set up in the view (or onReady with '
            'Get.context only as a last resort)',
    'mvc': 'MVC: let the controller expose a status and announce from the view',
    'setstate': 'setState: announce from the State after the async work completes (check mounted first)',
}
SECRET_ANNOUNCE_FIX = {k: v.replace('with the localised text', 'with a value-free message ("Code sent")')
                       for k, v in ANNOUNCE_FIX.items()}
FIX_BY_PROFILE = {
    'A11Y-011': ANNOUNCE_FIX,
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
SUPPRESS_RE = re.compile(r'a11y-ignore(-file)?\s*:\s*((?:A11Y-\d{3})(?:\s*,\s*A11Y-\d{3})*)\s*(.*)')

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



def toks_of(text):
    out = []
    for w in re.findall(r'[A-Za-z0-9]+', text):
        out += [p.lower() for p in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+', w)]
    return out


# ---------------------------------------------------------------------------------------- widget vocabulary

ICON_BUTTON = r'IconButton(?:\.(?:filled|filledTonal|outlined))?|FloatingActionButton(?:\.(?:small|large))?'
TAPPABLE = r'GestureDetector|InkWell|InkResponse|CupertinoButton(?:\.filled|\.tinted)?|RawMaterialButton'
ICONISH = re.compile(r'^(?:const\s+|new\s+)?(?:Icon|ImageIcon|FaIcon|FaIcons|PhosphorIcon|HugeIcon|Image(?:\.\w+)?|'
                     r'SvgPicture(?:\.\w+)?|CircleAvatar)\s*\(')
IMAGE_CALL = r'Image(?:\.(?:asset|network|file|memory))?|SvgPicture(?:\.(?:asset|network|string|file|memory))?|' \
             r'FadeInImage(?:\.(?:assetNetwork|memoryNetwork))?'
IMAGE_LABEL_ARGS = ('semanticLabel', 'semanticsLabel', 'imageSemanticLabel')
INTERACTIVE = re.compile(r'(?<![\w$.])(IconButton|ElevatedButton|TextButton|OutlinedButton|FilledButton|'
                         r'FloatingActionButton|CupertinoButton|GestureDetector|InkWell|InkResponse|TextField|'
                         r'TextFormField|CupertinoTextField|Checkbox|CheckboxListTile|Switch|SwitchListTile|Slider|'
                         r'Radio|RadioListTile|DropdownButton|PopupMenuButton|ListTile)(?:\.\w+)?\s*(?:<[^()]*?>\s*)?\(')
TAPPABLE_ANY = re.compile(r'^(?:const\s+|new\s+)?(IconButton|ElevatedButton|TextButton|OutlinedButton|FilledButton|'
                          r'FloatingActionButton|CupertinoButton|GestureDetector|InkWell|InkResponse|Checkbox|Radio|'
                          r'Switch|RawMaterialButton|[A-Z]\w*Button)(?:\.\w+)?\s*(?:<[^()]*?>\s*)?\(')
BOX_CALL = r'SizedBox(?:\.square|\.fromSize)?|Container'
PASS_THROUGH = ('Padding', 'Center', 'Align', 'SizedBox', 'Container', 'DecoratedBox', 'Ink', 'ClipOval',
                'ClipRRect', 'Opacity', 'Transform', 'Transform.scale', 'Transform.rotate', 'RotatedBox',
                'AnimatedOpacity', 'FittedBox', 'Hero', 'Material')
TEXTISH = re.compile(r'^(?:const\s+)?(?:Text|Text\.rich|SelectableText|RichText|AutoSizeText)\s*\(')
HANDLER_ARGS = ('onTap', 'onPressed', 'onLongPress', 'onDoubleTap', 'onTapDown', 'onTapUp')
GENERIC_LABEL_ARGS = ('semanticLabel', 'semanticsLabel', 'tooltip', 'label', 'semanticLabelText', 'semanticsValue')
APP_CALL = re.compile(r'(?:Material|Cupertino|Widgets|GetMaterial|GetCupertino|Fluent|Macos|Yaru|Shad)App'
                      r'(?:\.router)?$')

SECRET_WORDS = {'password', 'passwords', 'passwd', 'pwd', 'passcode', 'passphrase', 'pin', 'pincode', 'otp', 'totp',
                'cvv', 'cvc', 'token', 'tokens', 'secret', 'secrets', 'mnemonic', 'apikey', 'credential',
                'credentials'}
SECRET_PAIRS = (('api', 'key'), ('private', 'key'), ('access', 'token'), ('refresh', 'token'), ('seed', 'phrase'),
                ('recovery', 'phrase'), ('one', 'time'))
SECRET_EXCLUDE = {'label', 'labels', 'hint', 'hints', 'title', 'caption', 'message', 'msg', 'error', 'errors',
                  'visible', 'visibility', 'obscure', 'obscured', 'show', 'shown', 'hidden', 'hide', 'length', 'count',
                  'strength', 'policy', 'field', 'focus', 'node', 'enabled', 'required', 'rule', 'rules', 'valid',
                  'invalid', 'is', 'has', 'expiry', 'expires', 'expired', 'timeout', 'type', 'mode', 'status', 'sent',
                  'verified', 'attempts', 'remaining', 'l10n', 'loc', 'localizations', 'strings', 'tr', 'i18n', 'intl',
                  'lang', 'translations', 'description', 'semantics', 'pinned', 'set', 'reset', 'forgot', 'change',
                  'changed', 'new', 'update', 'updated', 'saved', 'copied', 'empty', 'icon', 'button', 'screen',
                  'page', 'route', 'state', 'enum', 'kind', 'step'}
L10N_RECV = re.compile(r'(?:^|\.)(?:l10n|loc|localizations|AppLocalizations|S|strings|t|tr|i18n|intl|lang|'
                       r'translations|context\s*\.\s*l10n|LocaleKeys|Strings|Texts|AppStrings|I18n)\s*(?:\.|$|\()',
                       re.I)

ON_PAIRS = (('primary', 'onPrimary'), ('secondary', 'onSecondary'), ('tertiary', 'onTertiary'),
            ('error', 'onError'), ('surface', 'onSurface'), ('background', 'onBackground'),
            ('primaryContainer', 'onPrimaryContainer'), ('secondaryContainer', 'onSecondaryContainer'),
            ('tertiaryContainer', 'onTertiaryContainer'), ('errorContainer', 'onErrorContainer'),
            ('surfaceVariant', 'onSurfaceVariant'), ('inverseSurface', 'onInverseSurface'))
MATERIAL = {'white': 'FFFFFFFF', 'black': 'FF000000', 'red': 'FFF44336', 'pink': 'FFE91E63', 'purple': 'FF9C27B0',
            'deepPurple': 'FF673AB7', 'indigo': 'FF3F51B5', 'blue': 'FF2196F3', 'lightBlue': 'FF03A9F4',
            'cyan': 'FF00BCD4', 'teal': 'FF009688', 'green': 'FF4CAF50', 'lightGreen': 'FF8BC34A',
            'lime': 'FFCDDC39', 'yellow': 'FFFFEB3B', 'amber': 'FFFFC107', 'orange': 'FFFF9800',
            'deepOrange': 'FFFF5722', 'brown': 'FF795548', 'grey': 'FF9E9E9E', 'blueGrey': 'FF607D8B'}
COLOR_LIT = r'(?:const\s+)?Color\s*\(\s*0x([0-9A-Fa-f]{8})\s*\)'
COLOR_DEF = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*=\s*(?:const\s+)?(?:Color\s*\(\s*0x([0-9A-Fa-f]{8})\s*\)|'
                       r'Color\s*\.\s*fromARGB\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)|'
                       r'Colors\s*\.\s*(\w+)\s*[;,)])')


def num(text):
    t = (text or '').strip()
    t = re.sub(r'^const\s+', '', t)
    if re.match(r'^-?\d+(?:\.\d+)?$', t):
        return float(t)
    return None


def luminance(hex8):
    out = []
    for k in (2, 4, 6):
        c = int(hex8[k:k + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, files, profile):
        self.files = files
        self.profile = profile
        self.findings = []
        self.suppressed = []
        self.stats = {'icon_buttons': 0, 'tappables': 0, 'images': 0, 'semantics_widgets': 0, 'color_schemes': 0,
                      'wrappers': []}
        self.label_wrappers = {}      # class -> forwarded tooltip/label field
        self.scale_wrappers = {}      # class -> (field, default)
        self.colors = {}
        self._seen = set()

    # -- reporting
    def add(self, df, rid, pos, evidence, note='', severity=None, span=None):
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
            lines = [ln, ln - 1]
            if span:
                lines += list(range(df.line_of(span[0]), df.line_of(span[1]) + 1))
            for l in lines:
                if rid in df.suppress_line.get(l, {}):
                    reason = df.suppress_line[l][rid]
                    break
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': df.rel, 'line': ln, 'reason': reason})
            return
        prof = FIX_BY_PROFILE.get(rid, {}).get(self.profile, '')
        if prof:
            note = (note + '; ' if note else '') + prof
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    # -- tree helpers (the widget tree is the call-paren nesting of one expression)
    def _prep(self, df):
        if hasattr(df, 'popens'):
            return
        df.popens = sorted(k for k, v in df.parens.items() if df.masked[k] == '(')
        df.pparent = {}
        stack = []
        for o in df.popens:
            while stack and df.parens[stack[-1]] < o:
                stack.pop()
            df.pparent[o] = stack[-1] if stack else None
            stack.append(o)

    @staticmethod
    def call_name(df, po):
        mm = re.search(r'([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*(?:<[^()<>]*(?:<[^()<>]*>)?[^()<>]*>)?\s*$',
                       df.masked[max(0, po - 120):po])
        return re.sub(r'\s+', '', mm.group(1)) if mm else ''

    def ancestors(self, df, pos):
        """(name, open_paren) of every call whose argument list contains pos, innermost first."""
        self._prep(df)
        k = bisect.bisect_left(df.popens, pos) - 1
        o = df.popens[k] if k >= 0 else None
        while o is not None and not (o < pos < df.parens.get(o, -1)):
            o = df.pparent.get(o)
        while o is not None:
            yield self.call_name(df, o), o
            o = df.pparent.get(o)

    def arg_containing(self, df, po, pos):
        args, _ = arg_map(df, po)
        for k, (s, e) in args.items():
            if s <= pos <= e:
                return k
        return None

    def calls(self, df, pattern):
        rx = re.compile(r'(?<![\w$.])(?:const\s+|new\s+)?(' + pattern + r')\s*(?:<[^()]*?>\s*)?\(')
        for mm in rx.finditer(df.masked):
            po = mm.end() - 1
            before = df.masked[max(0, mm.start() - 16):mm.start()]
            if re.search(r'\b(?:class|extends|implements|with|new|factory)\s*$', before) and 'new' not in before:
                continue
            args, pc = arg_map(df, po)
            if pc == po:
                continue
            if re.search(r'(?<![\w$])(?:this|super)\s*\.', df.masked[po:pc]):
                continue                    # a constructor declaration
            if self._is_decl(df, mm.start()):
                continue
            yield mm.group(1), mm.start(), po, pc, args

    @staticmethod
    def _is_decl(df, start):
        c = df.enclosing_class(start)
        if not c:
            return False
        name_at = re.match(r'\s*([A-Za-z_$][\w$.]*)', df.masked[start:start + 80])
        nm = name_at.group(1) if name_at else ''
        if nm.split('.')[0] != c[0]:
            return False
        before = df.masked[max(0, start - 30):start]
        return bool(re.search(r'(?:^|[;{}\n])\s*(?:const\s+|factory\s+)?$', before)) and \
            not re.search(r'\b(?:return|=>|=|:|\(|,)\s*(?:const\s+)?$', before)

    def val(self, df, args, k):
        if k not in args:
            return None
        return df.code[args[k][0]:args[k][1]].strip()

    def has_label_arg(self, df, args, keys=GENERIC_LABEL_ARGS):
        for k in keys:
            v = self.val(df, args, k)
            if v is not None and v != 'null':
                return True
        return False

    def labelled_by_ancestor(self, df, pos, depth=0):
        """True if an enclosing call labels pos: Semantics(label:), Tooltip, MergeSemantics, or any widget passing a
        tooltip/semanticLabel/label (NavigationDestination, ElevatedButton.icon, project buttons...)."""
        for name, po in self.ancestors(df, pos):
            base = name.split('.')[-1] if name.startswith(('const', 'new')) else name
            if base in ('Tooltip', 'MergeSemantics', 'ExcludeSemantics', 'BlockSemantics'):
                return True
            if base in ('InputDecoration', 'InputDecoration.collapsed'):
                continue                # the field's label does not name its suffix/prefix buttons
            args, _ = arg_map(df, po)
            if base == 'Semantics':
                if self.has_label_arg(df, args, ('label', 'attributedLabel', 'value')) or \
                        self.val(df, args, 'excludeSemantics') == 'true':
                    return True
                continue
            if self.has_label_arg(df, args):
                if self.arg_containing(df, po, pos) in GENERIC_LABEL_ARGS:
                    continue            # pos is the label itself (label: Row(Icon, Text))
                return True
        if depth < 2:
            return self._labelled_through_hop(df, pos, depth)
        return False

    def _labelled_through_hop(self, df, pos, depth):
        # one hop: final btn = IconButton(...); ... Semantics(label: x, child: btn)
        m = df.masked
        f = df.enclosing_func(pos)
        head = m[max(0, pos - 60):pos]
        vm = re.search(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*=\s*(?:const\s+)?$', head)
        if vm and f:
            v = vm.group(1)
            for um in re.finditer(r'(?<![\w$.])%s\b(?!\s*=[^=])' % re.escape(v), m[f[2]:f[3]]):
                p = f[2] + um.start()
                if p > pos and self.labelled_by_ancestor(df, p, depth + 1):
                    return True
        # helper method: Widget _buildClose() => IconButton(...); build: Semantics(label: x, child: _buildClose())
        if f and f[0] not in ('build',) and not re.match(r'^[A-Z]', f[0]):
            for cm in re.finditer(r'(?<![\w$.])%s\s*\(' % re.escape(f[0]), m):
                if f[1] <= cm.start() <= f[3]:
                    continue
                if self.labelled_by_ancestor(df, cm.start(), depth + 1):
                    return True
        return False

    def excluded_by_ancestor(self, df, pos):
        for name, po in self.ancestors(df, pos):
            if name in ('ExcludeSemantics', 'BlockSemantics'):
                args, _ = arg_map(df, po)
                if self.val(df, args, 'excluding') != 'false':
                    return True
            if name == 'Semantics':
                args, _ = arg_map(df, po)
                if self.val(df, args, 'excludeSemantics') == 'true':
                    return True
            args, _ = arg_map(df, po)
            if self.val(df, args, 'excludeFromSemantics') == 'true' and not name.startswith(('GestureDetector',
                                                                                              'RawGesture')):
                return True
        return False

    def unwrap_child(self, df, args, levels=3):
        """Text of the single child of a widget, looking through Padding/Center/SizedBox-like wrappers."""
        cur = args
        for _ in range(levels + 1):
            if 'child' not in cur:
                return None, None
            s, e = cur['child']
            txt = df.code[s:e].strip()
            mm = re.match(r'(?:const\s+|new\s+)?([A-Za-z_][\w.]*)\s*(?:<[^()]*?>\s*)?\(', txt)
            if not mm or mm.group(1) not in PASS_THROUGH:
                off = s + (len(df.code[s:e]) - len(df.code[s:e].lstrip()))
                return txt, off
            po = s + (len(df.code[s:e]) - len(df.code[s:e].lstrip())) + mm.end() - 1
            nxt, _ = arg_map(df, po)
            if 'children' in nxt:
                return None, None
            cur = nxt
        return None, None

    # -- wrappers found across files
    def find_wrappers(self):
        for df in self.files:
            self._prep(df)
            state_of = {}
            for name, o, c, header in df.classes:
                sm = re.search(r'\bextends\s+(?:State|ConsumerState)\s*<\s*(\w+)\s*>', header)
                if sm:
                    state_of[sm.group(1)] = (o, c)
            for name, o, c, header in df.classes:
                if not re.search(r'\bextends\s+\w*(?:Widget|StatelessWidget|StatefulWidget)\b', header):
                    continue
                body = df.masked[o:c]
                spans = [(o, c)] + ([state_of[name]] if name in state_of else [])
                for s, e in spans:
                    seg = df.code[s:e]
                    for tm in re.finditer(r'\b(?:tooltip|semanticLabel|semanticsLabel)\s*:\s*(?:widget\s*\.\s*)?'
                                          r'([a-z_]\w*)\s*[,)]', seg):
                        fld = tm.group(1)
                        if re.search(r'\bfinal\s+String\?\s+%s\s*;' % re.escape(fld), body) and \
                                not re.search(r'\brequired\s+this\s*\.\s*%s\b' % re.escape(fld), body) and \
                                re.search(r'\bthis\s*\.\s*%s\b' % re.escape(fld), body) and \
                                re.search(r'(?<![\w$.])(?:%s)\s*\(' % ICON_BUTTON, seg):
                            self.label_wrappers[name] = fld
                    for tm in re.finditer(r'TextScaler\s*\.\s*linear\s*\(\s*(?:widget\s*\.\s*)?([a-z_]\w*)\s*\)', seg):
                        fld = tm.group(1)
                        dm = re.search(r'\bthis\s*\.\s*%s\s*=\s*([\d.]+)' % re.escape(fld), body)
                        if dm and num(dm.group(1)) is not None and num(dm.group(1)) <= 1.3:
                            self.scale_wrappers[name] = (fld, dm.group(1))
            for mm in COLOR_DEF.finditer(df.code):
                nm = mm.group(1)
                if mm.group(2):
                    hx = mm.group(2).upper()
                elif mm.group(3):
                    hx = '%02X%02X%02X%02X' % tuple(int(mm.group(i)) & 255 for i in (3, 4, 5, 6))
                else:
                    hx = MATERIAL.get(mm.group(7))
                if not hx:
                    continue
                if nm in self.colors and self.colors[nm] != hx:
                    self.colors[nm] = None              # ambiguous name: never guess
                else:
                    self.colors.setdefault(nm, hx)
        self.stats['wrappers'] = sorted(set(self.label_wrappers) | set(self.scale_wrappers))

    def resolve_color(self, expr):
        e = re.sub(r'\s+', '', expr or '')
        e = re.sub(r'^const', '', e)
        mm = re.match(r'^Color\(0x([0-9A-Fa-f]{8})\)$', e)
        if mm:
            return mm.group(1).upper()
        mm = re.match(r'^Colors\.(\w+)$', e)
        if mm:
            return MATERIAL.get(mm.group(1))
        mm = re.match(r'^(?:[A-Za-z_$][\w$]*\.)*([A-Za-z_$][\w$]*)$', e)
        if mm:
            return self.colors.get(mm.group(1))
        return None

    def run(self):
        self.find_wrappers()
        for df in self.files:
            self._prep(df)
            self.stats['semantics_widgets'] += len(re.findall(r'(?<![\w$.])(?:Semantics|MergeSemantics|'
                                                              r'ExcludeSemantics)\s*\(', df.masked))
            self.check_icon_buttons(df)
            self.check_tappables(df)
            self.check_images(df)
            self.check_text_scale(df)
            self.check_tap_targets(df)
            self.check_fixed_height(df)
            self.check_secret_semantics(df)
            self.check_contrast(df)
            self.check_exclude(df)
            self.check_autofocus(df)
            self.check_logic_announce(df)

    # -- A11Y-001
    def check_icon_buttons(self, df):
        for name, st, po, pc, args in self.calls(df, ICON_BUTTON):
            if name.startswith('FloatingActionButton'):
                child, _ = self.unwrap_child(df, args, 0)
                if not child or not ICONISH.match(child):
                    continue
            self.stats['icon_buttons'] += 1
            tip = self.val(df, args, 'tooltip')
            if tip is not None and tip != 'null':
                continue
            icon = self.val(df, args, 'icon') if 'icon' in args else self.val(df, args, 'child')
            if icon and re.search(r'\bsemanticLabel\s*:\s*(?!null\b)', icon):
                continue
            fwd = re.match(r'^(?:widget\s*\.\s*)?([a-z_]\w*)$', icon or '')
            if fwd and self._forwarded_icon_labelled(df, st, fwd.group(1)):
                continue
            if self.labelled_by_ancestor(df, st):
                continue
            ev = df.snippet(st, min(pc + 1, st + 110))
            self.add(df, 'A11Y-001', st, ev, note='add tooltip: (from l10n); it becomes the semantic label',
                     span=(st, pc))
        for wname, fld in sorted(self.label_wrappers.items()):
            for name, st, po, pc, args in self.calls(df, re.escape(wname)):
                if name != wname or fld in args:
                    continue
                c = df.enclosing_class(st)
                if c and c[0] in (wname, '_%sState' % wname, wname + 'State'):
                    continue
                if self.labelled_by_ancestor(df, st):
                    continue
                self.add(df, 'A11Y-001', st, df.snippet(st, min(pc + 1, st + 110)),
                         note='%s forwards %s: to its IconButton; pass %s: here' % (wname, fld, fld), span=(st, pc))

    def _forwarded_icon_labelled(self, df, pos, fld):
        """The IconButton's icon is a constructor parameter: judge the call sites instead."""
        c = df.enclosing_class(pos)
        if not c:
            return False
        wname = re.sub(r'State$', '', c[0]).lstrip('_') if c[0].endswith('State') else c[0]
        if c[0].endswith('State'):
            sm = re.search(r'\bextends\s+(?:State|ConsumerState)\s*<\s*(\w+)\s*>', c[3])
            wname = sm.group(1) if sm else wname
        sites = 0
        for other in self.files:
            for name, st, po, pc, args in self.calls(other, re.escape(wname)):
                if name != wname:
                    continue
                v = self.val(other, args, fld)
                if v is None:
                    continue
                sites += 1
                if not re.search(r'\bsemanticLabel\s*:\s*(?!null\b)', v) and \
                        not self.labelled_by_ancestor(other, st):
                    return False
        return sites > 0

    # -- A11Y-002
    def check_tappables(self, df):
        self._tap_children = getattr(df, '_tap_children', set())
        for name, st, po, pc, args in self.calls(df, TAPPABLE):
            if not any(self.val(df, args, h) not in (None, 'null') for h in HANDLER_ARGS):
                continue
            self.stats['tappables'] += 1
            if self.val(df, args, 'excludeFromSemantics') == 'true':
                continue                                   # A11Y-009 judges this one
            child, off = self.unwrap_child(df, args)
            if not child or not ICONISH.match(child):
                continue
            cpo = df.masked.find('(', off)
            cargs, _ = arg_map(df, cpo) if cpo >= 0 else ({}, None)
            df._tap_children = getattr(df, '_tap_children', set()) | {off}
            if self.has_label_arg(df, cargs, IMAGE_LABEL_ARGS):
                continue
            if self.labelled_by_ancestor(df, st) or self.excluded_by_ancestor(df, st):
                continue
            self.add(df, 'A11Y-002', st, '%s(... child: %s)' % (name, ' '.join(child.split())[:60]),
                     note='wrap in Semantics(button: true, label: ...) or use IconButton(tooltip: ...)',
                     span=(st, pc))

    # -- A11Y-003
    def check_images(self, df):
        taps = getattr(df, '_tap_children', set())
        for name, st, po, pc, args in self.calls(df, IMAGE_CALL):
            if name in ('Image', 'SvgPicture', 'FadeInImage') and not args:
                continue
            self.stats['images'] += 1
            if self.has_label_arg(df, args, IMAGE_LABEL_ARGS) or 'excludeFromSemantics' in args and \
                    self.val(df, args, 'excludeFromSemantics') != 'false':
                continue
            if st in taps or any(abs(st - t) < 8 for t in taps):
                continue                                   # its tappable parent is A11Y-002
            if self.labelled_by_ancestor(df, st) or self.excluded_by_ancestor(df, st):
                continue
            self.add(df, 'A11Y-003', st, df.snippet(st, min(pc + 1, st + 100)),
                     note='add semanticLabel: (what it shows) or excludeFromSemantics: true if decorative',
                     span=(st, pc))

    # -- A11Y-004
    def _app_wide(self, df, pos):
        if re.search(r'(^|/)main[^/]*\.dart$', df.rel):
            return True
        for name, po in self.ancestors(df, pos):
            if APP_CALL.search(name) and self.arg_containing(df, po, pos) == 'builder':
                return True
            if name.startswith('MediaQuery'):
                args, pc = arg_map(df, po)
                if re.search(r'(?<![\w$.])\w*App(?:\.router)?\s*\(', df.masked[po:pc]):
                    return True
        return False

    def check_text_scale(self, df):
        m, code = df.masked, df.code
        hits = []
        for mm in re.finditer(r'TextScaler\s*\.\s*noScaling\b|MediaQuery\s*\.\s*withNoTextScaling\s*\(', m):
            hits.append((mm.start(), 'no scaling', None))
        for mm in re.finditer(r'\btextScaleFactor\s*:\s*([\d.]+)\b', code):
            v = num(mm.group(1))
            if v is not None and v <= 1.3 and m[mm.start()] != ' ':
                hits.append((mm.start(), 'textScaleFactor fixed at %s' % mm.group(1), v))
        for mm in re.finditer(r'TextScaler\s*\.\s*linear\s*\(\s*([\d.]+)\s*\)', code):
            v = num(mm.group(1))
            if v is not None and v <= 1.3 and m[mm.start()] != ' ':
                hits.append((mm.start(), 'TextScaler.linear(%s)' % mm.group(1), v))
        for mm in re.finditer(r'\bmaxScaleFactor\s*:\s*([\d.]+)', code):
            v = num(mm.group(1))
            if v is not None and v < 2.0 and m[mm.start()] != ' ':
                hits.append((mm.start(), 'clamped to maxScaleFactor %s' % mm.group(1), v))
        for mm in re.finditer(r'\b(?:textScaleFactor|textScaleFactorOf\s*\([^()]*\))\s*\.\s*clamp\s*\(\s*[\d.]+\s*,'
                              r'\s*([\d.]+)\s*\)', code):
            v = num(mm.group(1))
            if v is not None and v < 2.0 and m[mm.start()] != ' ':
                hits.append((mm.start(), 'textScaleFactor clamped to %s' % mm.group(1), v))
        for pos, what, v in hits:
            c = df.enclosing_class(pos)
            if c and c[0] in self.scale_wrappers:
                continue                                   # reported at the wrapper's call sites
            wide = self._app_wide(df, pos)
            if v is not None and v > 1.3:
                sev = 'low'
                note = '%s: still below the 200%% that WCAG 1.4.4 asks for' % what
            else:
                sev = 'high' if wide else 'medium'
                note = '%s%s' % (what, ' for the whole app' if wide else '')
            self.add(df, 'A11Y-004', pos, df.lines[df.line_of(pos) - 1].strip()[:110], note=note, severity=sev)
        for wname, (fld, dflt) in sorted(self.scale_wrappers.items()):
            for name, st, po, pc, args in self.calls(df, re.escape(wname)):
                if name != wname or fld in args:
                    continue
                self.add(df, 'A11Y-004', st, df.snippet(st, min(pc + 1, st + 90)),
                         note='%s defaults %s to %s, which fixes the text size' % (wname, fld, dflt),
                         severity='high' if self._app_wide(df, st) else 'medium', span=(st, pc))

    # -- A11Y-005
    def check_tap_targets(self, df):
        m = df.masked
        for mm in re.finditer(r'MaterialTapTargetSize\s*\.\s*shrinkWrap\b', m):
            self.add(df, 'A11Y-005', mm.start(), df.lines[df.line_of(mm.start()) - 1].strip()[:110],
                     note='shrinkWrap drops the 48 dp padding; keep MaterialTapTargetSize.padded', severity='low')
        for name, st, po, pc, args in self.calls(df, BOX_CALL):
            dims = []
            if name == 'SizedBox.square':
                d = num(self.val(df, args, 'dimension'))
                dims = [d, d] if d is not None else []
            elif name == 'SizedBox.fromSize':
                sm = re.search(r'Size\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)', self.val(df, args, 'size') or '')
                if sm:
                    dims = [float(sm.group(1)), float(sm.group(2))]
            else:
                for k in ('width', 'height'):
                    d = num(self.val(df, args, k))
                    if d is not None:
                        dims.append(d)
            dims = [d for d in dims if d > 0]
            if not dims:
                continue
            small = min(dims)
            if small >= 48:
                continue
            child, off = self.unwrap_child(df, args, 1)
            if not child:
                continue
            tm = TAPPABLE_ANY.match(child)
            if not tm:
                continue
            cpo = df.masked.find('(', off)
            cargs, _ = arg_map(df, cpo)
            if not any(self.val(df, cargs, h) not in (None, 'null') for h in HANDLER_ARGS + ('onChanged',)):
                continue
            sev = 'medium' if small < 44 else 'low'
            self.add(df, 'A11Y-005', st, '%s(%s, child: %s(...))' % (name, ', '.join(
                '%s: %s' % (k, self.val(df, args, k)) for k in ('width', 'height', 'dimension', 'size') if k in args),
                tm.group(1)), note='%s is %g dp; keep at least 48x48 dp (44x44 pt on iOS) of hit area' %
                                   (tm.group(1), small), severity=sev, span=(st, pc))

    # -- A11Y-006
    def check_fixed_height(self, df):
        for name, st, po, pc, args in self.calls(df, 'SizedBox|Container'):
            h = num(self.val(df, args, 'height'))
            if h is None or h <= 0 or h >= 40:
                continue
            child, _ = self.unwrap_child(df, args, 1)
            if not child or not TEXTISH.match(child):
                continue
            self.add(df, 'A11Y-006', st, '%s(height: %s, child: %s...)' % (name, self.val(df, args, 'height'),
                                                                          ' '.join(child.split())[:40]),
                     note='use ConstrainedBox(constraints: BoxConstraints(minHeight: %g)) or padding' % h,
                     span=(st, pc))

    # -- A11Y-007
    def _secret_expr(self, df, s, e):
        code, m = df.code, df.masked
        parts = [m[s:e]]
        for im in re.finditer(r'\$\{([^{}]*)\}|\$([A-Za-z_][\w]*)', code[s:e]):
            parts.append(im.group(1) or im.group(2))
        text = ' '.join(parts)
        for cm in re.finditer(r'[A-Za-z_$][\w$]*(?:\s*[?!]?\s*\.\s*[A-Za-z_$][\w$]*)*', text):
            chain = re.sub(r'\s+', '', cm.group(0))
            if L10N_RECV.search(chain) or re.search(r'\.(?:length|isEmpty|isNotEmpty|hashCode)$', chain):
                continue
            after = text[cm.end():cm.end() + 3]
            if after.lstrip().startswith('('):
                continue                                    # a call: describePassword(), not a value
            toks = toks_of(chain.replace('.', ' '))
            ts = set(toks)
            if ts & SECRET_EXCLUDE:
                continue
            joined = ' '.join(toks)
            if ts & SECRET_WORDS or any(' %s %s ' % p in ' %s ' % joined for p in SECRET_PAIRS):
                return chain
        return None

    def check_secret_semantics(self, df):
        for name, st, po, pc, args in self.calls(df, 'Semantics'):
            for k in ('label', 'value', 'hint', 'increasedValue', 'decreasedValue', 'tooltip'):
                if k in args:
                    hit = self._secret_expr(df, *args[k])
                    if hit:
                        self.add(df, 'A11Y-007', args[k][0], 'Semantics(%s: %s)' % (k, ' '.join(
                            df.code[args[k][0]:args[k][1]].split())[:60]), note='`%s` reaches the semantics tree' % hit,
                            span=(st, pc))
        for mm in re.finditer(r'\b(?:semanticsLabel|semanticLabel|semanticsValue)\s*:', df.masked):
            s = mm.end()
            e = expr_end(df.masked, s)
            hit = self._secret_expr(df, s, e)
            if hit:
                self.add(df, 'A11Y-007', mm.start(), df.snippet(mm.start(), e),
                         note='`%s` becomes the semantic label' % hit)
        for mm in re.finditer(r'\b(?:SemanticsService\s*\.\s*(?:announce|sendAnnouncement)|sendAnnouncement)\s*\(',
                              df.masked):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            args, _ = split_args(df, po)
            if not args:
                continue
            hit = self._secret_expr(df, args[0][1], args[0][2])
            if hit:
                fix = SECRET_ANNOUNCE_FIX.get(self.profile, '')
                self.add(df, 'A11Y-007', mm.start(), df.snippet(mm.start(), pc + 1),
                         note='`%s` is spoken aloud' % hit + ('; ' + fix if fix else ''), span=(mm.start(), pc))

    # -- A11Y-008
    def check_contrast(self, df):
        for name, st, po, pc, args in self.calls(df, r'ColorScheme(?:\.(?:light|dark|fromSeed|highContrastLight|'
                                                     r'highContrastDark))?'):
            self.stats['color_schemes'] += 1
            for bg, fg in ON_PAIRS:
                if bg not in args or fg not in args:
                    continue
                b = self.resolve_color(self.val(df, args, bg))
                f = self.resolve_color(self.val(df, args, fg))
                if not b or not f or b[:2] != 'FF' or f[:2] != 'FF':
                    continue                                # unresolved or translucent: never guess
                r = contrast(b, f)
                if r >= 4.5:
                    continue
                self.add(df, 'A11Y-008', args[fg][0], '%s: %s / %s: %s' % (
                    bg, self.val(df, args, bg), fg, self.val(df, args, fg)),
                    note='contrast %.2f:1 (#%s on #%s), needs 4.5:1 for text%s' % (
                        r, f[2:], b[2:], '' if r >= 3 else ' and 3:1 for icons and large text'))

    # -- A11Y-009
    def check_exclude(self, df):
        m = df.masked
        for name, st, po, pc, args in self.calls(df, 'ExcludeSemantics'):
            if self.val(df, args, 'excluding') not in (None, 'true'):
                continue                                    # excluding: !isFocused hides it only some of the time
            for im in INTERACTIVE.finditer(m, po, pc):
                ipo = im.end() - 1
                iargs, ipc = arg_map(df, ipo)
                handlers = [self.val(df, iargs, h) for h in HANDLER_ARGS + ('onChanged',)]
                if im.group(1) not in ('TextField', 'TextFormField', 'CupertinoTextField') and \
                        not any(h not in (None, 'null') for h in handlers):
                    continue
                if self._actionable_ancestor(df, st):
                    break
                self.add(df, 'A11Y-009', st, 'ExcludeSemantics(... %s(...))' % im.group(1),
                         note='%s at line %d is hidden from screen readers' % (im.group(1), df.line_of(im.start())),
                         span=(st, pc))
                break
        for name, st, po, pc, args in self.calls(df, 'GestureDetector|RawGestureDetector|InkWell'):
            if self.val(df, args, 'excludeFromSemantics') != 'true':
                continue
            if self.val(df, args, 'onTap') in (None, 'null'):
                continue
            if self._actionable_ancestor(df, st):
                continue
            child = self.val(df, args, 'child') or ''
            if re.search(r'(?<![\w$.])Semantics\s*\([^;]*\b(?:onTap|button)\s*:', child):
                continue
            self.add(df, 'A11Y-009', st, '%s(excludeFromSemantics: true, onTap: ...)' % name,
                     note='expose the action with Semantics(button: true, label: ..., onTap: ...)', span=(st, pc))

    def _actionable_ancestor(self, df, pos):
        for name, po in self.ancestors(df, pos):
            if name == 'Semantics':
                args, _ = arg_map(df, po)
                if any(self.val(df, args, k) not in (None, 'null', 'false') for k in ('onTap', 'button', 'onLongPress',
                                                                                      'onIncrease', 'link')):
                    return True
            if re.search(r'Button(?:\.\w+)?$', name) or name in ('Tooltip', 'ListTile', 'InkWell', 'GestureDetector'):
                args, _ = arg_map(df, po)
                if any(self.val(df, args, h) not in (None, 'null') for h in HANDLER_ARGS):
                    return True
        return False

    # -- A11Y-010
    def check_autofocus(self, df):
        m = df.masked
        for name, o, c, header in df.classes:
            inner = [cc for cc in df.classes if o < cc[1] < c]
            hits = [a.start() for a in re.finditer(r'\bautofocus\s*:\s*true\b', m[o:c])]
            hits = [o + h for h in hits if not any(cc[1] < o + h < cc[2] for cc in inner)]
            if len(hits) < 2:
                continue
            first = hits[0]
            for h in hits[1:]:
                if self._alternatives(df, first, h):
                    continue                                 # alternative branches: only one is built
                self.add(df, 'A11Y-010', h, df.lines[df.line_of(h) - 1].strip()[:110],
                         note='also autofocus at line %d in %s' % (df.line_of(first), name))

    @staticmethod
    def _alternatives(df, a, b):
        """True when a and b sit in different branches of a conditional (?:, if/else, switch, separate closures)."""
        m = df.masked
        pairs = dict(df.parens)
        pairs.update(df.braces)
        brk = match_pairs(m, '[', ']') if not hasattr(df, '_brk') else df._brk
        df._brk = brk
        pairs.update(brk)
        best = None
        for o, c in pairs.items():
            if m[o] in '([{' and o < a and c > b and (best is None or o > best):
                best = o
        lo = best + 1 if best is not None else 0
        top, i, mark = [], lo, None
        while i < b:
            if mark is None and i >= a:
                mark = len(top)
            ch = m[i]
            if ch in '([{' and i in pairs and pairs[i] > i:
                inner_a = i < a < pairs[i]
                if inner_a or pairs[i] >= b:
                    top.append(ch)
                    i += 1
                    continue
                top.append(ch + m[pairs[i]])
                i = pairs[i] + 1
                continue
            top.append(ch)
            i += 1
        flat = ''.join(top[mark or 0:])
        # a ternary ':' follows a closed expression; a named argument's ':' follows an identifier
        return bool(re.search(r'\belse\b|\bcase\b|\bdefault\b|=>|[)\]}\'"]\s*:(?!:)|\?(?![?.\[])', flat))

    # -- A11Y-011
    def check_logic_announce(self, df):
        if df.role not in ('logic', 'state'):
            return
        for mm in re.finditer(r'\bSemanticsService\s*\.\s*(?:announce|sendAnnouncement)\s*\(', df.masked):
            pc = df.parens.get(mm.end() - 1, mm.end())
            self.add(df, 'A11Y-011', mm.start(), df.snippet(mm.start(), pc + 1),
                     note='in a %s file' % df.role)


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
    sys.stderr.write('check_accessibility.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_accessibility.py <project-root> [--json] [--files <list>] '
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
    for rel in rels:
        a = arch_files.get(rel)
        if a and a.get('role') in ('barrel', 'di'):
            continue
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
    out = ['== ACCESSIBILITY',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  scanned: %d files, %d icon buttons, %d tappables, %d images, %d semantics widgets, %d color schemes'
           % (len(files), stats['icon_buttons'], stats['tappables'], stats['images'], stats['semantics_widgets'],
              stats['color_schemes'])]
    if stats['wrappers']:
        out.append('  wrappers: %s' % ', '.join(stats['wrappers'][:8]) +
                   (' ... %d more' % (len(stats['wrappers']) - 8) if len(stats['wrappers']) > 8 else ''))
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no accessibility findings')
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
