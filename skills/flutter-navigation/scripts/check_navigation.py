#!/usr/bin/env python3
"""check_navigation.py: find navigation and deep-link bugs in a Flutter project (read-only).

Usage:
  python3 -I check_navigation.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (route tables and constants span files);
             only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Layers, roles and the profile come from ../flutter-architecture/scripts/arch_check.py --json
when that sibling skill is installed; otherwise a path-based fallback is used and the output
says so.

Suppression (in the analysed code):
  // nav-ignore: NAV-003 <reason>        on the reported line or the line above it
  // nav-ignore-file: NAV-003 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/flutter-navigation@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

RULES = {
    'NAV-001': ('duplicate-route-path', 'medium',
                "Two routes resolve to the same URL pattern. go_router matches the first one, so the second is "
                "unreachable and navigating to it shows the first route's page."),
    'NAV-002': ('raw-path-string', 'low',
                "Navigation call with a raw path string although the project defines route constants, typed routes "
                "or route names. A typo or a renamed route still compiles and fails at runtime."),
    'NAV-003': ('unvalidated-route-param', 'medium',
                "A deep-link/route parameter is parsed or forced without validation (int.parse, `!`, a hard cast, an "
                "unchecked pathSegments index, an unchecked redirect target). A malformed link crashes the route or "
                "sends the user somewhere unintended. Use tryParse with a fallback, a path regex, or typed routes."),
    'NAV-004': ('extra-hard-cast', 'medium',
                "`state.extra` (or route `arguments`) is force-cast to a non-nullable type. `extra` is absent on deep "
                "links, web refresh/back and process restoration, so the cast throws. Pass an id in the path and load "
                "the object, or handle null."),
    'NAV-005': ('untrusted-url-launch', 'medium',
                "launchUrl/launchUrlString receives a URL from a deep link, route parameter, notification payload, "
                "markup link or text field, with no scheme/host check. Allow-list schemes (https, mailto ...) and "
                "hosts before launching."),
    'NAV-006': ('sensitive-data-in-route', 'high',
                "A token, password, secret or PII (email, phone) is placed in a route path or query string. URLs "
                "land in browser history, route logs, analytics screen views and crash breadcrumbs."),
    'NAV-007': ('io-in-redirect', 'medium',
                "A redirect/onEnter callback performs I/O (storage, network, token refresh). It runs on every "
                "navigation and every refresh, which adds latency to each tap and turns I/O failures into routing "
                "errors. Keep auth state in memory and feed the router through refreshListenable."),
    'NAV-008': ('router-recreated', 'medium',
                "The GoRouter is constructed inside build() or inside a provider that ref.watch()es state. Each "
                "rebuild (or hot reload) creates a new router and resets the navigation stack to initialLocation."),
    'NAV-009': ('multiple-routers', 'low',
                "More than one GoRouter is constructed in lib/. One app should have one router (one source of truth "
                "for the URL); nested navigation belongs in ShellRoute/StatefulShellRoute."),
    'NAV-010': ('missing-auth-guard', 'medium',
                "The app has a sign-in route but no redirect/onEnter guard anywhere, so protected routes are only "
                "guarded per screen (or not at all) and deep links bypass the check."),
    'NAV-011': ('debug-log-diagnostics-in-release', 'low',
                "`debugLogDiagnostics: true` is not gated by kDebugMode. go_router then logs every location, including "
                "query parameters, through package:logging in release builds as well."),
    'NAV-012': ('redirect-without-refresh', 'medium',
                "A top-level redirect reads auth state but the router has no refreshListenable (and nothing calls "
                "router.refresh()). After sign-out the user stays on protected screens until the next navigation."),
}

FIX_BY_PROFILE = {
    'mvn': "MVN: keep auth in a notifier; build the router once in a keepAlive provider that ref.listen()s the "
           "notifier into a ValueNotifier used as refreshListenable; one-time navigation via ref.listen in the view.",
    'riverpod': "Riverpod: build the router once in a keepAlive provider; ref.listen auth into a ValueNotifier "
                "refreshListenable and ref.read inside redirect.",
    'mvvm': "MVVM: make the auth repository a Listenable and pass it as refreshListenable (Compass app); views "
            "navigate after a command completes.",
    'bloc': "Bloc: pass the auth bloc to the router factory and wrap bloc.stream in a ChangeNotifier for "
            "refreshListenable; one-time navigation in BlocListener.",
    'provider': "Provider: pass the auth ChangeNotifier as refreshListenable and read it in redirect.",
    'getx': "GetX: guard with GetMiddleware.redirect and clear the stack with Get.offAllNamed on sign-out.",
    'mvc': "MVC: the auth model is a Listenable passed as refreshListenable; the view navigates after the controller call.",
    'setstate': "setState: hold the auth ChangeNotifier above MaterialApp.router and pass it as refreshListenable.",
    'unknown': "Guard in the router (redirect/onEnter + refreshListenable), not in each screen.",
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
NAV_VERBS = r'(?:go|push|pushReplacement|replace|pushNamed|goNamed|pushReplacementNamed|replaceNamed)'
SECRET_NAMES = re.compile(r'^(?:access_?token|refresh_?token|id_?token|auth_?token|bearer|jwt|password|passwd|pwd|'
                          r'pass_?code|secret|client_?secret|api_?key|private_?key|cvv|cvc|card_?number|pan|ssn)$', re.I)
TOKEN_NAMES = re.compile(r'^(?:token|otp|pin|session_?id|session_?token|sid|magic_?token|reset_?token|verification_?code)$', re.I)
PII_NAMES = re.compile(r'^(?:email|e_?mail|email_?address|phone|phone_?number|mobile|msisdn|national_?id|iban|dob|'
                       r'date_?of_?birth)$', re.I)
PARAM_SRC = re.compile(r'\b(?:pathParameters|queryParameters|queryParametersAll)\s*\[|\bpathSegments\s*\[')
UNTRUSTED_URL_SRC = re.compile(r'\b(?:pathParameters|queryParameters|queryParametersAll|pathSegments)\s*\[|'
                               r'\bstate\s*\.\s*(?:uri|extra)\b|\.extra\b|\bhref\b|\bpayload\b|\bremoteMessage\b|'
                               r'\bmessage\s*\.\s*data\b|\bnotification\w*\s*\.\s*(?:data|payload)\b|'
                               r'\w*[cC]ontroller\s*\.\s*text\b|\b(?:initialLink|initialUri|initialAppLink)\b|'
                               r'\bgetInitial(?:Link|Uri|AppLink)\b|\buriLinkStream\b|\bdeepLink\b')
URL_CHECK = re.compile(r'\.\s*scheme\b|\bisScheme\s*\(|\.\s*host\b|\ballowed\w*\b|\ballowList\w*|\bwhitelist\w*|'
                       r'\btrusted\w*(?:Host|Scheme|Domain)s?\b|startsWith\s*\(\s*[\'"]https?:', re.I)
REDIRECT_IO = re.compile(r'SharedPreferences\s*\.\s*getInstance\s*\(|\bSharedPreferencesAsync\s*\(|'
                         r'\bFlutterSecureStorage\s*\(|\.\s*read\s*\(\s*key\s*:|\bhttp\s*\.\s*(?:get|post|put|patch|'
                         r'delete|head|read)\s*\(|\bDio\s*\(|\b_?dio\s*\.\s*(?:get|post|put|patch|delete|request|fetch)\b|'
                         r'FirebaseFirestore\s*\.\s*instance|\.\s*collection\s*\(|\bgetIdToken(?:Result)?\s*\(|'
                         r'\bopenDatabase\s*\(|\bHive\s*\.\s*openBox|\bSupabase\s*\.\s*instance\s*\.\s*client\s*\.\s*from\s*\(|'
                         r'\bcurrentUser\s*!?\??\s*\.\s*reload\s*\(|\bawait\s+[\w.()<>!?\s]*?\.\s*(?:fetch|refresh|sync|'
                         r'request|verify|validate)\w*\s*\(')
AUTH_WORDS = re.compile(r'\b(?:\w*[aA]uth\w*|is[lL]ogged\w*|[lL]ogged[iI]n|isSignedIn|[sS]igned[iI]n|currentUser|'
                        r'[sS]ession\w*|is[gG]uest|has[tT]oken|[aA]ccessToken|loginState|userState)\b')
STATE_LIKE_WATCH = re.compile(r'(?i)repositor|service|client|api\b|apiProvider|datasource|source|storage|database|'
                              r'\bdb|dio|http|prefs|preferences|config|env|flavor|analytics|logger')
LOGIN_SEG = re.compile(r'^(?:login|log-in|log_in|signin|sign-in|sign_in|auth|authenticate|authentication)$', re.I)
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'on', 'return', 'assert', 'super', 'this', 'new', 'await',
            'throw', 'else', 'do', 'try', 'when', 'in', 'is', 'as', 'yield', 'case', 'default', 'with', 'finally'}


# --------------------------------------------------------------------------- lexing

def _ident(text, i):
    return 0 <= i < len(text) and (text[i].isalnum() or text[i] in '_$')


def lex(text):
    """Return (code, masked, comments, strings): comments blanked; masked also blanks string contents."""
    n = len(text)
    code, masked = list(text), list(text)
    comments, strings = [], []

    def blank(buf, s, e):
        for k in range(s, e):
            if buf[k] != '\n':
                buf[k] = ' '

    def skip_block(i):
        depth, i = 1, i + 2
        while i < n and depth:
            if text.startswith('/*', i):
                depth, i = depth + 1, i + 2
            elif text.startswith('*/', i):
                depth, i = depth - 1, i + 2
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
            dl = 3 if text.startswith(text[p] * 3, p) else 1
            blank(masked, p + dl, max(p + dl, j - dl))
            strings.append((i, j))
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


STR_LIT = re.compile(r'''(r?)(?:'([^'\\\n]*(?:\\.[^'\\\n]*)*)'|"([^"\\\n]*(?:\\.[^"\\\n]*)*)")''')
CLASS_RE = re.compile(r'\b(?:class|mixin|enum|extension)\s+([A-Za-z_]\w*)?[^{;()]*?\{')
SUPPRESS_RE = re.compile(r'nav-ignore(-file)?\s*:\s*((?:NAV-\d{3})(?:\s*,\s*NAV-\d{3})*)\s*(.*)')


class DartFile(object):
    def __init__(self, root, rel):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.masked, self.comments, self.strings = lex(self.raw)
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.lines = self.raw.split('\n')
        self.parens = match_pairs(self.masked, '(', ')')
        self.paren_open = dict((v, k) for k, v in self.parens.items())
        self.braces = match_pairs(self.masked, '{', '}')
        self.brace_opens = sorted(self.braces)
        self.parent = {}
        stack = []
        for o in self.brace_opens:
            while stack and self.braces[stack[-1]] < o:
                stack.pop()
            self.parent[o] = stack[-1] if stack else None
            stack.append(o)
        self.classes = []
        for cm in CLASS_RE.finditer(self.masked):
            o = cm.end() - 1
            if o in self.braces:
                self.classes.append((cm.group(1) or '', o, self.braces[o], self.masked[cm.start():o]))
        self.class_opens = set(c[1] for c in self.classes)
        self.layer, self.role, self.feature = 'other', 'other', None
        self.suppress_line, self.suppress_file = {}, {}
        for s, e in self.comments:
            sm = SUPPRESS_RE.search(self.raw[s:e])
            if not sm:
                continue
            ids = [x.strip() for x in sm.group(2).split(',')]
            reason = sm.group(3).strip().rstrip('*/').strip() or '(no reason given)'
            for i in ids:
                if sm.group(1):
                    self.suppress_file[i] = reason
                else:
                    self.suppress_line.setdefault(self.line_of(s), {})[i] = reason

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def line_text(self, ln):
        return self.lines[ln - 1].strip() if 0 < ln <= len(self.lines) else ''

    def innermost_brace(self, pos):
        k = bisect.bisect_left(self.brace_opens, pos) - 1
        if k < 0:
            return None
        o = self.brace_opens[k]
        while o is not None and not (o < pos < self.braces.get(o, -1)):
            o = self.parent.get(o)
        return o

    def class_at(self, pos):
        best = None
        for name, o, c, hdr in self.classes:
            if o < pos < c and (best is None or o > best[1]):
                best = (name, o, c, hdr)
        return best

    def is_function_brace(self, o):
        """True if the `{` at o opens a function, method, getter or closure body."""
        m = self.masked
        i = o - 1
        while i >= 0 and m[i] in ' \t\n':
            i -= 1
        for kw in ('async*', 'async', 'sync*'):
            if m[max(0, i - len(kw) + 1):i + 1] == kw:
                i -= len(kw)
                while i >= 0 and m[i] in ' \t\n':
                    i -= 1
                break
        if i >= 0 and m[i] == ')':
            po = self.paren_open.get(i)
            if po is None:
                return False
            j = po - 1
            while j >= 0 and m[j] in ' \t\n':
                j -= 1
            e = j + 1
            while j >= 0 and _ident(m, j):
                j -= 1
            return m[j + 1:e] not in KEYWORDS
        e = i + 1
        while i >= 0 and _ident(m, i):
            i -= 1
        word = m[i + 1:e]
        if word in ('else', 'try', 'do', 'finally'):
            return False
        j = i
        while j >= 0 and m[j] in ' \t\n':
            j -= 1
        k = j
        while k >= 0 and _ident(m, k):
            k -= 1
        return m[k + 1:j + 1] == 'get'

    def func_scope(self, pos):
        """(start, end) of the innermost enclosing function/closure body (block or arrow)."""
        o = self.innermost_brace(pos)
        scope = None
        while o is not None:
            if o in self.class_opens:
                break
            if self.is_function_brace(o):
                scope = (o, self.braces[o])
                break
            o = self.parent.get(o)
        if scope is None:
            scope = self.top_statement(pos)
        m = self.masked
        k = pos
        while True:
            k = m.rfind('=>', scope[0], k)
            if k < 0:
                break
            end = expr_end(m, k + 2)
            if end >= pos:
                return k + 2, end
        return scope

    def top_statement(self, pos):
        """(start, end) of the top-level declaration containing pos."""
        o = self.innermost_brace(pos)
        outer = None
        while o is not None:
            outer = o
            o = self.parent.get(o)
        m = self.masked
        if outer is not None:
            s = outer
            while s > 0 and m[s - 1] not in ';}':
                s -= 1
            e = self.braces[outer] + 1
            j = e
            while j < len(m) and m[j] in ' \t\n':
                j += 1
            if j < len(m) and m[j] in ';)':
                e = j + 1
            return s, e
        s = pos
        while s > 0 and m[s - 1] not in ';}':
            s -= 1
        e = m.find(';', pos)
        return s, (len(m) if e < 0 else e + 1)

    def enclosing_method_name(self, pos):
        """Name of the innermost named function/method whose body contains pos."""
        o = self.innermost_brace(pos)
        while o is not None:
            if o in self.class_opens:
                return None
            if self.is_function_brace(o):
                m = self.masked
                i = o - 1
                while i >= 0 and m[i] in ' \t\n':
                    i -= 1
                if m[i] == ')':
                    po = self.paren_open.get(i)
                    if po is not None:
                        j = po - 1
                        while j >= 0 and m[j] in ' \t\n':
                            j -= 1
                        e = j + 1
                        while j >= 0 and _ident(m, j):
                            j -= 1
                        name = m[j + 1:e]
                        if name:
                            return name
            o = self.parent.get(o)
        return None


def expr_end(m, i):
    n, depth = len(m), 0
    while i < n:
        c = m[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return i
            depth -= 1
        elif c in ';,' and depth == 0:
            return i
        i += 1
    return n


def split_args(df, po):
    """Top-level arguments of the call whose `(` is at po: list of (name|None, start, end)."""
    pc = df.parens.get(po)
    if pc is None:
        return []
    m, out, i = df.masked, [], po + 1
    while i < pc:
        while i < pc and m[i] in ' \t\n,':
            i += 1
        if i >= pc:
            break
        e = expr_end(m, i)
        e = min(e, pc)
        seg = m[i:e]
        nm = re.match(r'\s*([A-Za-z_$][\w$]*)\s*:(?!:)', seg)
        if nm:
            out.append((nm.group(1), i + nm.end(), e))
        else:
            out.append((None, i, e))
        i = e + 1
    return out


def arg(df, po, name):
    for n, s, e in split_args(df, po):
        if n == name:
            return s, e
    return None


def find_calls(df, name_re):
    """Yield (match, open_paren) for `Name(` / `Name<T>(` / `Name.ctor(` calls (not declarations)."""
    m = df.masked
    for mm in re.finditer(r'(?<![\w$.])(?:' + name_re + r')\s*(?:<[^<>;{}()]*(?:<[^<>;{}()]*>[^<>;{}()]*)*>)?\s*\(', m):
        po = mm.end() - 1
        if po in df.parens:
            prev = m[max(0, mm.start() - 12):mm.start()]
            if re.search(r'\b(?:class|extends|implements|with|factory)\s+$', prev):
                continue
            cls = df.class_at(mm.start())
            if cls and cls[0] and cls[0] == re.match(r'\w+', mm.group(0)).group(0):
                continue          # the class's own constructor declaration
            yield mm, po


def callback_body(df, s, e, funcs):
    """Body span(s) of a callback argument: inline closure, or a named function resolved via funcs."""
    m = df.masked
    txt = m[s:e].strip()
    if not txt:
        return []
    k = s + (len(m[s:e]) - len(m[s:e].lstrip()))
    if m[k] == '(':
        pc = df.parens.get(k)
        if pc is None:
            return []
        j = pc + 1
        while j < e and m[j] in ' \t\n':
            j += 1
        if m.startswith('async', j):
            j += 5
            while j < e and m[j] in ' \t\n*':
                j += 1
        if j < e and m[j] == '{' and j in df.braces:
            return [(df, j, df.braces[j])]
        if m[j:j + 2] == '=>':
            return [(df, j + 2, e)]
        return []
    ident = re.match(r'([A-Za-z_$][\w$]*)(?:\s*\.\s*([A-Za-z_$][\w$]*))?\s*$', txt)
    if ident:
        name = ident.group(2) or ident.group(1)
        return funcs.get(name, [])
    return []


# --------------------------------------------------------------------------- project model

CONST_DECL = re.compile(r'(?:\b(?:static|const|final)\s+)+(?:String\s+)?([A-Za-z_$][\w$]*)\s*=\s*'
                        r'((?:r?(?:\'[^\'\n]*\'|"[^"\n]*")\s*)+);|'
                        r'\bstatic\s+(?:const\s+|final\s+)?String\s+([A-Za-z_$][\w$]*)\s*=\s*'
                        r'((?:r?(?:\'[^\'\n]*\'|"[^"\n]*")\s*)+);|'
                        r'\bstatic\s+String\s+get\s+([A-Za-z_$][\w$]*)\s*=>\s*((?:r?(?:\'[^\'\n]*\'|"[^"\n]*")\s*)+);')
FUNC_DEF = re.compile(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(')


class Project(object):
    def __init__(self, files, pubspec):
        self.files = files
        self.pubspec = pubspec
        self.deps = set(re.findall(r'^\s{2}([A-Za-z_]\w*)\s*:', pubspec, re.M))
        self.consts = {}           # name -> raw literal text (None when ambiguous)
        self.const_owner = {}      # name -> (class, file)
        self.funcs = {}            # function name -> [(df, body_start, body_end)]
        self.router_factories = set()
        for df in files:
            self._collect(df)

    def _collect(self, df):
        code = df.code
        for cm in CONST_DECL.finditer(code):
            name = cm.group(1) or cm.group(3) or cm.group(5)
            lit = cm.group(2) or cm.group(4) or cm.group(6)
            cls = df.class_at(cm.start())
            keys = [name] + (['%s.%s' % (cls[0], name)] if cls and cls[0] else [])
            for k in keys:
                if k in self.consts and self.consts[k] != lit:
                    self.consts[k] = None
                else:
                    self.consts[k] = lit
                    self.const_owner[k] = (cls[0] if cls else '', df.rel)
        m = df.masked
        for fm in FUNC_DEF.finditer(m):
            po = fm.end() - 1
            pc = df.parens.get(po)
            if pc is None or fm.group(1) in KEYWORDS:
                continue
            j = pc + 1
            while j < len(m) and m[j] in ' \t\n':
                j += 1
            for kw in ('async*', 'async', 'sync*'):
                if m.startswith(kw, j):
                    j += len(kw)
                    while j < len(m) and m[j] in ' \t\n':
                        j += 1
                    break
            if j < len(m) and m[j] == '{' and j in df.braces:
                body = (df, j, df.braces[j])
            elif m.startswith('=>', j):
                body = (df, j + 2, expr_end(m, j + 2))
            else:
                continue
            before = m[max(0, fm.start() - 80):fm.start()]
            if re.search(r'[=(,:?]\s*$', before) or re.search(r'\breturn\s*$', before):
                continue          # a call or a closure argument, not a declaration
            self.funcs.setdefault(fm.group(1), []).append(body)
            if re.search(r'\bGoRouter\s*$', before) and re.search(r'(?<![\w$.])GoRouter(?:\.routingConfig)?\s*\(',
                                                                   m[body[1]:body[2]]):
                self.router_factories.add(fm.group(1))

    def literal_value(self, lit, depth=0):
        """Concatenate adjacent string literals and resolve $name / ${A.b} interpolation."""
        parts = []
        for sm in STR_LIT.finditer(lit):
            s = sm.group(2) if sm.group(2) is not None else sm.group(3)
            if sm.group(1):
                parts.append(s)
                continue

            def sub(mm):
                key = mm.group(1) or mm.group(2)
                v = self.resolve_name(key, depth + 1)
                if v is None:
                    raise ValueError(key)
                return v
            try:
                parts.append(re.sub(r'\$\{\s*([A-Za-z_$][\w$.]*)\s*\}|\$([A-Za-z_][\w]*)', sub, s))
            except ValueError:
                return None
        return ''.join(parts)

    def resolve_name(self, key, depth=0):
        if depth > 6:
            return None
        lit = self.consts.get(key)
        if lit is None and '.' in key:
            lit = self.consts.get(key.split('.')[-1])
        if lit is None:
            return None
        return self.literal_value(lit, depth)

    def resolve_expr(self, text):
        t = text.strip()
        if not t:
            return None
        if re.match(r'''^(?:r?(?:'[^'\n]*'|"[^"\n]*")\s*)+$''', t):
            return self.literal_value(t)
        if re.match(r'^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?$', t):
            return self.resolve_name(t)
        return None


# --------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, project, profile):
        self.p = project
        self.profile = profile
        self.findings, self.suppressed = [], []
        self._seen = set()

    def report(self, df, pos_or_line, rid, evidence, note='', severity=None, by_line=False):
        ln = pos_or_line if by_line else df.line_of(pos_or_line)
        key = (rid, df.rel, ln)
        if key in self._seen:
            return
        self._seen.add(key)
        sev = severity or RULES[rid][1]
        reason = df.suppress_file.get(rid)
        if reason is None:
            for cand in (ln, ln - 1):
                if rid in df.suppress_line.get(cand, {}):
                    reason = df.suppress_line[cand][rid]
                    break
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': df.rel, 'line': ln, 'reason': reason})
            return
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': ' '.join(evidence.split())[:160], 'message': RULES[rid][2],
                              'note': note})

    def snippet(self, df, s, e, limit=110):
        t = ' '.join(df.code[s:e].split())
        return t if len(t) <= limit else t[:limit - 3] + '...'

    # ---------------------------------------------------------------- route table
    def collect_routes(self):
        p = self.p
        sub_names = set()
        for df in p.files:
            for mm in re.finditer(r'\bclass\s+(\w+)[^{]*?\bextends\s+GoRoute\b(?!Data)', df.masked):
                sub_names.add(mm.group(1))
        names = ['GoRoute'] + sorted(sub_names)
        self.routes = []      # dicts: df, pos, raw, path(own), full, parent
        self.unresolved = 0
        for df in p.files:
            calls = []
            for mm, po in find_calls(df, '|'.join(re.escape(n) for n in names)):
                callee = re.match(r'\w+', mm.group(0)).group(0)
                encl = df.class_at(mm.start())
                if encl and encl[0] == callee:
                    continue          # the subclass's own constructor declaration
                a = arg(df, po, 'path')
                if a is None and mm.group(0).split('(')[0].strip() in sub_names:
                    pos_args = [x for x in split_args(df, po) if x[0] is None]
                    a = (pos_args[0][1], pos_args[0][2]) if pos_args else None
                if a is None:
                    continue
                raw = df.code[a[0]:a[1]].strip()
                val = p.resolve_expr(raw)
                calls.append({'df': df, 'pos': mm.start(), 'po': po, 'pc': df.parens[po], 'raw': raw, 'path': val,
                              'case_insensitive': bool(re.search(r'caseSensitive\s*:\s*false',
                                                                 df.masked[po:df.parens[po]]))})
            for c in calls:
                parent = None
                for o in calls:
                    if o is not c and o['po'] < c['po'] and c['pc'] < o['pc']:
                        if parent is None or o['po'] > parent['po']:
                            parent = o
                c['parent'] = parent
            for c in calls:
                c['full'] = self._full(c)
                if c['full'] is None:
                    self.unresolved += 1
            self.routes.extend(calls)
        # typed routes (annotation trees)
        self.typed = []
        for df in p.files:
            for mm, po in find_calls(df, r'TypedGoRoute|TypedRelativeGoRoute'):
                a = arg(df, po, 'path')
                if a:
                    self.typed.append({'df': df, 'pos': mm.start(), 'raw': df.code[a[0]:a[1]].strip(),
                                       'path': p.resolve_expr(df.code[a[0]:a[1]])})

    def _full(self, c, depth=0):
        if c['path'] is None or depth > 20:
            return None
        path = c['path']
        if path.startswith('/'):
            return path
        par = c['parent']
        if par is None:
            return None
        base = self._full(par, depth + 1)
        if base is None:
            return None
        return (base.rstrip('/') + '/' + path).replace('//', '/')

    # ---------------------------------------------------------------- rules
    def run(self):
        p = self.p
        self.uses_go_router = 'go_router' in p.deps or any('package:go_router/' in f.code for f in p.files)
        self.collect_routes()
        self.router_calls = []
        for df in p.files:
            for mm, po in find_calls(df, r'GoRouter(?:\s*\.\s*routingConfig)?'):
                self.router_calls.append((df, mm.start(), po))
        self.rule_duplicate_paths()
        self.rule_raw_paths()
        for df in p.files:
            self.rule_unvalidated_params(df)
            self.rule_extra_cast(df)
            self.rule_url_launch(df)
            self.rule_sensitive_nav(df)
            self.rule_debug_log(df)
        self.rule_sensitive_templates()
        self.rule_redirects()
        self.rule_router_lifecycle()
        self.rule_auth_guard()

    def rule_duplicate_paths(self):
        trees = {}
        for df in self.p.files:
            trees[df.rel] = [(po, df.parens[po]) for _, po in find_calls(
                df, r'GoRouter(?:\s*\.\s*routingConfig)?|RoutingConfig')]
        cond_re = re.compile(r'(?:\bif\s*\((?:[^()]|\([^()]*\))*\)|\belse)\s*$')
        seen = {}
        for c in self.routes:
            if c['full'] is None:
                continue
            key = re.sub(r':\w+', ':', c['full'].rstrip('/') or '/')
            if c['case_insensitive']:
                key = key.lower()
            m = c['df'].masked
            c['conditional'] = bool(cond_re.search(m[max(0, c['pos'] - 300):c['pos']]))
            encl = [t for t in trees.get(c['df'].rel, []) if t[0] < c['po'] < t[1]]
            c['tree'] = (c['df'].rel, max(encl)[0]) if encl else None
            first = None
            for o in seen.get(key, []) + seen.get(key.lower(), []):
                if o['tree'] is None or c['tree'] is None or o['tree'] == c['tree']:
                    if not (o['conditional'] and c['conditional']):
                        first = o
                        break
            seen.setdefault(key, []).append(c)
            if c['case_insensitive'] and key.lower() != key:
                seen.setdefault(key.lower(), []).append(c)
            if first is None:
                continue
            self.report(c['df'], c['pos'], 'NAV-001', 'path %s (%s) duplicates %s:%d' % (
                c['raw'], c['full'], first['df'].rel, first['df'].line_of(first['pos'])),
                note='the later route never matches; rename it or merge the two routes')

    def rule_raw_paths(self):
        p = self.p
        route_consts = {}
        for k, lit in p.consts.items():
            if lit is None or '.' in k:
                continue
            v = p.literal_value(lit)
            owner = p.const_owner.get(k, ('', ''))[0]
            if v and v.startswith('/') and re.search(r'(?i)route|path|screen|page|nav|location|link', owner + k):
                route_consts.setdefault(v, '%s.%s' % (owner, k) if owner else k)
        has_typed = bool(self.typed)
        named = []
        for c in self.routes:
            a = arg(c['df'], c['po'], 'name')
            if a and c['full']:
                pat = re.sub(r':\w+(?:\((?:\\.|[^\\()])+\))?', '[^/]+', re.escape(c['full']).replace('\\:', ':'))
                named.append((re.compile('^' + pat + '/?$'), c['df'].code[a[0]:a[1]].strip(), c['df'].rel))
        # several routers in different files (e.g. an examples folder): only trust same-file evidence
        multi = len(set(d.rel for d, _, _ in self.router_calls)) > 1
        typed_files = set(t['df'].rel for t in self.typed)
        use_consts = len(route_consts) >= 2
        if not (use_consts or has_typed or named):
            return
        nav_re = re.compile(r'(?<![\w$])(?:context|router|_router|appRouter|goRouter|_goRouter|\w*[Rr]outer|'
                            r'GoRouter\s*\.\s*of\s*\(\s*\w+\s*\))\s*\.\s*(?:go|push|pushReplacement|replace)'
                            r'\s*(?:<[^>]*>)?\s*\(\s*|'
                            r'\bNavigator\s*\.\s*(?:of\s*\(\s*\w+\s*\)\s*\.\s*)?(?:pushNamed|pushReplacementNamed|'
                            r'pushNamedAndRemoveUntil|popAndPushNamed|restorablePushNamed)\s*(?:<[^>]*>)?\s*\(\s*'
                            r'(?:\w+\s*,\s*)?|'
                            r'\bGet\s*\.\s*(?:toNamed|offNamed|offAllNamed|offAndToNamed|offNamedUntil)\s*(?:<[^>]*>)?\s*\(\s*')
        for df in p.files:
            for mm in nav_re.finditer(df.masked):
                q = mm.end()
                if q >= len(df.code) or df.code[q] not in '\'"':
                    continue
                lm = STR_LIT.match(df.code, q)
                if not lm:
                    continue
                val = lm.group(2) if lm.group(2) is not None else lm.group(3)
                if not val.startswith('/'):
                    continue
                plain = val.split('?')[0]
                hint = route_consts.get(plain)
                if hint:
                    note = 'use %s' % hint
                elif use_consts:
                    note = 'use the route constant (add one if missing)'
                elif has_typed and (not multi or df.rel in typed_files):
                    note = 'use the typed route (XRoute(...).go(context))'
                else:
                    match = next((nm for rx, nm, rel in named if rx.match(plain) and (not multi or rel == df.rel)),
                                 None)
                    if match is None:
                        continue      # only some routes are named; this one is not
                    note = 'the route is named: goNamed(%s)' % match
                self.report(df, mm.start(), 'NAV-002', self.snippet(df, mm.start(), lm.end() + 1), note=note)

    def rule_unvalidated_params(self, df):
        m, code = df.masked, df.code
        if not PARAM_SRC.search(m):
            return
        constrained = set()
        for c in self.routes + self.typed:
            if c['path']:
                constrained.update(re.findall(r':(\w+)\(', c['path']))
        scopes = {}

        def tainted(scope):
            if scope in scopes:
                return scopes[scope]
            names = set()
            s, e = scope
            for am in re.finditer(r'(?<![\w$.])([A-Za-z_]\w*)\s*=(?![=>])', m[s:e]):
                rs = s + am.end()
                rhs = m[rs:expr_end(m, rs)]
                if PARAM_SRC.search(rhs) or re.search(r'\bstate\s*\.\s*uri\b|\buri\s*\.\s*pathSegments\b', rhs) or \
                        any(re.search(r'(?<![\w$.])%s(?![\w$])' % re.escape(n), rhs) for n in names):
                    names.add(am.group(1))
            scopes[scope] = names
            return names

        def key_of(txt):
            km = re.search(r'(?:pathParameters|queryParameters)\s*\[\s*[\'"](\w+)[\'"]', txt)
            return km.group(1) if km else None

        # parse calls
        for pm in re.finditer(r'(?<![\w$.])(?:int|double|num|BigInt|DateTime)\s*\.\s*parse\s*\(|'
                              r'\.\s*values\s*\.\s*byName\s*\(', m):
            po = pm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            argtxt = m[po + 1:pc]
            scope = df.func_scope(pm.start())
            hit = PARAM_SRC.search(argtxt) or any(
                re.search(r'(?<![\w$.])%s(?![\w$])' % re.escape(n), argtxt) for n in tainted(scope))
            if not hit:
                continue
            k = key_of(code[po + 1:pc])
            if k and k in constrained:
                continue
            self.report(df, pm.start(), 'NAV-003', self.snippet(df, pm.start(), pc + 1),
                        note='a malformed link throws inside the route builder; use tryParse (or asNameMap()[v]) '
                             'with a fallback or a NotFound page, a path regex like :id(\\d+), or a typed route')
        # forced query parameters
        for qm in re.finditer(r'\bqueryParameters\s*\[[^\]\n]*\]\s*(?:!(?![=.])|as\s+(?:String|int)\b(?!\s*\?))', m):
            self.report(df, qm.start(), 'NAV-003', self.snippet(df, qm.start(), qm.end()),
                        note='query parameters are optional by nature; a link without it throws. Read it as nullable '
                             'and fall back')
        # unchecked pathSegments index
        for sm in re.finditer(r'\bpathSegments\s*\[\s*\d+\s*\]', m):
            s, e = df.func_scope(sm.start())
            if re.search(r'pathSegments\s*\.\s*(?:length|isEmpty|isNotEmpty)|elementAtOrNull', m[s:e]):
                continue
            self.report(df, sm.start(), 'NAV-003', self.snippet(df, sm.start(), sm.end()),
                        note='check pathSegments.length first (or use elementAtOrNull); a short link throws RangeError')
        # unchecked redirect target taken from the query string
        for gm in re.finditer(r'(?<![\w$])(?:context|router|_router|\w*[Rr]outer)\s*\.\s*(?:go|push|replace|'
                              r'pushReplacement)\s*\(\s*', m):
            a_end = expr_end(m, gm.end())
            argtxt = m[gm.end():a_end]
            scope = df.func_scope(gm.start())
            src = re.search(r'queryParameters\s*\[', argtxt) or any(
                re.fullmatch(r'\s*%s\s*(?:\?\?.*)?' % re.escape(n), argtxt, re.S) for n in tainted(scope))
            if not src:
                continue
            s, e = scope
            if re.search(r'startsWith\s*\(\s*[\'"]/|\bisAbsolute\b|\.\s*hasScheme\b|\ballowed\w*|\bisSafe\w*|'
                         r'\bvalidat\w*|\bsanitiz\w*', m[s:e] + code[s:e]):
                continue
            self.report(df, gm.start(), 'NAV-003', self.snippet(df, gm.start(), a_end + 1), severity='low',
                        note='redirect target from the query string: accept only an in-app path (starts with "/", not '
                             '"//") that matches a known route')

    def rule_extra_cast(self, df):
        m = df.masked
        uses_gr = 'package:go_router/' in df.code or 'GoRouterState' in df.masked
        for em in re.finditer(r'\.\s*(extra|arguments)\b\s*(!(?!=))?\s*(?:as\s+([A-Za-z_][\w.]*(?:\s*<[^;(){}]*?>)?)(\s*\?)?)?', m):
            kind, bang, typ, nullable = em.group(1), em.group(2), em.group(3), em.group(4)
            if not (bang or typ):
                continue
            if typ and (nullable or typ in ('dynamic', 'Object')) and not bang:
                continue
            before = m[max(0, em.start() - 40):em.start()]
            if kind == 'arguments' and not re.search(r'settings\s*$|ModalRoute\s*\.\s*of\s*\([^)]*\)\s*[!?]?\s*$', before):
                continue
            if kind == 'extra' and not uses_gr:
                continue
            s, e = df.func_scope(em.start())
            body = m[s:e]
            if re.search(r'\.\s*%s\s*(?:is\b|==\s*null|!=\s*null|\?\?|case\b)' % kind, body) or \
                    re.search(r'\bis\s+%s\b' % re.escape(typ or '~'), body):
                continue
            self.report(df, em.start(), 'NAV-004', self.snippet(df, max(s, em.start() - 30), em.end()),
                        note=('Navigator arguments are absent when the route is opened by name from a deep link or a '
                              'web refresh' if kind == 'arguments' else
                              'extra is not part of the URL: deep links, web refresh/back and restoration arrive with '
                              'extra == null (or undecoded without an extraCodec)'))

    def rule_url_launch(self, df):
        m = df.masked
        if 'launch' not in m:
            return
        imports_launcher = 'package:url_launcher/' in df.code
        for lm in re.finditer(r'(?<![\w$.])(launchUrl|launchUrlString|launch)\s*\(', m):
            if lm.group(1) == 'launch' and not imports_launcher:
                continue
            po = lm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            args = split_args(df, po)
            if not args or args[0][0] is not None:
                continue
            a = m[args[0][1]:args[0][2]]
            scope = df.func_scope(lm.start())
            s, e = scope
            body = m[s:e]
            src = UNTRUSTED_URL_SRC.search(a)
            if not src:
                ident = re.findall(r'(?<![\w$.])([A-Za-z_]\w*)', a)
                for name in ident:
                    for am in re.finditer(r'(?<![\w$.])%s\s*=(?![=>])' % re.escape(name), body):
                        rs = s + am.end()
                        if UNTRUSTED_URL_SRC.search(m[rs:expr_end(m, rs)]):
                            src = True
                            break
                    if src:
                        break
            if not src or URL_CHECK.search(body):
                continue
            self.report(df, lm.start(), 'NAV-005', self.snippet(df, lm.start(), pc + 1),
                        note='parse with Uri.tryParse, then allow only expected schemes (https, mailto, tel) and hosts; '
                             'never launch javascript:, file:, intent: or unknown custom schemes from outside input')

    def _sensitive_class(self, name):
        leaf = re.split(r'[.\s]', name.strip())[-1].lstrip('_')
        if SECRET_NAMES.match(leaf):
            return 'high', 'secret'
        if TOKEN_NAMES.match(leaf):
            return 'medium', 'token'
        if PII_NAMES.match(leaf):
            return 'medium', 'pii'
        return None, None

    def rule_sensitive_templates(self):
        for c in self.routes + self.typed:
            val = c['path'] or ''
            for name in re.findall(r':(\w+)', val):
                sev, kind = self._sensitive_class(name)
                if sev:
                    self.report(c['df'], c['pos'], 'NAV-006', 'path %s declares :%s' % (c['raw'], name), severity=sev,
                                note=('PII in the URL; pass an opaque id and load the value'
                                      if kind == 'pii' else
                                      'an inbound one-time link may carry a token: consume it in redirect/onEnter, '
                                      'exchange it, then go() to a clean location'))
        for df in self.p.files:
            for cm in re.finditer(r'\bclass\s+\w+[^{;]*\bextends\s+(?:GoRouteData|RelativeGoRouteData)\b[^{;]*\{', df.masked):
                o = cm.end() - 1
                body = df.masked[o:df.braces.get(o, o)]
                for fm in re.finditer(r'\bfinal\s+[\w<>?]+\s+(\w+)\s*;', body):
                    sev, kind = self._sensitive_class(fm.group(1))
                    if sev:
                        self.report(df, o + fm.start(), 'NAV-006', self.snippet(df, o + fm.start(), o + fm.end()),
                                    severity=sev, note='typed-route fields become path or query parameters')

    def rule_sensitive_nav(self, df):
        m, code = df.masked, df.code
        nav = re.compile(r'(?<![\w$])(?:context|router|_router|\w*[Rr]outer|GoRouter\s*\.\s*of\s*\(\s*\w+\s*\)|'
                         r'Navigator(?:\s*\.\s*of\s*\(\s*\w+\s*\))?|Get)\s*\.\s*(?:go|push|pushReplacement|replace|'
                         r'goNamed|pushNamed|pushReplacementNamed|replaceNamed|namedLocation|pushNamedAndRemoveUntil|'
                         r'toNamed|offNamed|offAllNamed)\s*(?:<[^>]*>)?\s*\(')
        for nm in nav.finditer(m):
            po = nm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            args = split_args(df, po)
            pos_args = [a for a in args if a[0] is None]
            if nm.group(0).startswith('Navigator') and len(pos_args) > 1:
                pos_args = pos_args[1:]          # Navigator.pushNamed(context, location)
            hits = []
            if pos_args:
                txt = code[pos_args[0][1]:pos_args[0][2]]
                for im in re.finditer(r'\$\{\s*([\w.?!]+)\s*\}|\$([A-Za-z_]\w*)', txt):
                    hits.append((im.group(1) or im.group(2)).rstrip('!?'))
                for km in re.finditer(r'[?&](\w+)=', txt):
                    hits.append(km.group(1))
            for name, s, e in args:
                if name in ('queryParameters', 'pathParameters', 'parameters'):
                    for km in re.finditer(r'[\'"](\w+)[\'"]\s*:', code[s:e]):
                        hits.append(km.group(1))
            worst = None
            for h in hits:
                sev, kind = self._sensitive_class(h)
                if sev and (worst is None or SEV_ORDER[sev] < SEV_ORDER[worst[0]]):
                    worst = (sev, kind, h)
            if worst:
                self.report(df, nm.start(), 'NAV-006', self.snippet(df, nm.start(), pc + 1), severity=worst[0],
                            note='`%s` goes into the location; pass it in memory (state, repository) or exchange it '
                                 'for an opaque id' % worst[2])

    def rule_debug_log(self, df):
        for dm in re.finditer(r'\bdebugLogDiagnostics\s*:\s*true\b', df.masked):
            self.report(df, dm.start(), 'NAV-011', df.line_text(df.line_of(dm.start())),
                        note='use debugLogDiagnostics: kDebugMode')

    def _redirect_bodies(self):
        """[(df, pos_of_arg, kind, [(df, s, e)], router_call_po or None)]"""
        out = []
        for df in self.p.files:
            for mm, po in find_calls(df, r'GoRouter(?:\s*\.\s*routingConfig)?|RoutingConfig|GoRoute|ShellRoute|'
                                         r'StatefulShellRoute(?:\s*\.\s*indexedStack)?'):
                for kind in ('redirect', 'onEnter'):
                    a = arg(df, po, kind)
                    if a:
                        top = bool(re.match(r'GoRouter|RoutingConfig', mm.group(0)))
                        out.append((df, a[0], kind, callback_body(df, a[0], a[1], self.p.funcs),
                                    po if top else None))
            for cm in re.finditer(r'\bclass\s+\w+[^{;]*\bextends\s+(?:GoRouteData|RelativeGoRouteData)\b[^{;]*\{',
                                  df.masked):
                o = cm.end() - 1
                for rm in re.finditer(r'\bredirect\s*\(\s*BuildContext\b', df.masked[o:df.braces.get(o, o)]):
                    p0 = o + rm.end() - 1
                    p0 = df.masked.rfind('(', o, o + rm.end())
                    pc = df.parens.get(p0)
                    if pc is None:
                        continue
                    j = pc + 1
                    bodies = []
                    rest = df.masked[j:j + 30]
                    km = re.match(r'\s*(?:async\s*)?(\{|=>)', rest)
                    if km:
                        q = j + km.end() - 1
                        if km.group(1) == '{' and q in df.braces:
                            bodies = [(df, q, df.braces[q])]
                        elif km.group(1) == '=>':
                            bodies = [(df, q + 1, expr_end(df.masked, q + 1))]
                    out.append((df, o + rm.start(), 'redirect', bodies, None))
        return out

    def rule_redirects(self):
        self.guards = self._redirect_bodies()
        for df, pos, kind, bodies, _ in self.guards:
            for bdf, s, e in bodies:
                body = bdf.masked[s:e]
                io = REDIRECT_IO.search(body)
                if io:
                    self.report(bdf, s + io.start(), 'NAV-007', '%s: %s' % (kind, self.snippet(bdf, s + io.start(),
                                                                                              s + io.end() + 40, 90)),
                                note='read cached auth state (repository/notifier field) instead; refresh it outside '
                                     'the router and notify refreshListenable')
        # NAV-012: top-level redirect reading auth without refreshListenable
        refresh_called = any(re.search(r'(?:[Rr]outer|GoRouter\s*\.\s*of\s*\([^)]*\))\s*\.\s*refresh\s*\(\s*\)',
                                       f.masked) for f in self.p.files)
        for df, pos, kind, bodies, router_po in self.guards:
            if router_po is None or kind != 'redirect' or refresh_called:
                continue
            if arg(df, router_po, 'refreshListenable'):
                continue
            region = df.masked[slice(*df.top_statement(router_po))]
            if any(not STATE_LIKE_WATCH.search(w) for w in re.findall(r'\bref\s*\.\s*watch\s*\(([^;]*?)\)\s*[;.,)]', region)):
                continue          # NAV-008 covers the recreate-on-change design
            for bdf, s, e in bodies:
                body = bdf.masked[s:e]
                if re.search(r'\.\s*of\s*\(\s*context\s*\)|\bcontext\s*\.\s*watch\b|\bdependOnInheritedWidget', body):
                    continue
                if AUTH_WORDS.search(body):
                    self.report(df, pos, 'NAV-012', 'redirect: ' + self.snippet(bdf, s, e, 80),
                                note=FIX_BY_PROFILE.get(self.profile, FIX_BY_PROFILE['unknown']))
                    break

    def rule_router_lifecycle(self):
        p = self.p
        for df, pos, po in self.router_calls:
            if self.in_widget_build(df, pos):
                self.report(df, pos, 'NAV-008', df.line_text(df.line_of(pos)),
                            note='create it once: a top-level final, a field in State/initState, or a keepAlive provider')
                continue
            region = df.masked[slice(*df.top_statement(pos))]
            wm = None
            for cand in re.finditer(r'\bref\s*\.\s*watch\s*\(([^;]*?)\)\s*[;.,)]', region):
                if not STATE_LIKE_WATCH.search(cand.group(1)):
                    wm = cand
                    break
            if wm and re.search(r'@riverpod|@Riverpod|Provider\b', region):
                s0 = df.top_statement(pos)[0]
                self.report(df, s0 + wm.start(), 'NAV-008', self.snippet(df, s0 + wm.start(), s0 + wm.end() + 40),
                            note='ref.watch rebuilds the provider and the GoRouter on every change; ref.listen into a '
                                 'refreshListenable and ref.read inside redirect')
        if p.router_factories:
            names = '|'.join(re.escape(n) for n in sorted(p.router_factories))
            for df in p.files:
                for fm in re.finditer(r'(?<![\w$.])(?:%s)\s*\(' % names, df.masked):
                    if self.in_widget_build(df, fm.start()):
                        before = df.masked[max(0, fm.start() - 40):fm.start()]
                        if re.search(r'\bGoRouter\s*$', before):
                            continue
                        self.report(df, fm.start(), 'NAV-008',
                                    self.snippet(df, fm.start(), df.parens.get(fm.end() - 1, fm.end()) + 1),
                                    note='this factory returns a new GoRouter on every build(); hot reload and any '
                                         'rebuild reset the navigation stack. Create it once (State field or provider)')
        if len(self.router_calls) > 1:
            first = self.router_calls[0]
            locs = ', '.join('%s:%d' % (d.rel, d.line_of(ps)) for d, ps, _ in self.router_calls[:4])
            df, pos, _ = self.router_calls[1]
            self.report(df, pos, 'NAV-009', '%d GoRouter constructions: %s' % (len(self.router_calls), locs),
                        note='one router per app; flavors can share one factory. Ignore if these are separate apps')

    def in_widget_build(self, df, pos):
        if df.enclosing_method_name(pos) != 'build':
            return False
        cls = df.class_at(pos)
        return bool(cls and re.search(r'\bextends\s+(?:StatelessWidget|StatefulWidget|State\s*<|ConsumerWidget|'
                                      r'ConsumerState\s*<|HookWidget|HookConsumerWidget|StatelessHookWidget)', cls[3]))

    def rule_auth_guard(self):
        if not self.uses_go_router or self.profile == 'getx':
            return
        if self.guards:
            return
        for c in self.routes + self.typed:
            val = c['path'] or re.sub(r'''^r?['"]|['"]$''', '', c['raw'])
            segs = [s for s in val.split('/') if s and not s.startswith(':')]
            if segs and LOGIN_SEG.match(segs[-1]):
                self.report(c['df'], c['pos'], 'NAV-010', 'route %s, and no redirect/onEnter in the app' % c['raw'],
                            note=FIX_BY_PROFILE.get(self.profile, FIX_BY_PROFILE['unknown']))
                return


# --------------------------------------------------------------------------- driver

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
        return None, ('path-based fallback (flutter-architecture skill not installed: '
                      '../flutter-architecture/scripts/arch_check.py missing)')
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
    segs = rel.lower().split('/')
    dirs, stem = segs[1:-1], segs[-1][:-5]
    if re.match(r'main\w*$', stem) and len(segs) == 2 or any(s in ('router', 'routes', 'routing', 'di') for s in dirs):
        layer = 'app'
    elif 'domain' in dirs:
        layer = 'domain'
    elif 'data' in dirs:
        layer = 'data'
    elif any(s in ('presentation', 'ui', 'view', 'views', 'screens', 'pages', 'widgets') for s in dirs):
        layer = 'presentation'
    else:
        layer = 'other'
    if any(s in ('notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
                 'cubit', 'cubits', 'controller', 'controllers') for s in dirs) or \
            stem.endswith(('_notifier', '_view_model', '_viewmodel', '_bloc', '_cubit', '_controller')):
        role = 'logic'
    elif any(s in ('view', 'views', 'screens', 'pages') for s in dirs) or stem.endswith(('_screen', '_page', '_view')):
        role = 'view'
    elif 'widgets' in dirs or 'widget' in dirs:
        role = 'widget'
    else:
        role = 'other'
    feature = None
    for k, s in enumerate(dirs):
        if s in ('features', 'feature', 'modules') and k + 1 < len(dirs):
            feature = dirs[k + 1]
    return layer, role, feature


def detect_profile_fallback(deps, rels):
    riverpod = deps & {'flutter_riverpod', 'hooks_riverpod', 'riverpod'}
    vm = any('view_model' in r or 'viewmodel' in r for r in rels)
    if riverpod and any('/notifier' in r for r in rels) and not vm:
        return 'mvn'
    if 'get' in deps:
        return 'getx'
    if vm:
        return 'mvvm'
    if deps & {'bloc', 'flutter_bloc'} or any(r.endswith(('_bloc.dart', '_cubit.dart')) for r in rels):
        return 'bloc'
    if 'provider' in deps:
        return 'provider'
    if riverpod:
        return 'riverpod'
    return 'setstate' if 'flutter' in deps else 'unknown'


def read_files_arg(root, a):
    if os.path.isfile(a):
        with open(a, encoding='utf-8', errors='replace') as fh:
            items = [l.strip() for l in fh if l.strip()]
    else:
        items = [x.strip() for x in a.split(',') if x.strip()]
    out = set()
    for it in items:
        q = os.path.relpath(it, root) if os.path.isabs(it) else it
        q = os.path.normpath(q).replace(os.sep, '/')
        out.add(q[2:] if q.startswith('./') else q)
    return out


def usage(msg):
    sys.stderr.write('check_navigation.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_navigation.py <project-root> [--json] [--files <list>] '
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


def detect_router(deps, files):
    found = [pkg for pkg in ('go_router', 'auto_route', 'beamer', 'routemaster', 'get') if pkg in deps]
    if not found and any(re.search(r'\bNavigator\s*\.', f.masked) for f in files):
        found = ['Navigator']
    return found


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
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if 'GENERATED CODE - DO NOT MODIFY' in df.raw[:400]:
            continue
        a = arch_files.get(rel)
        if a:
            df.layer, df.role, df.feature = a.get('layer') or 'other', a.get('role') or 'other', a.get('feature')
        else:
            df.layer, df.role, df.feature = classify_fallback(rel)
        files.append(df)

    project = Project(files, pubspec)
    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(project.deps, rels), 'fallback detection from pubspec and folders'

    ck = Checker(project, profile)
    if files:
        ck.run()
    else:
        ck.routes, ck.typed, ck.router_calls, ck.guards, ck.unresolved = [], [], [], [], 0
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (SEV_ORDER.get(f['severity'], 9), f['id'], f['file'], f['line']))

    routers = detect_router(project.deps, files)
    nav_calls = sum(len(re.findall(r'\.\s*(?:go|push|pushReplacement|replace|goNamed|pushNamed|pop|toNamed|'
                                   r'offAllNamed)\s*(?:<[^>]*>)?\s*\(', f.masked)) for f in files)
    stats = {'files': len(files), 'routers': routers, 'router_instances': len(ck.router_calls),
             'routes': len(ck.routes), 'routes_unresolved': ck.unresolved, 'typed_routes': len(ck.typed),
             'guards': len(ck.guards), 'navigation_calls': nav_calls,
             'reported_scope': ('files list (%d)' % len(only)) if only is not None else 'all'}
    report = {'schema': SCHEMA, 'root': root, 'package': package,
              'profile': {'presentation': profile, 'source': psource},
              'classification': classification, 'stats': stats,
              'findings': findings, 'suppressed': suppressed}
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2) + '\n')
        return 0
    out = ['== NAVIGATION',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  router: %s; %d GoRouter instance(s), %d routes (%d unresolved), %d typed routes, %d guards, '
           '%d navigation calls' % (', '.join(routers) or 'none found', len(ck.router_calls), len(ck.routes),
                                    ck.unresolved, len(ck.typed), len(ck.guards), nav_calls)]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    if not groups:
        out.append('  no navigation findings')
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
