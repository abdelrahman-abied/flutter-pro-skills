#!/usr/bin/env python3
"""check_i18n.py: find localization, RTL and formatting bugs in a Flutter/Dart project (read-only).

Usage:
  python3 -I check_i18n.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (catalog parity needs every locale);
             only findings in the listed files (Dart or catalog files) are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

What it reads:
  - message catalogs: gen-l10n ARB files (l10n.yaml, default lib/l10n/app_en.arb),
    intl_utils ARB files (lib/l10n/intl_*.arb), easy_localization JSON
    (assets/translations/<locale>.json) and slang JSON (*.i18n.json)
  - lib/**/*.dart, skipping generated code and the gen-l10n output

Layers and roles come from ../flutter-architecture/scripts/arch_check.py --json
("files" array) when that sibling skill is installed; otherwise a path-based
fallback is used and the output says so.

Suppression:
  // i18n-ignore: I18N-010 <reason>        on the reported line or the line above
  // i18n-ignore-file: I18N-012 <reason>   anywhere in the Dart file
  "@@x-i18n-ignore": "I18N-001 <reason>"  top-level key in an ARB/JSON catalog
                                           (gen-l10n ignores keys starting with @)

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/i18n@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

RULES = {
    'I18N-001': ('catalog-missing-keys', 'medium',
                 "A locale's catalog lacks keys that the template defines. Users of that locale see the "
                 "template language for those strings (gen-l10n falls back silently)."),
    'I18N-002': ('placeholder-mismatch', 'medium',
                 "A translation's placeholders differ from the template: a dropped placeholder loses the value, "
                 "an unknown one (often a translated or misspelled name) changes the generated method signature."),
    'I18N-003': ('plural-forms-missing', 'medium',
                 "A plural message lacks CLDR categories this locale needs (Arabic: one, two, few, many). "
                 "intl falls back to `other`, which is grammatically wrong for 3-10 and 11-99 in Arabic."),
    'I18N-004': ('secret-in-catalog', 'high',
                 "A catalog contains something that looks like a credential or token. Catalogs ship inside the app "
                 "binary and go to translators and translation platforms; keep secrets in the data layer's config."),
    'I18N-005': ('synthetic-package', 'medium',
                 "Uses the removed synthetic `package:flutter_gen` (or `synthetic-package: true`). Current Flutter "
                 "generates l10n into the source tree; import the generated file from lib/ instead."),
    'I18N-006': ('catalog-missing-descriptions', 'info',
                 "Template messages without an `@key.description`. Translators work without context, which is how "
                 "\"Book\" (noun) becomes \"Book\" (verb) in Arabic."),
    'I18N-010': ('hardcoded-ui-string', 'low',
                 "User-facing string literal in a localised app (the checker counterpart of UI-l10n). Move it to the "
                 "catalog and read it in the view."),
    'I18N-011': ('translation-concatenation', 'medium',
                 "A translated string is concatenated or interpolated with other text. Word order, spacing and "
                 "punctuation differ per language (and per direction); use one message with placeholders."),
    'I18N-012': ('physical-direction-geometry', 'medium',
                 "Left/right geometry in an app that ships an RTL locale (the checker counterpart of UI-rtl). Use "
                 "EdgeInsetsDirectional, AlignmentDirectional, PositionedDirectional, TextAlign.start/end."),
    'I18N-013': ('non-mirroring-directional-icon', 'medium',
                 "A left/right icon that Flutter does NOT mirror in RTL (its IconData has no matchTextDirection). "
                 "Use a mirroring icon (Icons.chevron_left/right, arrow_back/forward, CupertinoIcons.back/forward) "
                 "or pick by Directionality."),
    'I18N-014': ('format-without-locale', 'medium',
                 "DateFormat/NumberFormat without a locale in a localised app. Flutter does not set Intl.defaultLocale, "
                 "so this formats as en_US (English months, Western digits) for every user."),
    'I18N-015': ('translation-in-logic', 'medium',
                 "Logic, state or data code resolves translated text. The string freezes at the locale it was built "
                 "in and the layer now depends on the UI; return a key, enum or typed failure and translate in the view."),
    'I18N-016': ('missing-localization-delegates', 'medium',
                 "The app widget is missing localizationsDelegates/supportedLocales (or the Global*Localizations "
                 "delegates). Without GlobalWidgetsLocalizations, Directionality stays LTR even for Arabic."),
    'I18N-018': ('mojibake-text', 'high',
                 "Text that was UTF-8, decoded as Latin-1/CP1252 and saved again (Arabic shows as 'Ø§Ù„' or "
                 "'Ã˜Â§'). Users see garbage; restore the original text and keep files UTF-8."),
    'I18N-017': ('dynamic-icu-pattern', 'medium',
                 "An ICU/Intl message pattern is built at runtime. Untrusted text inside a pattern is parsed as "
                 "syntax ({, }, ', plural) and can break or rewrite the message; pass it as an argument."),
}

FIX_BY_PROFILE = {
    'mvn': "MVN: the notifier stores a typed value (enum, sealed XError, key); the view maps it with AppLocalizations.of(context).",
    'mvvm': "MVVM: the view model exposes typed state or an error enum; the view (or a widget-side mapper) translates it.",
    'bloc': "Bloc: emit a status enum or typed failure; translate in BlocBuilder/BlocListener with the context.",
    'riverpod': "Riverpod: keep AsyncValue/state typed; translate in the widget's switch.",
    'provider': "Provider: keep a typed field on the ChangeNotifier; translate in the Consumer/build.",
    'getx': "GetX: store the key in the controller and call .tr in the view (Obx/GetBuilder), so Get.updateLocale re-renders it.",
    'mvc': "MVC: the controller exposes typed state; the view translates.",
    'setstate': "Keep typed values in State fields and translate in build().",
    'unknown': "Keep typed values in logic and translate in the widget that has the BuildContext.",
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$|(^|/)l10n\.dart$|'
                          r'(^|/)strings[^/]*\.g\.dart$|(^|/)codegen_loader\.g\.dart$')
EXCLUDED_PATH_RE = re.compile(r'(^|/)(debug|dev|devtools|example|examples|demo|demos|playground|sandbox|storybook|'
                              r'widgetbook|mock|mocks|fake|fakes|fixtures|testing|test_utils|gallery_debug)(/|$)|'
                              r'(_debug|_dev|_preview|_mock|_fake|\.stories|_stories|_story)\.dart$|(^|/)debug_[^/]*\.dart$')

RTL_LANGS = {'ar', 'fa', 'he', 'iw', 'ps', 'sd', 'ur', 'ug', 'yi', 'dv', 'ckb'}
# CLDR cardinal categories that integers can hit and that differ from `other` (intl plural_rules.dart).
PLURAL_REQUIRED = {
    'ar': ('one', 'two', 'few', 'many'),
    'he': ('one', 'two'), 'iw': ('one', 'two'),
    'ru': ('one', 'few', 'many'), 'uk': ('one', 'few', 'many'), 'be': ('one', 'few', 'many'),
    'pl': ('one', 'few', 'many'),
    'cs': ('one', 'few'), 'sk': ('one', 'few'),
    'hr': ('one', 'few'), 'sr': ('one', 'few'), 'bs': ('one', 'few'),
    'lt': ('one', 'few'), 'sl': ('one', 'two', 'few'),
    'ga': ('one', 'two', 'few', 'many'), 'cy': ('zero', 'one', 'two', 'few', 'many'),
    'lv': ('zero', 'one'),
}
PLURAL_ALIASES = {'=0': 'zero', '=1': 'one', '=2': 'two', '0': 'zero', '1': 'one', '2': 'two'}
PLURAL_KEYS = {'zero', 'one', 'two', 'few', 'many', 'other'}

SECRET_PATTERNS = [
    ('Google API key', re.compile(r'AIza[0-9A-Za-z_\-]{35}')),
    ('Stripe secret key', re.compile(r'\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}')),
    ('AWS access key id', re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ('GitHub token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}')),
    ('Slack token', re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}')),
    ('private key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('JWT', re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}')),
    ('credentials in URL', re.compile(r'https?://[^/\s:@{}]+:[^/\s@{}]+@')),
    ('token in URL query', re.compile(r'[?&](?:api[_-]?key|key|token|access_token|secret|password|sig|signature)=[^&\s{}]{8,}', re.I)),
]
SECRET_KEY_NAME = re.compile(r'(?i)(api[_-]?key|secret|passw(or)?d|token|private[_-]?key|client[_-]?secret|bearer)')

UNIVERSAL_NAMED = {'hintText', 'labelText', 'helperText', 'errorText', 'counterText', 'prefixText', 'suffixText',
                   'semanticLabel', 'semanticsLabel', 'tooltip', 'helpText', 'cancelText', 'confirmText',
                   'fieldLabelText', 'fieldHintText', 'errorFormatText', 'errorInvalidText', 'barrierLabel',
                   'middleText', 'textConfirm', 'textCancel', 'textCustom', 'placeholder', 'hourLabelText',
                   'minuteLabelText', 'searchFieldLabel', 'restorationScopeId_'}
KNOWN_NAMED = {
    'MaterialApp': {'title'}, 'MaterialApp.router': {'title'}, 'CupertinoApp': {'title'},
    'CupertinoApp.router': {'title'}, 'WidgetsApp': {'title'}, 'GetMaterialApp': {'title'},
    'GetMaterialApp.router': {'title'}, 'Title': {'title'},
    'BottomNavigationBarItem': {'label', 'tooltip'}, 'NavigationDestination': {'label', 'tooltip'},
    'SnackBarAction': {'label'}, 'Tab': {'text'}, 'TextSpan': {'text'}, 'Tooltip': {'message'},
    'Semantics': {'label', 'hint', 'value', 'tooltip'}, 'DropdownMenuEntry': {'label'},
    'Fluttertoast.showToast': {'msg'}, 'Get.defaultDialog': {'title'}, 'Get.snackbar': {'title', 'message'},
    'CupertinoContextMenuAction': set(), 'PopupMenuItem': set(), 'CheckedPopupMenuItem': set(),
    'showToast': {'msg'}, 'SearchDelegate': {'searchFieldLabel'}, 'TextField': {'placeholder'},
}
POSITIONAL = {'Text': (0,), 'SelectableText': (0,), 'AutoSizeText': (0,), 'Get.snackbar': (0, 1),
              'Get.rawSnackbar': (), 'showToast': (0,), 'Text.new': (0,)}
RESTRICTED_PARAM_RE = re.compile(r'(?i)(title|subtitle|label|text|message|hint|caption|description|header|'
                                 r'heading|placeholder|tooltip|content|body|buttonText|actionText|cta)$')
WIDGET_SUPERS = {'StatelessWidget', 'StatefulWidget', 'ConsumerWidget', 'ConsumerStatefulWidget', 'HookWidget',
                 'HookConsumerWidget', 'StatefulHookWidget', 'StatefulHookConsumerWidget', 'GetView', 'GetWidget',
                 'GetResponsiveView', 'GetResponsiveWidget', 'StatelessHookWidget', 'LeafRenderObjectWidget'}
KEY_SUFFIX = re.compile(r'^\s*\.\s*(tr|tr\s*\(|trParams|trPlural|trPluralParams|trArgs|i18n|plural|localized|'
                        r'translate|tl|t\s*\(|tr\b)')
DEBUG_CALLEE = re.compile(r'(^|\.)(print|debugPrint|log|logger|Logger|developer\.log|assert|debugPrintStack|'
                          r'Key|ValueKey|ObjectKey|GlobalKey|PageStorageKey|LocalKey|RestorationBucket|'
                          r'Exception|Error|ArgumentError|StateError|UnimplementedError|UnsupportedError|'
                          r'FlutterError|ErrorDescription|ErrorSummary|DiagnosticsProperty|StringProperty|'
                          r'FlagProperty|EnumProperty|IntProperty|DoubleProperty|ObjectFlagProperty|'
                          r'Uri|RegExp|DateFormat|NumberFormat|AssetImage|Image\.asset|SvgPicture\.asset|'
                          r'Lottie\.asset|rootBundle\.load\w*|Hero|Icon|RouteSettings)$')
DEBUG_NAMED = {'restorationId', 'debugLabel', 'heroTag', 'tag', 'semanticsIdentifier', 'routeName', 'name',
               'key', 'fontFamily', 'package', 'locale', 'pattern', 'path', 'url', 'route', 'id', 'identifier'}

MIRROR_FREE_ICONS = re.compile(
    r'\bIcons\s*\.\s*((?:keyboard_arrow_left|keyboard_arrow_right|keyboard_double_arrow_left|keyboard_double_arrow_right|'
    r'arrow_circle_left|arrow_circle_right|east|west|subdirectory_arrow_left|subdirectory_arrow_right|'
    r'arrow_left_sharp|arrow_right_sharp)(?:_outlined|_rounded|_sharp|_outline)?)\b|'
    r'\bCupertinoIcons\s*\.\s*((?:chevron_left|chevron_right|chevron_back|chevron_forward|arrow_left|arrow_right|'
    r'chevron_compact_left|chevron_compact_right|arrow_left_circle|arrow_right_circle|chevron_left_circle|'
    r'chevron_right_circle|chevron_left_2|chevron_right_2|arrow_left_square|arrow_right_square)(?:_fill)?)\b')
DIRECTION_AWARE = re.compile(r'TextDirection\s*\.\s*rtl|\bisRtl\b|\bisRTL\b|\bisRightToLeft\b|Directionality\s*\.\s*'
                             r'(?:of|maybeOf)|\btextDirection\s*==|\bisArabic\b|\brtl\b|matchTextDirection|'
                             r'Transform\s*\.\s*flip|\bisLtr\b|\bisLTR\b|TextDirection\s*\.\s*ltr\s*[?=]')

def is_prose(text):
    """Real words (not a separator, unit, acronym or one capitalised name) in a literal."""
    words = WORD_RE.findall(text)
    if len(words) >= 2:
        return True
    if len(words) == 1:
        w = words[0]
        latin = re.match(r'^[A-Za-z]+$', w)
        return not latin or (w.islower() and len(w) >= 3)
    return False


MOJIBAKE_RE = re.compile(r'(?:[\u00D8\u00D9\u00DA\u00DB\u00C3\u00C2\u00C5\u00D0\u00D1\u00D7]'
                         r'[\u0080-\u00BF\u0152\u0153\u0160\u0161\u0178\u017D\u017E\u0192\u02C6\u02DC'
                         r'\u2013-\u203A\u20AC\u2122]){2,}')
LETTER_RE = re.compile(r'[^\W\d_]', re.U)
WORD_RE = re.compile(r'[^\W\d_]{2,}', re.U)


# --------------------------------------------------------------------------- lexing

def lex(text):
    """Return (code, masked, comments, strings).

    code:     comments blanked (newlines kept), strings intact.
    masked:   comments and string *contents* blanked (quotes kept): safe for paren/brace matching.
    strings:  list of dicts {s, e, cs, ce, raw, interps:[(s, e)]}: literal span, content span, and the
              spans of `$x` / `${...}` interpolations inside it (absolute offsets).
    """
    n = len(text)
    code = list(text)
    masked = list(text)
    comments, strings = [], []

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

    def is_str_start(i):
        c = text[i]
        if c in '\'"':
            return True
        return c in 'rR' and i + 1 < n and text[i + 1] in '\'"' and not (i > 0 and (text[i - 1].isalnum() or text[i - 1] in '_$'))

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
            if is_str_start(i):
                i = skip_string(i, None)
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return n

    def skip_string(i, interps):
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
            if not raw and text[i] == '$' and i + 1 < n:
                if text[i + 1] == '{':
                    j = skip_expr(i + 2)
                    if interps is not None:
                        interps.append((i, j))
                    i = j
                    continue
                m = re.match(r'[A-Za-z_]\w*', text[i + 1:i + 80])
                if m:
                    if interps is not None:
                        interps.append((i, i + 1 + m.end()))
                    i += 1 + m.end()
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
        elif is_str_start(i):
            interps = []
            j = skip_string(i, interps)
            p = i + (1 if text[i] in 'rR' else 0)
            q = text[p]
            dl = 3 if text.startswith(q * 3, p) else 1
            cs, ce = p + dl, max(p + dl, j - dl)
            if j <= n and not text.startswith(q * dl, j - dl):
                ce = j  # unterminated
            blank(masked, cs, ce)
            strings.append({'s': i, 'e': j, 'cs': cs, 'ce': ce, 'raw': p != i, 'interps': interps})
            i = j
        else:
            i += 1
    return ''.join(code), ''.join(masked), comments, strings


def match_pairs(masked, open_c, close_c):
    pairs, stack = {}, []
    for i, c in enumerate(masked):
        if c == open_c:
            stack.append(i)
        elif c == close_c and stack:
            o = stack.pop()
            pairs[o] = i
    return pairs


class Nesting(object):
    """Innermost-enclosing lookups for one bracket kind."""

    def __init__(self, pairs):
        self.pairs = pairs
        self.opens = sorted(pairs)
        self.parent = {}
        stack = []
        for o in self.opens:
            while stack and pairs[stack[-1]] < o:
                stack.pop()
            self.parent[o] = stack[-1] if stack else None
            stack.append(o)

    def innermost(self, pos):
        k = bisect.bisect_left(self.opens, pos) - 1
        if k < 0:
            return None
        o = self.opens[k]
        while o is not None and not (o < pos < self.pairs[o]):
            o = self.parent.get(o)
        return o

    def chain(self, pos):
        o = self.innermost(pos)
        while o is not None:
            yield o
            o = self.parent.get(o)


# --------------------------------------------------------------------------- per-file model

class DartFile(object):
    def __init__(self, root, rel):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.masked, self.comments, self.strings = lex(self.raw)
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.lines = self.raw.split('\n')
        self.parens = Nesting(match_pairs(self.masked, '(', ')'))
        self.braces = Nesting(match_pairs(self.masked, '{', '}'))
        self.brackets = Nesting(match_pairs(self.masked, '[', ']'))
        self.string_starts = [s['s'] for s in self.strings]
        # code with string *text* blanked but interpolations kept: for finding expressions
        buf = list(self.code)
        for st in self.strings:
            i = st['cs']
            for a, b in st['interps'] + [(st['ce'], st['ce'])]:
                for k in range(i, a):
                    if buf[k] != '\n':
                        buf[k] = ' '
                i = b
        self.icode = ''.join(buf)
        self.layer, self.role, self.feature = 'other', 'other', None
        self.suppress_line, self.suppress_file = {}, {}
        for s, e in self.comments:
            txt = self.raw[s:e]
            for m in SUPPRESS_RE.finditer(txt):
                ids = re.findall(r'I18N-\d{3}', m.group(2))
                reason = m.group(3).strip().rstrip('*/').strip() or '(no reason given)'
                if m.group(1):
                    for rid in ids:
                        self.suppress_file[rid] = reason
                else:
                    ln = self.line_of(s)
                    for rid in ids:
                        self.suppress_line.setdefault(ln, {})[rid] = reason
                        # a comment alone on its line covers the next line too
                        if not self.lines[ln - 1][:s - self.line_starts[ln - 1]].strip():
                            self.suppress_line.setdefault(ln + 1, {})[rid] = reason

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def line_text(self, ln):
        return self.lines[ln - 1].strip() if 0 < ln <= len(self.lines) else ''

    def string_at(self, pos):
        k = bisect.bisect_right(self.string_starts, pos) - 1
        if k >= 0 and self.strings[k]['s'] <= pos < self.strings[k]['e']:
            return self.strings[k]
        return None

    def content(self, st):
        """String content with interpolations (and escape sequences) replaced by spaces."""
        out, i = [], st['cs']
        for a, b in st['interps']:
            out.append(self.raw[i:a])
            out.append(' ')
            i = b
        out.append(self.raw[i:st['ce']])
        txt = ''.join(out)
        if not st['raw']:
            txt = re.sub(r'\\(?:u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)', ' ', txt)
        return txt


SUPPRESS_RE = re.compile(r'i18n-ignore(-file)?\s*:\s*((?:I18N-\d{3})(?:\s*,\s*I18N-\d{3})*)\s*(.*)')
CLASS_DECL_RE = re.compile(r'\bclass\s+([A-Za-z_]\w*)\s*(?:<[^{]*?>)?\s+extends\s+([A-Za-z_][\w.]*)'
                           r'(?:\s*<[^{]*?>)?([^{]*)\{')
CALLEE_RE = re.compile(r'((?:[A-Za-z_]\w*\s*\.\s*)*[A-Za-z_]\w*)\s*(?:<[^<>()]*(?:<[^<>()]*>[^<>()]*)*>)?\s*!?\s*$')


def callee_before(masked, o):
    seg = masked[max(0, o - 160):o]
    m = CALLEE_RE.search(seg)
    if not m:
        return ''
    name = re.sub(r'\s+', '', m.group(1))
    if name.startswith('const.') or name.startswith('new.'):
        name = name.split('.', 1)[1]
    return name


def split_args(masked, o, c):
    """Top-level argument segments of the call whose parens are (o, c): [(start, end)]."""
    segs, depth, start = [], 0, o + 1
    for i in range(o + 1, c):
        ch = masked[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == ',' and depth == 0:
            segs.append((start, i))
            start = i + 1
    if masked[start:c].strip():
        segs.append((start, c))
    return segs


NAMED_ARG_RE = re.compile(r'^\s*([A-Za-z_]\w*)\s*:(?!:)')


def arg_info(masked, o, c):
    """[(name or None, positional index or None, start, end, value_start)]."""
    out, pos = [], 0
    for s, e in split_args(masked, o, c):
        m = NAMED_ARG_RE.match(masked[s:e])
        if m:
            out.append((m.group(1), None, s, e, s + m.end()))
        else:
            out.append((None, pos, s, e, s))
            pos += 1
    return out


# --------------------------------------------------------------------------- ICU (gen-l10n) parsing

class IcuError(Exception):
    pass


def parse_icu(msg, escaping=False):
    """Return {'placeholders': set, 'plurals': [(name, set(cases))], 'selects': [name]} or raise IcuError."""
    res = {'placeholders': set(), 'plurals': [], 'selects': []}
    n = len(msg)

    def message(i, depth):
        while i < n:
            ch = msg[i]
            if escaping and ch == "'":
                if i + 1 < n and msg[i + 1] == "'":
                    i += 2
                    continue
                j = msg.find("'", i + 1)
                if j < 0:
                    return n
                i = j + 1
                continue
            if ch == '{':
                i = argument(i + 1, depth + 1)
                continue
            if ch == '}':
                if depth == 0:
                    raise IcuError('unbalanced }')
                return i
            i += 1
        if depth > 0:
            raise IcuError('unterminated {')
        return i

    def ws(i):
        while i < n and msg[i] in ' \t\n\r':
            i += 1
        return i

    def argument(i, depth):
        i = ws(i)
        m = re.match(r'[^\s{},\']+', msg[i:])  # gen-l10n wants an identifier; keep others to report them
        if not m:
            raise IcuError('bad placeholder')
        name = m.group(0)
        i = ws(i + m.end())
        if i < n and msg[i] == '}':
            res['placeholders'].add(name)
            return i + 1
        if i >= n or msg[i] != ',':
            raise IcuError('bad argument')
        i = ws(i + 1)
        m = re.match(r'[A-Za-z]+', msg[i:])
        if not m:
            raise IcuError('bad argument type')
        kind = m.group(0)
        i = ws(i + m.end())
        res['placeholders'].add(name)
        if kind not in ('plural', 'select', 'selectordinal'):
            # {date, date, yMd} style argument: skip to the closing brace
            j = msg.find('}', i)
            if j < 0:
                raise IcuError('unterminated argument')
            return j + 1
        if i >= n or msg[i] != ',':
            raise IcuError('missing , after %s' % kind)
        i = ws(i + 1)
        cases = set()
        while i < n and msg[i] != '}':
            m = re.match(r'=?\s*-?\d+|[A-Za-z_]\w*', msg[i:])
            if not m:
                raise IcuError('bad case')
            case = re.sub(r'\s+', '', m.group(0))
            i = ws(i + m.end())
            if i >= n or msg[i] != '{':
                raise IcuError('case without {')
            j = message(i + 1, depth + 1)
            if j >= n or msg[j] != '}':
                raise IcuError('unterminated case')
            cases.add(PLURAL_ALIASES.get(case, case) if kind != 'select' else case)
            i = ws(j + 1)
        if i >= n:
            raise IcuError('unterminated %s' % kind)
        if kind == 'select':
            res['selects'].append(name)
        else:
            res['plurals'].append((name, cases))
        return i + 1

    message(0, 0)
    return res


def json_placeholders(msg):
    """easy_localization / slang placeholders: {} positional, {name}, $name, ${name}."""
    names = set(re.findall(r'\{\s*([A-Za-z_]\w*)\s*\}', msg))
    names |= set(re.findall(r'\$\{?([A-Za-z_]\w*)\}?', msg))
    pos = len(re.findall(r'\{\s*\}', msg))
    if pos:
        names.add('{} x%d' % pos)
    return names


# --------------------------------------------------------------------------- catalogs

KEY_LINE_RE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*:')
LOCALE_RE = re.compile(r'^([a-z]{2,3})(?:[_-]([A-Z][a-z]{3}))?(?:[_-]([A-Z]{2}|\d{3}))?$')


def lang_of(locale):
    return re.split(r'[_-]', locale)[0].lower() if locale else ''


class Catalog(object):
    """One locale file: messages {key: value}, line numbers, plural/placeholder info."""

    def __init__(self, root, rel, locale, kind, escaping=False):
        self.rel, self.locale, self.kind = rel, locale, kind
        self.messages, self.lines, self.meta = {}, {}, {}
        self.ignore = {}
        self.error = None
        try:
            with open(os.path.join(root, rel), encoding='utf-8-sig', errors='replace') as fh:
                self.raw = fh.read()
            data = json.loads(self.raw)
        except (OSError, ValueError) as exc:
            self.raw, data = '', {}
            self.error = str(exc)[:80]
        if not isinstance(data, dict):
            data = {}
        ign = data.get('@@x-i18n-ignore')
        if isinstance(ign, str):
            ign = [ign]
        if isinstance(ign, list):
            for item in ign:
                if isinstance(item, str):
                    for m in re.finditer(r'(I18N-\d{3})\s*([^;]*)', item):
                        self.ignore[m.group(1)] = m.group(2).strip() or '(no reason given)'
        if kind == 'arb':
            if not locale and isinstance(data.get('@@locale'), str):
                self.locale = data['@@locale']
            for k, v in data.items():
                if k.startswith('@'):
                    if k.startswith('@') and not k.startswith('@@') and isinstance(v, dict):
                        self.meta[k[1:]] = v
                    continue
                if isinstance(v, str):
                    self.messages[k] = v
        else:
            self._flatten(data, '')
        first_line = {}
        for i, line in enumerate(self.raw.split('\n'), 1):
            m = KEY_LINE_RE.match(line)
            if m and m.group(1) not in first_line:
                first_line[m.group(1)] = i
        for k in self.messages:
            self.lines[k] = first_line.get(k.split('.')[-1], 1)
        self.escaping = escaping

    def _flatten(self, d, prefix):
        for k, v in d.items():
            if k.startswith('@@'):
                continue
            key = prefix + k
            if isinstance(v, dict):
                ks = set(v)
                if ks and ks <= PLURAL_KEYS | {'@'} and 'other' in ks and all(isinstance(x, str) for x in v.values()):
                    self.messages[key] = {'__plural__': {c: v[c] for c in v}}
                else:
                    self._flatten(v, key + '.')
            elif isinstance(v, str):
                self.messages[key] = v

    def info(self, key):
        """(placeholders set, plurals [(name, cases)], parse_ok)."""
        v = self.messages.get(key)
        if isinstance(v, dict):
            forms = v['__plural__']
            ph = set()
            for txt in forms.values():
                ph |= json_placeholders(txt)
            return ph, [('(count)', set(forms))], True
        if v is None:
            return set(), [], False
        if self.kind == 'arb':
            try:
                r = parse_icu(v, self.escaping)
            except IcuError:
                return set(), [], False
            return r['placeholders'], r['plurals'], True
        return json_placeholders(v), [], True


def read_simple_yaml(path):
    out = {}
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                m = re.match(r'^([A-Za-z][\w-]*)\s*:\s*(.*?)\s*(?:#.*)?$', line)
                if m:
                    out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def find_catalog_groups(root, deps, pubspec, l10n):
    """Return a list of groups: {'system', 'dir', 'template': Catalog, 'catalogs': [Catalog]}."""
    groups = []
    escaping = l10n.get('use-escaping', '').lower() == 'true'
    skip_dirs = {'build', '.dart_tool', '.git', 'ios', 'android', 'macos', 'windows', 'linux', 'web', 'node_modules',
                 '.pub-cache', 'test', 'integration_test', '.fvm', 'Pods'}

    def walk(base):
        for dp, dns, fns in os.walk(base):
            dns[:] = sorted(d for d in dns if d not in skip_dirs and not d.startswith('.'))
            for fn in sorted(fns):
                yield os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/')

    # ARB (gen-l10n, intl_utils, or loose)
    arb_dirs = {}
    for rel in walk(root):
        if rel.endswith('.arb') and '/example/' not in '/' + rel:
            arb_dirs.setdefault(os.path.dirname(rel), []).append(rel)
    if l10n or arb_dirs:
        cfg_dir = (l10n.get('arb-dir') or 'lib/l10n').strip('/') if l10n else None
        for d, files in sorted(arb_dirs.items()):
            names = [os.path.basename(f) for f in files]
            if cfg_dir is not None and d == cfg_dir:
                system = 'gen-l10n'
                template_name = l10n.get('template-arb-file') or 'app_en.arb'
            elif 'intl_utils' in deps or re.search(r'^flutter_intl\s*:', pubspec, re.M) or any(n.startswith('intl_') for n in names):
                system = 'intl_utils'
                mm = re.search(r'^\s+main_locale\s*:\s*(\S+)', pubspec, re.M)
                template_name = 'intl_%s.arb' % (mm.group(1) if mm else 'en')
            else:
                system = 'arb'
                template_name = next((n for n in names if re.search(r'[_-]en\.arb$', n)), names[0])
            if template_name not in names:
                template_name = next((n for n in names if re.search(r'[_-]en\.arb$', n)), sorted(names)[0])
            cats = []
            for f in files:
                stem = os.path.basename(f)[:-4]
                m = re.search(r'[_-]([a-z]{2,3}(?:[_-][A-Z][a-z]{3})?(?:[_-](?:[A-Z]{2}|\d{3}))?)$', stem)
                cats.append(Catalog(root, f, m.group(1) if m else '', 'arb', escaping))
            tmpl = next(c for c in cats if os.path.basename(c.rel) == template_name)
            groups.append({'system': system, 'dir': d, 'template': tmpl, 'catalogs': cats})

    # easy_localization JSON
    if 'easy_localization' in deps:
        cand = {}
        for rel in walk(root):
            if rel.endswith('.json') and (rel.startswith('assets/') or rel.startswith('lib/') or '/translations/' in rel
                                          or '/langs/' in rel or '/i18n/' in rel or '/l10n/' in rel):
                stem = os.path.basename(rel)[:-5]
                if LOCALE_RE.match(stem):
                    cand.setdefault(os.path.dirname(rel), []).append((rel, stem))
        for d, items in sorted(cand.items()):
            if len(items) < 2 and not ('translations' in d or 'langs' in d):
                continue
            cats = [Catalog(root, rel, stem.replace('-', '_'), 'json') for rel, stem in items]
            mm = re.search(r'fallbackLocale\s*:\s*(?:const\s+)?Locale\(\s*[\'"](\w+)', '')
            tmpl = next((c for c in cats if lang_of(c.locale) == 'en'), None) or max(cats, key=lambda c: len(c.messages))
            groups.append({'system': 'easy_localization', 'dir': d, 'template': tmpl, 'catalogs': cats})

    # slang JSON
    if 'slang' in deps or 'slang_flutter' in deps:
        cand = {}
        for rel in walk(root):
            m = re.search(r'(?:^|/)(?:\w+?_)?([a-z]{2,3}(?:[_-][A-Z]{2})?)\.i18n\.json$', rel)
            if m:
                cand.setdefault(os.path.dirname(rel), []).append((rel, m.group(1)))
        for d, items in sorted(cand.items()):
            cats = [Catalog(root, rel, loc.replace('-', '_'), 'json') for rel, loc in items]
            tmpl = next((c for c in cats if lang_of(c.locale) == 'en'), None) or max(cats, key=lambda c: len(c.messages))
            groups.append({'system': 'slang', 'dir': d, 'template': tmpl, 'catalogs': cats})
    return groups


# --------------------------------------------------------------------------- classification fallback

def classify_fallback(rel):
    p = rel.lower()
    segs = p.split('/')
    layer = 'other'
    for s in segs[1:-1]:
        if s == 'domain':
            layer = 'domain'
            break
        if s == 'data':
            layer = 'data'
            break
        if s in ('presentation', 'ui', 'view', 'views', 'screens', 'pages', 'widgets'):
            layer = 'presentation'
            break
        if s in ('core', 'shared', 'common', 'utils'):
            layer = 'core'
    base = segs[-1]
    role = 'other'
    if re.search(r'_(notifier|view_model|viewmodel|bloc|cubit|controller|store)\.dart$', base) or \
            any(s in ('notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
                      'cubit', 'cubits', 'controller', 'controllers') for s in segs):
        role = 'logic'
    elif base.endswith('_state.dart') or 'state' in segs:
        role = 'state'
    elif 'usecases' in segs or 'use_cases' in segs or base.endswith('_usecase.dart') or base.endswith('_use_case.dart'):
        role = 'usecase'
    elif base.endswith('_repository_impl.dart') or ('repositories' in segs and layer == 'data'):
        role = 'repository-impl'
    elif base.endswith('_repository.dart'):
        role = 'repository-contract'
    elif any(s in ('sources', 'datasources', 'data_sources', 'api', 'remote', 'local') for s in segs) or \
            re.search(r'_(source|api|client)\.dart$', base):
        role = 'source'
    elif 'services' in segs or base.endswith('_service.dart'):
        role = 'service'
    elif re.search(r'_(dto|request|response)\.dart$', base):
        role = 'dto'
    elif 'entities' in segs:
        role = 'entity'
    elif re.search(r'_(screen|page|view)\.dart$', base) or any(s in ('screens', 'pages', 'views', 'view') for s in segs):
        role = 'view'
    elif 'widgets' in segs or 'widget' in segs:
        role = 'widget'
    if layer == 'other' and role in ('repository-impl', 'source', 'service', 'dto'):
        layer = 'data'
    if layer == 'other' and role in ('usecase', 'entity'):
        layer = 'domain'
    if layer == 'other' and role in ('logic', 'state', 'view', 'widget'):
        layer = 'presentation'
    return layer, role


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
        return None, 'path-based fallback (flutter-architecture skill not installed: ../flutter-architecture/scripts/arch_check.py missing)'
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


def detect_profile_fallback(deps, rels):
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


# --------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, root, files, groups, ctx):
        self.root, self.files, self.groups, self.ctx = root, files, groups, ctx
        self.findings, self.suppressed = [], []
        self.seen = set()

    def add(self, where, rid, line, evidence, severity=None, note=''):
        """where: DartFile or Catalog."""
        sev = severity or RULES[rid][1]
        rel = where.rel
        key = (rid, rel, line, evidence)
        if key in self.seen:
            return
        self.seen.add(key)
        reason = None
        if isinstance(where, DartFile):
            reason = where.suppress_file.get(rid) or where.suppress_line.get(line, {}).get(rid)
        else:
            reason = where.ignore.get(rid)
        ev = re.sub(r'\s+', ' ', evidence).strip()
        if len(ev) > 140:
            ev = ev[:137] + '...'
        item = {'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': rel, 'line': line,
                'evidence': ev, 'message': RULES[rid][2], 'note': note}
        if reason:
            self.suppressed.append({'id': rid, 'file': rel, 'line': line, 'reason': reason})
        else:
            self.findings.append(item)

    # ------------------------------------------------------------ catalogs
    def check_catalogs(self):
        for g in self.groups:
            tmpl = g['template']
            by_locale = {c.locale: c for c in g['catalogs']}
            tkeys = list(tmpl.messages)
            # I18N-006 (once per template)
            if tmpl.kind == 'arb' and tkeys:
                undescribed = [k for k in tkeys if not (isinstance(tmpl.meta.get(k), dict) and tmpl.meta[k].get('description'))]
                if len(undescribed) * 5 >= len(tkeys) and len(undescribed) >= 3:
                    self.add(tmpl, 'I18N-006', 1, '%d of %d template messages have no description (e.g. %s)' %
                             (len(undescribed), len(tkeys), ', '.join(undescribed[:3])))
            for c in g['catalogs']:
                if c.error:
                    continue  # listed under stats.catalogs[].unreadable; gen-l10n reports the syntax error
                self.check_secrets(c)
                bad = [k for k, v in c.messages.items()
                       if any(MOJIBAKE_RE.search(x) for x in (v['__plural__'].values() if isinstance(v, dict) else [v]))]
                if bad:
                    self.add(c, 'I18N-018', c.lines.get(bad[0], 1), '%d message%s in %s, first: %s' % (
                        len(bad), '' if len(bad) == 1 else 's', c.locale or c.rel, bad[0]))
                if c is tmpl:
                    self.check_plurals(c, tkeys)
                    continue
                parent = by_locale.get(lang_of(c.locale)) if lang_of(c.locale) != c.locale else None
                have = set(c.messages) | (set(parent.messages) if parent is not None else set())
                missing = [k for k in tkeys if k not in have]
                if missing and tkeys:
                    pct = 100.0 * (len(tkeys) - len(missing)) / len(tkeys)
                    note = 'coverage %.0f%%; falls back to %s' % (pct, tmpl.locale or 'the template')
                    if parent is not None:
                        note += ' (after %s)' % parent.locale
                    self.add(c, 'I18N-001', 1, '%d of %d keys missing in %s: %s%s' %
                             (len(missing), len(tkeys), c.locale or os.path.basename(c.rel), ', '.join(missing[:4]),
                              ' ...' if len(missing) > 4 else ''), note=note)
                self.check_placeholders(tmpl, c)
                self.check_plurals(c, [k for k in tkeys if k in c.messages])

    def check_placeholders(self, tmpl, c):
        for k, v in c.messages.items():
            if k not in tmpl.messages:
                continue
            tph, tpl, tok = tmpl.info(k)
            ph, pl, ok = c.info(k)
            if not (tok and ok):
                continue
            declared = set()
            if tmpl.kind == 'arb' and isinstance(tmpl.meta.get(k), dict) and isinstance(tmpl.meta[k].get('placeholders'), dict):
                declared = set(tmpl.meta[k]['placeholders'])
            allowed = tph | declared
            extra = sorted(ph - allowed)
            lost = sorted(p for p in tph - ph if not p.startswith('{}'))
            if c.kind == 'json':
                lost = sorted(tph - ph)
            if extra or lost:
                parts = []
                if extra:
                    parts.append('unknown %s' % ', '.join('{%s}' % p for p in extra))
                if lost:
                    parts.append('drops %s' % ', '.join('{%s}' % p for p in lost))
                sev = 'medium'
                note = ''
                if extra and any(not re.match(r'^[A-Za-z_]\w*$', p) for p in extra):
                    note = 'placeholder name is not a Dart identifier (translated?)'
                elif extra:
                    note = 'gen-l10n adds the unknown name as a new parameter for every locale' if c.kind == 'arb' else ''
                self.add(c, 'I18N-002', c.lines.get(k, 1), '%s: %s' % (k, '; '.join(parts)), sev, note)

    def check_plurals(self, c, keys):
        req = PLURAL_REQUIRED.get(lang_of(c.locale))
        if not req:
            return
        for k in keys:
            _, plurals, ok = c.info(k)
            if not ok:
                continue
            for name, cases in plurals:
                missing = [x for x in req if x not in cases]
                if missing:
                    note = ''
                    if lang_of(c.locale) == 'ar':
                        note = 'ar: zero=0, one=1, two=2, few=3-10, many=11-99, other=100+ (mod 100)'
                    self.add(c, 'I18N-003', c.lines.get(k, 1), '%s (%s): missing %s' %
                             (k, c.locale, ', '.join(missing)), note=note)
                    break

    def check_secrets(self, c):
        for k, v in c.messages.items():
            texts = list(v['__plural__'].values()) if isinstance(v, dict) else [v]
            for txt in texts:
                hit = None
                for label, rx in SECRET_PATTERNS:
                    if rx.search(txt):
                        hit = label
                        break
                if not hit and SECRET_KEY_NAME.search(k.split('.')[-1]) and re.match(r'^[A-Za-z0-9_\-+/=.]{16,}$', txt) \
                        and re.search(r'\d', txt) and re.search(r'[A-Za-z]', txt):
                    hit = 'secret-like value under key %r' % k
                if hit:
                    shown = re.sub(r'([A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]{6,}', r'\1…', txt)[:60]
                    self.add(c, 'I18N-004', c.lines.get(k, 1), '%s: %s (%s)' % (k, shown, hit))
                    break

    # ------------------------------------------------------------ Dart
    def run(self):
        self.check_catalogs()
        if self.ctx['l10n_yaml'].get('synthetic-package', '').lower() == 'true':
            self.add(self.ctx['l10n_file'], 'I18N-005', self.ctx['l10n_synthetic_line'],
                     'synthetic-package: true', 'high', 'current Flutter stops with "Cannot enable synthetic-package"')
        for df in self.files:
            self.check_imports(df)
            if self.ctx['catalog_localised']:
                self.check_hardcoded(df)
                self.check_concat(df)
            if self.ctx['rtl']:
                self.check_geometry(df)
                self.check_icons(df)
            if self.ctx['format_gate']:
                self.check_formats(df)
            if self.ctx['localised']:
                self.check_logic(df)
                self.check_app_widget(df)
            self.check_dynamic_icu(df)
            self.check_mojibake(df)

    def check_imports(self, df):
        for m in re.finditer(r'^\s*import\s+[\'"](package:flutter_gen/gen_l10n/[^\'"]+)[\'"]', df.code, re.M):
            self.add(df, 'I18N-005', df.line_of(m.start()), "import '%s'" % m.group(1),
                     note='replace with the generated file under lib/ (arb-dir or output-dir)')

    def debug_context(self, df, pos):
        """True if pos sits in debug-only code."""
        for o in df.braces.chain(pos):
            head = df.masked[max(0, o - 120):o]
            if re.search(r'\bif\s*\(\s*!?\s*k(?:Debug|Profile|Release)Mode\b[^)]*\)\s*$', head):
                if 'kReleaseMode' in head and '!' not in head.split('kReleaseMode')[0][-3:]:
                    continue
                return True
            if re.search(r'\b(?:debugFillProperties|toString|toStringShort|debugDescribe\w*)\s*\([^)]*\)\s*$', head):
                return True
        # ternary or && guarded by kDebugMode in the same statement
        start = max(df.masked.rfind(';', 0, pos), df.masked.rfind('{', 0, pos), df.masked.rfind('}', 0, pos))
        if re.search(r'\bk(?:Debug|Profile)Mode\b', df.masked[start + 1:pos]):
            return True
        for o in df.parens.chain(pos):
            name = callee_before(df.masked, o)
            if name and DEBUG_CALLEE.search(name):
                return True
        cls = self.enclosing_class(df, pos)
        if cls and re.search(r'Debug|Dev(?:Tools|Menu|Panel|Screen|Page)|Playground|Sandbox|Showcase|Gallery', cls):
            return True
        return False

    def enclosing_class(self, df, pos):
        best = None
        for m in df.class_decls:
            if m[1] < pos < m[2]:
                best = m[0]
        return best

    def check_hardcoded(self, df):
        if EXCLUDED_PATH_RE.search(df.rel):
            return
        m = df.masked
        widgets = self.ctx['widget_classes']
        for st in df.strings:
            s = st['s']
            # first literal of an adjacent-string group only
            prev = m[:s].rstrip()
            if prev.endswith(("'", '"')) and df.string_at(len(prev) - 1) is not None:
                continue
            # extend over adjacent literals
            group = [st]
            end = st['e']
            while True:
                nxt = re.match(r'\s*', m[end:]).end() + end
                s2 = df.string_at(nxt)
                if s2 is None or s2['s'] != nxt:
                    break
                group.append(s2)
                end = s2['e']
            after = m[end:end + 40]
            if KEY_SUFFIX.match(after):
                continue
            text = ''.join(df.content(x) for x in group)
            if not self.looks_user_facing(text) or MOJIBAKE_RE.search(text):
                continue  # mojibake is I18N-018
            if any(st['s'] < x[0] < end for x in self.translation_spans(df)):
                continue  # a translation glued into a literal is I18N-011
            if self.ctx['package'] and re.sub(r'[\W_]', '', text).lower() == self.ctx['package'].replace('_', '').lower():
                continue  # the app's own name
            o = df.parens.innermost(s)
            if o is None:
                continue
            # the literal must sit directly in this call's argument (not in a nested list/map/closure)
            inner_br = df.brackets.innermost(s)
            inner_bc = df.braces.innermost(s)
            if (inner_br is not None and inner_br > o) or (inner_bc is not None and inner_bc > o):
                continue
            callee = callee_before(m, o)
            if not callee:
                continue
            c = df.parens.pairs[o]
            arg = None
            for a in arg_info(m, o, c):
                if a[2] <= s < a[3]:
                    arg = a
                    break
            if arg is None:
                continue
            if any(arg[2] <= x[0] < arg[3] for x in self.translation_spans(df)):
                continue  # literal joined to a translation in the same argument: I18N-011
            name, pidx = arg[0], arg[1]
            base = callee.split('.')[-1] if callee.count('.') == 1 and callee.split('.')[0][:1].isupper() and \
                callee.split('.')[0] in widgets else callee
            cls_name = callee.split('.')[0] if callee[:1].isupper() else callee
            flagged = False
            if name is None:
                flagged = pidx in POSITIONAL.get(callee, ())
                if flagged:
                    tail = m[c + 1:c + 30]
                    if re.match(r'\s*\.\s*tr\s*\(', tail):  # easy_localization Text('key').tr()
                        continue
            else:
                if name in DEBUG_NAMED:
                    continue
                if name in UNIVERSAL_NAMED:
                    flagged = True
                elif name in KNOWN_NAMED.get(callee, ()):
                    flagged = True
                elif (cls_name in widgets or base in widgets) and RESTRICTED_PARAM_RE.search(name):
                    flagged = True
            if not flagged:
                continue
            if self.debug_context(df, s):
                continue
            sev = 'low' if is_prose(text) else 'info'
            note = '' if sev == 'low' else 'one capitalised word or acronym: may be a brand, unit or code; confirm first'
            line = df.line_of(s)
            self.add(df, 'I18N-010', line, '%s(%s%s)' % (callee, (name + ': ') if name else '',
                                                         df.raw[s:min(end, s + 70)]), sev, note)

    @staticmethod
    def looks_user_facing(text):
        t = text.strip()
        if len(LETTER_RE.findall(t)) < 2:
            return False
        if re.match(r'^[a-z0-9]+(?:[._][a-z0-9]+)+$', t):  # key-like: home.title / login_button
            return False
        if re.match(r'^[A-Z0-9]+(?:_[A-Z0-9]+)+$', t):  # CONSTANT_NAME
            return False
        if re.search(r'^\w+://|^www\.|^mailto:|^tel:|^/[\w/:-]*$|^assets/|^packages/|\.(png|jpe?g|svg|gif|webp|json|'
                     r'riv|ttf|otf|mp3|mp4|wav|lottie|pdf|html?)$', t, re.I):
            return False
        if re.match(r'^[\w.+-]+@[\w-]+\.[\w.]+$', t):
            return False
        if re.match(r'^#?[0-9a-fA-F]{6,8}$', t):
            return False
        if re.match(r'^[yMdEHhmsSaKkLQGzZvVx\s:./,\-\'T]+$', t) and re.search(r'yy|MM|dd|HH|mm', t):
            return False  # date pattern
        return True

    def translation_spans(self, df):
        """Positions (start, end) of translated-string expressions in df.code."""
        if df._tspans is not None:
            return df._tspans
        code = df.icode
        classes = self.ctx['l10n_classes']
        cls_alt = '|'.join(sorted(re.escape(c) for c in classes))
        getters = set(self.ctx['l10n_getters'])
        var_names = set()
        for mm in re.finditer(r'\b(?:final|var|const|late\s+final|late)?\s*(?:(?:%s)\??\s+)?([A-Za-z_]\w*)\s*=\s*'
                              r'(?:(?:%s)\s*\.\s*of\s*\(\s*\w+\s*\)|context\s*\.\s*(?:%s)\b|lookup\w*\s*\()' %
                              (cls_alt, cls_alt, '|'.join(sorted(map(re.escape, getters))) or 'l10n'), code):
            var_names.add(mm.group(1))
        for mm in re.finditer(r'\b(?:%s)\s*\??\s+([A-Za-z_]\w*)\s*[,);=]' % cls_alt, code):
            var_names.add(mm.group(1))
        var_names -= {'context', 'this', 'super', 'of', 'delegate'}
        pats = [r'\b(?:%s)\s*\.\s*of\s*\(\s*\w+\s*\)\s*!?\s*\.\s*([A-Za-z_]\w*)' % cls_alt,
                r'\bS\s*\.\s*current\s*\.\s*([A-Za-z_]\w*)',
                r'\blookup\w*Localizations\s*\([^()]*\)\s*\.\s*([A-Za-z_]\w*)']
        if getters:
            pats.append(r'\bcontext\s*\.\s*(?:%s)\s*\.\s*([A-Za-z_]\w*)' % '|'.join(sorted(map(re.escape, getters))))
        if var_names:
            pats.append(r'(?<![\w.$])(?:%s)\s*!?\s*\.\s*([A-Za-z_]\w*)' % '|'.join(sorted(map(re.escape, var_names))))
        spans = []
        for p in pats:
            for mm in re.finditer(p, code):
                if mm.group(1) in ('localeName', 'of', 'delegate', 'supportedLocales', 'localizationsDelegates',
                                   'hashCode', 'runtimeType', 'toString'):
                    continue
                e = mm.end()
                rest = code[e:e + 2]
                if re.match(r'\s*\(', code[e:e + 20]):
                    o = code.index('(', e)
                    c = df.parens.pairs.get(o)
                    if c is not None:
                        e = c + 1
                spans.append((mm.start(), e))
        # GetX 'key'.tr / easy_localization 'key'.tr() / tr('key')
        for st in df.strings:
            after = code[st['e']:st['e'] + 30]
            mm = re.match(r'\s*\.\s*(?:tr|trParams|trPlural)\b(\s*\()?', after)
            if mm:
                e = st['e'] + mm.end()
                if mm.group(1):
                    o = code.index('(', st['e'])
                    c = df.parens.pairs.get(o)
                    e = c + 1 if c is not None else e
                spans.append((st['s'], e))
        for mm in re.finditer(r'(?<![\w.])(?:tr|plural|context\s*\.\s*tr)\s*\(\s*[\'"]', code):
            o = code.index('(', mm.start())
            c = df.parens.pairs.get(o)
            if c is not None:
                spans.append((mm.start(), c + 1))
        spans.sort()
        df._tspans = spans
        return spans

    def check_concat(self, df):
        if EXCLUDED_PATH_RE.search(df.rel):
            return
        spans = self.translation_spans(df)
        if not spans:
            return
        code, m = df.code, df.masked
        done_strings = set()
        for s, e in spans:
            st = df.string_at(s)
            if st is not None and st['s'] != s:
                # inside an interpolation of string st
                if id(st) in done_strings:
                    continue
                done_strings.add(id(st))
                if self.debug_context(df, st['s']):
                    continue
                inside = [x for x in spans if st['cs'] <= x[0] < st['ce']]
                rest = df.content(st)
                others = [it for it in st['interps'] if not any(it[0] <= x[0] < it[1] for x in inside)]
                if is_prose(re.sub(r'<[^<>]*>', ' ', rest)):
                    sev = 'medium'
                elif rest.strip() or others or len(inside) >= 2:
                    sev = 'low'
                else:
                    continue
                self.add(df, 'I18N-011', df.line_of(st['s']), df.raw[st['s']:min(st['e'], st['s'] + 100)], sev,
                         'interpolated into a larger string')
                continue
            if st is not None and st['s'] == s:
                pass  # 'key'.tr span starting at a literal: fall through to operator checks
            before = m[max(0, s - 60):s]
            after = m[e:e + 60]
            op_after = re.match(r'\s*\+(?!\+|=)\s*', after)
            op_before = re.search(r'(?<![+=])\+\s*$', before)
            if not (op_after or op_before):
                continue
            if self.debug_context(df, s):
                continue
            other_pos = e + op_after.end() if op_after else None
            sev = 'low'
            for pos in ([other_pos] if other_pos is not None else []) + ([s - len(before) + op_before.start() - 1] if op_before else []):
                if pos is None:
                    continue
                if op_after and pos == other_pos:
                    o_st = df.string_at(pos)
                    if o_st is not None and is_prose(df.content(o_st)):
                        sev = 'medium'
                else:
                    j = len(m[:pos + 1].rstrip()) - 1
                    o_st = df.string_at(j)
                    if o_st is not None and is_prose(df.content(o_st)):
                        sev = 'medium'
            ln = df.line_of(s)
            self.add(df, 'I18N-011', ln, df.line_text(ln), sev, 'joined with +')

    def direction_aware(self, df, pos):
        ln = df.line_of(pos)
        window = '\n'.join(df.lines[max(0, ln - 4):ln + 2])
        window = re.sub(r'//.*', '', window)
        return bool(DIRECTION_AWARE.search(window))

    def check_geometry(self, df):
        m = df.masked
        forces_ltr = bool(re.search(r'textDirection\s*:\s*(?:ui\.)?TextDirection\s*\.\s*ltr', m))
        hits = []

        def norm(x):
            return re.sub(r'\s+', '', x or '')

        for mm in re.finditer(r'\b(EdgeInsets|Positioned|BorderRadius|Border)\s*\.?\s*(only|fromLTRB|horizontal)?\s*\(', m):
            kind, ctor = mm.group(1), mm.group(2)
            if (kind == 'EdgeInsets' and ctor not in ('only', 'fromLTRB')) or (kind == 'Positioned' and ctor) or \
                    (kind == 'BorderRadius' and ctor not in ('only', 'horizontal')) or (kind == 'Border' and ctor):
                continue
            o = mm.end() - 1
            c = df.parens.pairs.get(o)
            if c is None:
                continue
            args = arg_info(m, o, c)
            named = {a[0]: norm(df.code[a[4]:a[3]]) for a in args if a[0]}
            if ctor == 'fromLTRB':
                pos = [norm(df.code[a[2]:a[3]]) for a in args if a[0] is None]
                if len(pos) == 4 and pos[0] != pos[2]:
                    hits.append((mm.start(), 'EdgeInsets.fromLTRB(%s)' % ', '.join(pos), 'medium',
                                 'EdgeInsetsDirectional.fromSTEB'))
                continue
            if kind == 'BorderRadius':
                if ctor == 'horizontal':
                    l, r = named.get('left'), named.get('right')
                else:
                    l = (named.get('topLeft'), named.get('bottomLeft'))
                    r = (named.get('topRight'), named.get('bottomRight'))
                if l != r:
                    hits.append((mm.start(), m[mm.start():mm.end()] + '...)', 'low', 'BorderRadiusDirectional'))
                continue
            l, r = named.get('left'), named.get('right')
            if re.search(r'\.(left|right)\b', (l or '') + (r or '')):
                continue  # copies an already-resolved EdgeInsets/Rect
            if (l or r) and l != r:
                repl = {'EdgeInsets': 'EdgeInsetsDirectional.only(start:, end:)', 'Positioned': 'PositionedDirectional',
                        'Border': 'BorderDirectional'}[kind]
                ev = '%s%s(%s)' % (kind, '.' + ctor if ctor else '',
                                   ', '.join('%s: %s' % (k, v) for k, v in (('left', l), ('right', r)) if v))
                hits.append((mm.start(), ev, 'low' if kind == 'Border' else 'medium', repl))
        for mm in re.finditer(r'\b(Alignment)\s*\.\s*(topLeft|centerLeft|bottomLeft|topRight|centerRight|bottomRight)\b', m):
            before = m[max(0, mm.start() - 20):mm.start()]
            grad = re.search(r'\b(begin|end)\s*:\s*$', before)
            hits.append((mm.start(), 'Alignment.%s' % mm.group(2), 'low' if grad else 'medium',
                         'AlignmentDirectional.%s' % mm.group(2).replace('Left', 'Start').replace('Right', 'End')))
        for mm in re.finditer(r'\b(alignment|begin|end)\s*:\s*\.(topLeft|centerLeft|bottomLeft|topRight|centerRight|bottomRight)\b', m):
            hits.append((mm.start(), '%s: .%s' % (mm.group(1), mm.group(2)), 'low' if mm.group(1) != 'alignment' else 'medium',
                         'AlignmentDirectional.%s' % mm.group(2).replace('Left', 'Start').replace('Right', 'End')))
        for mm in re.finditer(r'\btextAlign\s*:\s*\.(left|right)\b', m):
            hits.append((mm.start(), 'textAlign: .%s' % mm.group(1), 'medium',
                         'TextAlign.%s' % ('start' if mm.group(1) == 'left' else 'end')))
        for mm in re.finditer(r'\bTextAlign\s*\.\s*(left|right)\b', m):
            hits.append((mm.start(), 'TextAlign.%s' % mm.group(1), 'medium',
                         'TextAlign.%s' % ('start' if mm.group(1) == 'left' else 'end')))
        for pos, ev, sev, repl in hits:
            if self.direction_aware(df, pos) or self.debug_context(df, pos):
                continue
            note = 'use %s' % repl
            if forces_ltr:
                sev = 'low'
                note += '; this file forces TextDirection.ltr somewhere: fine if the code sits inside that subtree'
            self.add(df, 'I18N-012', df.line_of(pos), ev, sev, note)

    def check_icons(self, df):
        for mm in MIRROR_FREE_ICONS.finditer(df.masked):
            if self.direction_aware(df, mm.start()):
                continue
            name = mm.group(0).replace(' ', '')
            self.add(df, 'I18N-013', df.line_of(mm.start()), name,
                     note='media/physical arrows are fine; navigation arrows should mirror')

    def check_formats(self, df):
        m = df.masked
        machine_layer = df.layer in ('data', 'domain') or df.role in ('dto', 'source', 'service', 'repository-impl')
        for mm in re.finditer(r'\b(DateFormat|NumberFormat)\s*(?:\.\s*([A-Za-z_]\w*))?\s*\(', m):
            kind, ctor = mm.group(1), mm.group(2)
            if ctor in ('localeExists', 'useNativeDigitsByDefaultFor', 'shouldUseNativeDigitsByDefaultFor',
                        'allLocalesWithSymbols', 'numberOfIntegerDigits', 'new'):
                if ctor != 'new':
                    continue
                ctor = None
            o = mm.end() - 1
            c = df.parens.pairs.get(o)
            if c is None:
                continue
            args = arg_info(m, o, c)
            if any(a[0] == 'locale' for a in args):
                continue
            npos = sum(1 for a in args if a[0] is None)
            if kind == 'DateFormat':
                need = 2 if ctor is None else 1
            elif ctor is None:
                need = 2
            elif ctor in ('decimalPattern', 'percentPattern', 'scientificPattern'):
                need = 1
            else:
                need = 99  # named locale: only
            if npos >= need:
                continue
            if self.debug_context(df, mm.start()):
                continue
            ev = df.code[mm.start():min(c + 1, mm.start() + 80)]
            sev, note = 'medium', ''
            pat = None
            if args and args[0][0] is None:
                ps = df.string_at(args[0][2] + len(m[args[0][2]:args[0][3]]) - len(m[args[0][2]:args[0][3]].lstrip()))
                if ps is not None:
                    pat = df.content(ps)
            if kind == 'DateFormat' and pat is not None and not re.search(r'MMM|E|a|L', pat) and re.search(r'y', pat):
                sev, note = 'info', "numeric/machine pattern: pass 'en' explicitly (or use toIso8601String) to make that intent clear"
            elif machine_layer:
                sev, note = 'info', 'data/domain layer: fine for wire formats; display formatting belongs in the view'
            elif self.ctx['intl_default_locale']:
                sev, note = 'info', 'Intl.defaultLocale is assigned in this project; confirm it follows locale changes'
            self.add(df, 'I18N-014', df.line_of(mm.start()), ev, sev, note)

    def check_logic(self, df):
        if df.role not in ('logic', 'state', 'usecase', 'repository', 'repository-impl', 'repository-contract', 'source',
                           'service', 'entity', 'dto') or EXCLUDED_PATH_RE.search(df.rel):
            return
        if any(name in self.ctx['widget_classes'] for name, _, _ in df.class_decls):
            return  # the file declares a widget: it is UI whatever its folder says
        # Only count places that *resolve* translations here. A mapper that receives AppLocalizations as a
        # parameter (`String label(AppLocalizations l10n) => switch (this) {...}`) is called from the view
        # with the view's l10n: that is the sanctioned pattern, not a finding.
        code = df.icode
        getters = '|'.join(sorted(map(re.escape, self.ctx['l10n_getters'])))
        rx = (r'\b(?:%s)\s*\.\s*of\s*\(|\blookup\w*Localizations\s*\(|\bS\s*\.\s*current\b|'
              r'\bcontext\s*\.\s*(?:%s)\b|(?<![\w.])(?:tr|plural)\s*\(\s*[\'"]|[\'"]\s*\.\s*(?:tr|trParams|trPlural)\b' %
              ('|'.join(sorted(map(re.escape, self.ctx['l10n_classes']))), getters))
        hits = sorted(set(mm.start() for mm in re.finditer(rx, code)))
        code = df.code
        hits = [h for h in hits if not self.debug_context(df, h)]
        if not hits:
            return
        profile = self.ctx['profile']
        getx_tr = profile == 'getx' and all(re.match(r'[\'"]', code[h]) or code[h:h + 3] in ('tr(',) for h in hits)
        sev = 'low' if getx_tr else 'medium'
        note = FIX_BY_PROFILE.get(profile, FIX_BY_PROFILE['unknown'])
        if 'BuildContext' in code and re.search(r'\.of\s*\(\s*context', code):
            note += ' (a BuildContext in logic is also ARCH-102)'
        ln = df.line_of(hits[0])
        self.add(df, 'I18N-015', ln, '%s (%d use%s in this %s file)' % (df.line_text(ln), len(hits),
                                                                        '' if len(hits) == 1 else 's', df.role), sev, note)

    def check_app_widget(self, df):
        m = df.masked
        for mm in re.finditer(r'\b(MaterialApp|CupertinoApp|WidgetsApp|GetMaterialApp|GetCupertinoApp)'
                              r'(\s*\.\s*router)?\s*\(', m):
            if EXCLUDED_PATH_RE.search(df.rel) or self.debug_context(df, mm.start()):
                continue
            o = mm.end() - 1
            c = df.parens.pairs.get(o)
            if c is None:
                continue
            args = arg_info(m, o, c)
            named = {a[0]: df.code[a[4]:a[3]] for a in args if a[0]}
            name = mm.group(1) + ('.router' if mm.group(2) else '')
            sev = 'high' if self.ctx['rtl'] else 'medium'
            problems = []
            if 'localizationsDelegates' not in named:
                problems.append('no localizationsDelegates')
            else:
                v = named['localizationsDelegates'].strip()
                if v.startswith(('[', 'const [', 'const<', '<')) and not re.search(
                        r'GlobalWidgetsLocalizations|GlobalMaterialLocalizations\s*\.\s*delegates|'
                        r'GlobalCupertinoLocalizations\s*\.\s*delegates|localizationsDelegates|localizationDelegates|\.\.\.\s*\w',
                        v):
                    problems.append('localizationsDelegates without GlobalWidgetsLocalizations')
            if 'supportedLocales' not in named:
                problems.append("no supportedLocales (defaults to [Locale('en', 'US')])")
            if problems:
                systems = self.ctx['systems']
                if 'easy_localization' in systems:
                    note = ('easy_localization: localizationsDelegates: context.localizationDelegates, '
                            'supportedLocales: context.supportedLocales, locale: context.locale')
                elif 'gen-l10n' in systems or 'intl_utils' in systems:
                    note = ('gen-l10n: localizationsDelegates: AppLocalizations.localizationsDelegates, '
                            'supportedLocales: AppLocalizations.supportedLocales')
                else:
                    note = ('add flutter_localizations: localizationsDelegates: GlobalMaterialLocalizations.delegates '
                            '(+ GlobalCupertinoLocalizations.delegate) and supportedLocales listing every shipped locale')
                if self.ctx['configured_app_widgets'] and len(named) <= 3:
                    sev = 'low'
                    note = 'secondary app widget (error/fallback screen?) while the main one is configured; ' + note
                self.add(df, 'I18N-016', df.line_of(mm.start()), '%s(...): %s' % (name, '; '.join(problems)), sev, note)

    def check_mojibake(self, df):
        bad = [st for st in df.strings if MOJIBAKE_RE.search(df.raw[st['cs']:st['ce']])]
        if bad:
            first = bad[0]
            self.add(df, 'I18N-018', df.line_of(first['s']), '%d literal%s, first: %s' % (
                len(bad), '' if len(bad) == 1 else 's', df.raw[first['s']:min(first['e'], first['s'] + 50)]))

    def check_dynamic_icu(self, df):
        m = df.masked
        for mm in re.finditer(r'\b(MessageFormat|Intl\s*\.\s*(?:message|plural|gender|select))\s*\(', m):
            o = mm.end() - 1
            c = df.parens.pairs.get(o)
            if c is None:
                continue
            args = arg_info(m, o, c)
            if not args or args[0][0] is not None:
                continue
            seg = df.code[args[0][2]:args[0][3]].strip()
            st = df.string_at(args[0][2] + (len(df.code[args[0][2]:args[0][3]]) - len(df.code[args[0][2]:args[0][3]].lstrip())))
            kind = re.sub(r'\s+', '', mm.group(1))
            if kind == 'MessageFormat':
                bad = st is None or st['interps'] or not seg.endswith(("'", '"'))
            else:
                bad = st is not None and bool(st['interps']) and kind == 'Intl.message'
            if bad:
                self.add(df, 'I18N-017', df.line_of(mm.start()), df.line_text(df.line_of(mm.start())))


# --------------------------------------------------------------------------- CLI

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
    sys.stderr.write('check_i18n.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_i18n.py <project-root> [--json] [--files <list>] '
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
        if re.match(r'^\S', line):
            section = line.split(':')[0].strip()
            continue
        if section in ('dependencies', 'dev_dependencies', 'dependency_overrides'):
            mm = re.match(r'^ {2}([A-Za-z_]\w*)\s*:', line)
            if mm:
                deps.add(mm.group(1))
    return deps


class _Pseudo(object):
    """Lets non-Dart files (l10n.yaml) carry findings."""

    def __init__(self, rel):
        self.rel = rel
        self.ignore = {}


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

    l10n_path = os.path.join(root, 'l10n.yaml')
    l10n = read_simple_yaml(l10n_path) if os.path.isfile(l10n_path) else {}
    l10n_exists = os.path.isfile(l10n_path)
    synth_line = 1
    if l10n_exists:
        with open(l10n_path, encoding='utf-8', errors='replace') as fh:
            for i, line in enumerate(fh, 1):
                if line.strip().startswith('synthetic-package'):
                    synth_line = i
    groups = find_catalog_groups(root, deps, pubspec, l10n if l10n_exists else {})

    # generated-output exclusions from l10n.yaml
    out_dir = (l10n.get('output-dir') or l10n.get('arb-dir') or 'lib/l10n').strip('/')
    out_stem = (l10n.get('output-localization-file') or 'app_localizations.dart')[:-5]
    gen_out = re.compile(r'^%s/%s(_[\w]+)?\.dart$' % (re.escape(out_dir), re.escape(out_stem)))

    rels = []
    lib = os.path.join(root, 'lib')
    if os.path.isdir(lib):
        for dp, dns, fns in os.walk(lib):
            dns[:] = sorted(d for d in dns if not d.startswith('.') and d != 'generated')
            for fn in sorted(fns):
                if fn.endswith('.dart'):
                    rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/')
                    if not GENERATED_RE.search(rel) and not gen_out.match(rel):
                        rels.append(rel)

    arch, classification = (None, 'no lib/ directory') if not rels else run_arch_check(root, opts['profile'])
    arch_files = {}
    if arch and isinstance(arch.get('files'), list):
        for f in arch['files']:
            if isinstance(f, dict) and f.get('file'):
                arch_files[f['file']] = f

    files = []
    for rel in rels:
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if re.search(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|DO NOT EDIT', df.raw[:600]):
            continue
        a = arch_files.get(rel)
        if a:
            df.layer, df.role, df.feature = a.get('layer') or 'other', a.get('role') or 'other', a.get('feature')
        else:
            df.layer, df.role = classify_fallback(rel)
        if df.layer in ('ui', 'view'):
            df.layer = 'presentation'
        df._tspans = None
        df.class_decls = []
        for mm in CLASS_DECL_RE.finditer(df.masked):
            o = mm.end() - 1
            c = df.braces.pairs.get(o, len(df.masked))
            df.class_decls.append((mm.group(1), o, c))
        files.append(df)

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(deps, rels), 'fallback detection from pubspec and folders'

    # project facts
    allcode = '\n'.join(f.code for f in files)
    widget_classes = set()
    supers = {}
    for f in files:
        for mm in CLASS_DECL_RE.finditer(f.masked):
            supers[mm.group(1)] = mm.group(2).split('.')[-1]
            if re.search(r'\b(?:implements|with)\b[^{]*\bPreferredSizeWidget\b', mm.group(3) or ''):
                widget_classes.add(mm.group(1))
    changed = True
    while changed:
        changed = False
        for cls, sup in supers.items():
            if cls not in widget_classes and (sup in WIDGET_SUPERS or sup in widget_classes or
                                              re.match(r'State$|^State<', sup)):
                if sup in WIDGET_SUPERS or sup in widget_classes:
                    widget_classes.add(cls)
                    changed = True
    getx_translations = bool(re.search(r'\bextends\s+Translations\b', allcode)) and 'get' in deps
    locales = set()
    for g in groups:
        for c in g['catalogs']:
            if c.locale:
                locales.add(c.locale)
    for mm in re.finditer(r'\bLocale\s*(?:\.\s*fromSubtags)?\s*\(\s*(?:languageCode\s*:\s*)?[\'"]([a-zA-Z]{2,3})[\'"]', allcode):
        locales.add(mm.group(1).lower())
    if getx_translations:
        for mm in re.finditer(r'[\'"]([a-z]{2,3})(?:[_-][A-Z]{2})?[\'"]\s*:\s*\{', allcode):
            locales.add(mm.group(1))
    rtl = sorted({lang_of(l) for l in locales if lang_of(l) in RTL_LANGS})
    catalog_localised = bool(groups) or l10n_exists or getx_translations or \
        bool(deps & {'easy_localization', 'slang', 'slang_flutter', 'intl_utils'})
    localised = catalog_localised or 'flutter_localizations' in deps
    systems = sorted({g['system'] for g in groups})
    if getx_translations:
        systems.append('getx')
    l10n_classes = {'AppLocalizations', 'S', 'L10n', 'AppLocalization', 'Loc', 'I18n', 'AppStrings', 'Lang', 'L'}
    if l10n.get('output-class'):
        l10n_classes.add(l10n['output-class'])
    if 'slang' in deps or 'slang_flutter' in deps:
        l10n_classes.add('Translations')
    getters = {'l10n', 'loc', 'l', 'strings', 'i18n', 'lang', 'localizations', 'appLocalizations', 'texts', 'tr_'}
    for mm in re.finditer(r'\bget\s+([A-Za-z_]\w*)\s*=>\s*(?:%s)\s*\.\s*of\s*\(\s*this\s*\)' %
                          '|'.join(sorted(map(re.escape, l10n_classes))), allcode):
        getters.add(mm.group(1))
    ctx = {
        'package': package, 'profile': profile, 'rtl': rtl, 'systems': systems, 'locales': sorted(locales), 'localised': localised,
        'catalog_localised': catalog_localised,
        'format_gate': localised or any(lang_of(l) != 'en' for l in locales),
        'widget_classes': widget_classes, 'l10n_classes': l10n_classes, 'l10n_getters': getters,
        'intl_default_locale': bool(re.search(r'\bIntl\s*\.\s*defaultLocale\s*=', allcode)),
        'l10n_yaml': l10n, 'l10n_file': _Pseudo('l10n.yaml'), 'l10n_synthetic_line': synth_line,
    }
    ctx['configured_app_widgets'] = len(re.findall(
        r'\b(?:MaterialApp|CupertinoApp|WidgetsApp|GetMaterialApp|GetCupertinoApp)(?:\s*\.\s*router)?\s*\((?:(?!\b(?:MaterialApp|CupertinoApp)\b)[\s\S]){0,4000}?\blocalizationsDelegates\s*:',
        '\n'.join(f.masked for f in files)))
    ck = Checker(root, files, groups, ctx)
    ck.run()
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (SEV_ORDER.get(f['severity'], 9), f['id'], f['file'], f['line']))

    cat_stats = [{'system': g['system'], 'dir': g['dir'], 'template': g['template'].rel,
                  'locales': sorted(c.locale for c in g['catalogs']),
                  'keys': len(g['template'].messages),
                  'unreadable': [c.rel for c in g['catalogs'] if c.error]} for g in groups]
    report = {
        'schema': SCHEMA, 'root': root, 'package': package,
        'profile': {'presentation': profile, 'source': psource},
        'classification': classification,
        'stats': {'files': len(files), 'catalog_files': sum(len(g['catalogs']) for g in groups),
                  'catalogs': cat_stats, 'systems': systems, 'localised': localised,
                  'locales': sorted(locales), 'rtl_locales': rtl,
                  'intl_default_locale_set': ctx['intl_default_locale'],
                  'reported_scope': 'files list (%d)' % len(only) if only is not None else 'all'},
        'findings': findings,
        'suppressed': suppressed,
    }
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        return 0
    if groups:
        g0 = groups[0]
        loc_line = '%s (%s, template %s), %d locale%s' % (
            ', '.join(systems), g0['dir'], os.path.basename(g0['template'].rel), len(locales),
            '' if len(locales) == 1 else 's')
    elif localised:
        loc_line = '%s, no catalog files found' % (', '.join(systems) or 'flutter_localizations only')
    else:
        loc_line = 'not localised (no l10n.yaml, catalogs or translation package)'
    out = ['== I18N',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  localisation: %s; RTL: %s' % (loc_line, ', '.join(rtl) if rtl else 'none'),
           '  scanned: %d Dart files, %d catalog files' % (len(files), report['stats']['catalog_files'])]
    for cs in cat_stats:
        if cs['unreadable']:
            out.append('  unreadable catalogs (invalid JSON, skipped): %s' % ', '.join(cs['unreadable']))
    index, ordered = {}, []
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(ordered)
            ordered.append((k, []))
        ordered[index[k]][1].append(f)
    if not ordered:
        out.append('  no i18n findings')
    for (rid, sev), items in ordered:
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
