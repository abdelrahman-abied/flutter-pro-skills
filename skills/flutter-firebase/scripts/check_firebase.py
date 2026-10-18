#!/usr/bin/env python3
"""check_firebase.py: find Firebase setups that are open, fragile or costly in a Flutter app (read-only).

Usage:
  python3 -I check_firebase.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (handlers, flags and callers are resolved
             project-wide); only findings in the listed files are reported. Rules files at the
             repository root are listed with their ../ path.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  FIRE-001 rules-open-access              FIRE-007 unbounded-query
  FIRE-002 rules-test-mode-expiry         FIRE-008 listener-dropped
  FIRE-003 rules-auth-only                FIRE-009 remote-config-secret-or-gate
  FIRE-004 emulator-outside-debug         FIRE-010 client-writes-privilege-field
  FIRE-005 initialize-app-order           FIRE-011 app-check-missing
  FIRE-006 background-handler-not-entry-point  FIRE-012 app-check-debug-provider

The checker reads Dart under lib/ (generated files and firebase_options*.dart skipped),
pubspec.yaml, firebase.json, and the security rules it names or that sit at the project or
repository root: firestore.rules, storage.rules and database.rules.json (firestore.indexes.json
is counted). Files outside the project are reported with ../ paths. A project with no Firebase
dependency gets no findings.

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py --json when
that sibling skill is installed; otherwise a path-based fallback is used and the output says so.

Suppression (in the analysed code and in .rules files):
  // fire-ignore: FIRE-004 <reason>        on the reported line or the line above
  // fire-ignore-file: FIRE-004 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import datetime
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/firebase@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
TOOL = 'check_firebase.py'

RULES = {
    'FIRE-001': ('rules-open-access', 'high',
                 'A security rule grants access to everyone: `allow ...: if true`, an `allow` with no condition, or '
                 'a Realtime Database ".read"/".write" set to true. Firebase config ships in every client, so anyone '
                 'can call the database or bucket directly, without your app. Deny by default and allow each path '
                 'for the signed-in owner (request.auth.uid) with validated data.'),
    'FIRE-002': ('rules-test-mode-expiry', 'high',
                 'The rules are the console\'s "test mode" template: `request.time < timestamp.date(...)` (or '
                 'Realtime Database `now < <ms>`). Until that date anyone can read and write everything; after it '
                 'every request is denied and the app stops working. Replace it with real per-path rules and test '
                 'them with the emulator.'),
    'FIRE-003': ('rules-auth-only', 'medium',
                 'A rule lets any signed-in user write (or read) with no other check: `if request.auth != null` (or a '
                 'helper that only checks that). Signing in is not authorisation: any account, including an anonymous '
                 'one, can overwrite other users\' data. Compare request.auth.uid with the owner field or path and '
                 'validate request.resource.data.'),
    'FIRE-004': ('emulator-outside-debug', 'high',
                 'The app connects to a local emulator (useFirestoreEmulator, useAuthEmulator, useFunctionsEmulator, '
                 'useStorageEmulator, useDatabaseEmulator) with nothing that keeps it out of release builds: no '
                 'kDebugMode check, no dev flavor or --dart-define, only a hand-flipped constant. A release build that '
                 'talks to localhost fails for every user, or silently uses a test backend. Connect emulators only '
                 'under kDebugMode or in a dev flavor\'s entry point.'),
    'FIRE-005': ('initialize-app-order', 'high',
                 'Firebase.initializeApp is not finished before runApp (not awaited, or called after it), or main() '
                 'calls it before WidgetsFlutterBinding.ensureInitialized(). The first widget that reads '
                 'FirebaseAuth.instance or FirebaseFirestore.instance then throws "No Firebase App \'[DEFAULT]\' has '
                 'been created", or the platform channel throws "Binding has not yet been initialized". Call '
                 'ensureInitialized(), then await Firebase.initializeApp(options: DefaultFirebaseOptions.'
                 'currentPlatform), then runApp.'),
    'FIRE-006': ('background-handler-not-entry-point', 'high',
                 'FirebaseMessaging.onBackgroundMessage gets a handler that is a closure, an instance method, or a '
                 'top-level/static function without @pragma(\'vm:entry-point\'). The handler runs in a separate '
                 'isolate that looks it up by name: a closure or instance method fails at registration, and in '
                 'release builds an unannotated function is tree-shaken, so background messages are dropped.'),
    'FIRE-007': ('unbounded-query', 'low',
                 'A Firestore collection query is fetched or listened to with no limit(). Every matching document is '
                 'a billed read on each fetch, and a listener re-reads them on every reconnect, so cost and memory '
                 'grow with the collection. Page it: limit() plus startAfterDocument(lastDoc), or FirestoreListView.'),
    'FIRE-008': ('listener-dropped', 'medium',
                 'A Firebase stream (snapshots(), authStateChanges(), onValue, onMessage, onTokenRefresh) is listened '
                 'to inside a class with a lifetime (a State, bloc, cubit, controller, auto-dispose notifier or a '
                 'class with dispose()), and the StreamSubscription is thrown away. The listener outlives its owner: '
                 'reads keep being billed and the callback runs after dispose (setState on an unmounted State, emit '
                 'after close). Keep the subscription and cancel it in the owner\'s dispose hook.'),
    'FIRE-009': ('remote-config-secret-or-gate', 'medium',
                 'A Remote Config key looks like a secret (api_key, secret, token, password) or a security decision '
                 '(is_admin, role, permission). Remote Config is downloaded to every client and readable by anyone '
                 'with the app, and a client-side flag can be flipped. Keep secrets on a server, and decide '
                 'privileges with custom claims checked in security rules or in Cloud Functions.'),
    'FIRE-010': ('client-writes-privilege-field', 'medium',
                 'The client writes a privilege field (role, isAdmin, permissions, claims) to Firestore or the '
                 'Realtime Database. Any user can send the same write with their own value, so a privilege stored by '
                 'the client is a privilege any user can grant themselves. Set roles from a trusted backend (custom '
                 'claims via the Admin SDK) and make the rules reject client writes to these fields.'),
    'FIRE-011': ('app-check-missing', 'low',
                 'The app uses a backend Firebase product (Firestore, Functions, Storage, Realtime Database, AI Logic, '
                 'Data Connect) but never activates App Check. Without it anyone with the public config can script '
                 'calls against the project, and rules are the only line of defence. Add firebase_app_check and '
                 'activate it at start-up (Play Integrity, App Attest or DeviceCheck, reCAPTCHA on the web), then '
                 'enforce it in the console.'),
    'FIRE-012': ('app-check-debug-provider', 'medium',
                 'App Check is activated with a debug provider (AndroidProvider.debug, AppleProvider.debug, '
                 'AndroidDebugProvider, AppleDebugProvider) outside a kDebugMode branch. A release build then sends '
                 'debug tokens, which enforcement rejects (the app breaks) or which only work because a debug token '
                 'was registered (any holder of it passes). Use the debug provider only under kDebugMode and Play '
                 'Integrity / App Attest otherwise.'),
}

SAMPLE_RULES = {'FIRE-004', 'FIRE-011', 'FIRE-012'}
EXAMPLE_SEGS = {'example', 'examples', 'sample', 'samples'}

ROOT_NOTE = {
    'mvn': 'MVN: do it in the composition root (lib/main_<flavor>.dart or the bootstrap) before ProviderScope; data '
           'sources get the configured instance from a provider (firestoreProvider), never call .instance '
           'themselves.',
    'mvvm': 'MVVM: do it in main_<flavor>.dart before the Provider/MultiProvider tree; services under data/services '
            'receive the configured instance through their constructor.',
    'bloc': 'Bloc: do it in bootstrap() / main_<flavor>.dart before runApp; the repository (or its data client '
            'package) receives the configured instance through its constructor.',
    'riverpod': 'Riverpod: do it in main() before ProviderScope, or override a firestoreProvider per flavor; '
                'providers read the instance from that provider.',
    'provider': 'Provider: do it in main() before the MultiProvider; services get the configured instance through '
                'their constructor.',
    'getx': 'GetX: do it in main() (or the initial Bindings) before runApp; a GetxService wraps the configured '
            'instance.',
    'mvc': 'MVC: do it in main() before runApp; the model or service gets the configured instance.',
    'setstate': 'Do it in main() before runApp, and pass the configured instance to the classes that use it.',
    'unknown': 'Do it in the composition root (main_<flavor>.dart or a bootstrap) before runApp.',
}

LISTEN_NOTE = {
    'mvn': 'MVN: expose the stream from the data source through the repository and use case, and return it from a '
           'StreamNotifier\'s build() (Riverpod cancels it), or keep the subscription and call '
           'ref.onDispose(sub.cancel).',
    'mvvm': 'MVVM: keep the StreamSubscription in a field of the view model and cancel it in dispose().',
    'bloc': 'Bloc: use emit.forEach / emit.onEach in an event handler (cancelled with the bloc), or keep the '
            'subscription and cancel it in close().',
    'riverpod': 'Riverpod: return the stream from a StreamProvider / StreamNotifier, or keep the subscription and '
                'call ref.onDispose(sub.cancel).',
    'provider': 'Provider: keep the subscription in a field of the ChangeNotifier and cancel it in dispose().',
    'getx': 'GetX: keep the subscription (or a Worker) and cancel it in onClose().',
    'mvc': 'MVC: keep the subscription and cancel it when the controller is disposed.',
    'setstate': 'Keep the subscription in a State field and cancel it in dispose(), or use a StreamBuilder.',
    'unknown': 'Keep the subscription and cancel it in the owner\'s dispose hook.',
}

QUERY_NOTE = {
    'mvn': 'MVN: page in the data source (limit + startAfterDocument), keep the cursor in the repository, and let '
           'the notifier ask for the next page through a use case.',
    'mvvm': 'MVVM: page in the service/repository (limit + startAfterDocument) and expose a load-more command from '
            'the view model.',
    'bloc': 'Bloc: page in the repository and add a FetchNextPage event (with a droppable transformer).',
    'riverpod': 'Riverpod: page in the source and keep pages in an AsyncNotifier with a fetchMore() method.',
    'provider': 'Provider: page in the service and expose loadMore() from the ChangeNotifier.',
    'getx': 'GetX: page in the repository/service and expose loadMore() from the controller.',
    'mvc': 'MVC: page in the model or service.',
    'setstate': 'Page in a small source class, or use FirestoreListView / FirestoreQueryBuilder from firebase_ui_firestore.',
    'unknown': 'Page in the data source (limit + startAfterDocument), or use FirestoreListView.',
}

TRUST_NOTE = {
    'mvn': 'MVN: the data source reads the role from the ID token (getIdTokenResult().claims), the repository maps it '
           'to an entity, and the notifier only displays it; the server enforces it.',
    'mvvm': 'MVVM: the repository reads the role from the ID token claims; the view model only shows or hides UI, '
            'the server enforces it.',
    'bloc': 'Bloc: the authentication repository exposes the role from ID token claims; the bloc only shows or hides '
            'UI, the server enforces it.',
    'riverpod': 'Riverpod: a provider reads the role from ID token claims; UI decisions follow it, the server '
                'enforces it.',
    'provider': 'Provider: the service reads the role from ID token claims; the server enforces it.',
    'getx': 'GetX: the service reads the role from ID token claims; the server enforces it.',
    'mvc': 'MVC: the model reads the role from ID token claims; the server enforces it.',
    'setstate': 'Read the role from ID token claims for display only; the server enforces it.',
    'unknown': 'Read the role from ID token claims for display only; the server enforces it.',
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.gen|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$|'
                          r'(^|/)firebase_options[^/]*\.dart$')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|'
                              r'AUTO[- ]?GENERATED FILE|Autogenerated from Pigeon|Autogenerated by jnigen|'
                              r'Generated by `?package:ffigen|Generated by: OpenAPI Generator|'
                              r'File generated by FlutterFire CLI', re.I)
SUPPRESS_RE = re.compile(r'fire-ignore(-file)?\s*:\s*((?:FIRE-\d{3})(?:\s*,\s*FIRE-\d{3})*)\s*(.*)')

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

FIREBASE_DEP_RE = re.compile(r'^(firebase_\w+|cloud_firestore|cloud_functions|flutterfire_\w+)$')
PROTECTED_DEPS = ('cloud_firestore', 'cloud_functions', 'firebase_storage', 'firebase_database',
                  'firebase_data_connect', 'firebase_ai', 'firebase_vertexai')
FIREBASE_IMPORT_RE = re.compile(r'''^\s*import\s+['"]package:(firebase_\w+|cloud_firestore|cloud_functions)/''',
                                re.M)
EMU_RE = re.compile(r'\.\s*(use(?:Firestore|Auth|Functions|Storage|Database|DataConnect)Emulator|'
                    r'connect(?:Firestore|Auth|Functions|Storage|Database)Emulator)\s*\(')
INIT_RE = re.compile(r'(?<![\w$.])Firebase\s*\.\s*initializeApp\s*\(')
RUNAPP_RE = re.compile(r'(?<![\w$.])runApp\s*\(')
ENSURE_RE = re.compile(r'\b(?:WidgetsFlutterBinding|SentryWidgetsFlutterBinding|\w*Binding)\s*\.\s*'
                       r'ensureInitialized\s*\(|\bWidgetsBinding\s*\.\s*instance\b')
BG_RE = re.compile(r'(?<![\w$])FirebaseMessaging\s*\.\s*onBackgroundMessage\s*\(')
PRAGMA_RE = re.compile(r'''@pragma\s*\(\s*['"]vm:entry-point['"]''')
QUERY_END_RE = re.compile(r'\.\s*(snapshots|get)\s*\(')
LISTEN_RE = re.compile(r'(?<!\.)\.\s*listen\s*\(')
FB_STREAM_RE = re.compile(r'\.\s*snapshots\s*\(|\b(?:authStateChanges|idTokenChanges|userChanges|snapshotsInSync)\s*\(|'
                          r'\.\s*onValue\b|\.\s*onChild(?:Added|Changed|Removed|Moved)\b|'
                          r'\bFirebaseMessaging\s*\.\s*(?:onMessage|onMessageOpenedApp)\b|'
                          r'\.\s*onTokenRefresh\b|\.\s*onConfigUpdated\b')
WRITE_RE = re.compile(r'\.\s*(set|update|add|setData|updateData)\s*\(')
RC_GET_RE = re.compile(r'''\.\s*(getString|getBool|getInt|getDouble|getValue)\s*\(\s*(['"])([^'"\n]+)\2\s*\)''')
RC_DEFAULTS_RE = re.compile(r'\.\s*setDefaults\s*\(')
DEBUG_PROVIDER_RE = re.compile(r'\b(?:AndroidProvider\s*\.\s*debug|AppleProvider\s*\.\s*debug|'
                               r'AndroidDebugProvider\s*\(|AppleDebugProvider\s*\(|WebDebugProvider\s*\()')
APPCHECK_ACTIVATE_RE = re.compile(r'\bFirebaseAppCheck\b[\s\S]{0,200}?\.\s*activate\s*\(|'
                                  r'\b\w*[aA]ppCheck\w*\s*\.\s*activate\s*\(')

SECRET_KEY_RE = re.compile(r'(?i)(api[_-]?key|secret|token|passw(?:or)?d|private[_-]?key|credential|'
                           r'access[_-]?key|signing[_-]?key|auth[_-]?key)')
GATE_KEY_RE = re.compile(r'(?i)(admin|(?:^|[_-]|[a-z])roles?(?:$|[_-]|[A-Z])|permission|privilege|superuser|'
                         r'moderator|(?:^|[_-])staff|allow_?list|white_?list|bypass|can_?access|is_?authori[sz]ed)')
PRIV_KEY_RE = re.compile(r'(?i)^(role|roles|user_?role|is_?admin|admin|permissions?|privileges?|claims|'
                         r'custom_?claims|is_?moderator|is_?staff|is_?super_?user|super_?user|access_?level)$')

FLAVOR_FILE_RE = re.compile(r'(?:^|/)main_(?:dev|development|local|emulators?|debug|test|testing|e2e|mock|fake)'
                            r'(?:_\w+)?\.dart$')
CONFIG_WORD_RE = re.compile(r'(?i)flavor|environment|^env$|^env[A-Z_]|appEnv|buildMode|buildType|isDev|isLocal|'
                            r'isDebug|isProd|production|staging')
PLATFORM_IDENTS = {'defaultTargetPlatform', 'TargetPlatform', 'kIsWeb', 'Platform', 'isAndroid', 'isIOS',
                   'isMacOS', 'isWindows', 'isLinux', 'isFuchsia', 'android', 'iOS', 'macOS', 'windows', 'linux',
                   'fuchsia', 'null', 'true', 'false', 'mounted', 'await'}

CODEGEN_NOTIFIER = re.compile(r'\bextends\s+_\$\w+')
DISPOSE_METHOD_RE = re.compile(r'\b(?:void|Future<void>|FutureOr<void>)\s+(dispose|close|onClose|cancel)\s*\(')


def path_segs(rel):
    return [s.lower() for s in rel.split('/')]


# ---------------------------------------------------------------------------------------- rules files

def _blank_comments(text):
    """Blank // and /* */ comments (newlines kept). Returns (code, comments[(s, e)], masked) where masked
    also blanks string contents."""
    n = len(text)
    code = list(text)
    masked = list(text)
    comments = []
    i = 0
    while i < n:
        c = text[i]
        if c in '\'"':
            j = i + 1
            while j < n and text[j] != c and text[j] != '\n':
                if text[j] == '\\':
                    j += 1
                j += 1
            for k in range(i + 1, min(j, n)):
                masked[k] = ' '
            i = j + 1
        elif text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                code[k] = masked[k] = ' '
            comments.append((i, j))
            i = j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if text[k] != '\n':
                    code[k] = masked[k] = ' '
            comments.append((i, j))
            i = j
        else:
            i += 1
    return ''.join(code), comments, ''.join(masked)


class RulesFile(object):
    """A Firestore/Storage .rules file or a Realtime Database rules JSON file."""

    def __init__(self, path, rel, kind):
        self.rel = rel
        self.kind = kind
        with open(path, encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.comments, self.masked = _blank_comments(self.raw)
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.suppress_line = {}
        self.suppress_file = {}
        for s, e in self.comments:
            sm = SUPPRESS_RE.search(self.raw[s:e])
            if not sm:
                continue
            ids = [x.strip() for x in sm.group(2).split(',')]
            reason = sm.group(3).strip().strip('*/').strip() or '(no reason given)'
            if sm.group(1):
                for i in ids:
                    self.suppress_file[i] = reason
            else:
                d = self.suppress_line.setdefault(self.line_of(s), {})
                for i in ids:
                    d[i] = reason

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def line_text(self, pos):
        ln = self.line_of(pos)
        s = self.line_starts[ln - 1]
        e = self.raw.find('\n', s)
        return ' '.join(self.code[s:e if e >= 0 else len(self.raw)].split())


def _norm(c):
    c = ' '.join(c.split())
    while c.startswith('(') and c.endswith(')'):
        depth = 0
        ok = True
        for i, ch in enumerate(c):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0 and i != len(c) - 1:
                    ok = False
                    break
        if not ok:
            break
        c = c[1:-1].strip()
    return c


def _split_bool(c, op):
    out, depth, start, i = [], 0, 0, 0
    while i < len(c):
        ch = c[i]
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif depth == 0 and c.startswith(op, i):
            out.append(c[start:i])
            start = i + len(op)
            i += len(op)
            continue
        i += 1
    out.append(c[start:])
    return [_norm(x) for x in out if x.strip()]


AUTH_NULL_RE = re.compile(r'^(?:request\.auth(?:\.uid)?\s*!=\s*null|null\s*!=\s*request\.auth(?:\.uid)?|'
                          r'auth\s*!=\s*null|auth\.uid\s*!=\s*null)$')
TIME_BOMB_RE = re.compile(r'request\.time\s*<=?\s*timestamp\.date\s*\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)')
RTDB_BOMB_RE = re.compile(r'^now\s*<=?\s*(\d{12,14})$')
WRITE_OPS = {'write', 'create', 'update', 'delete'}
READ_OPS = {'read', 'get', 'list'}


def parse_security_rules(rf):
    """Yield dicts {pos, ops, cond (None = no condition), path, funcs} for each allow statement."""
    m = rf.masked
    braces = match_pairs(m, '{', '}')
    funcs = {}
    for fm in re.finditer(r'\bfunction\s+(\w+)\s*\(([^)]*)\)\s*\{', m):
        o = fm.end() - 1
        c = braces.get(o)
        if c is None:
            continue
        body = rf.code[o + 1:c]
        rm = re.search(r'\breturn\b([\s\S]*?)(?:;|$)', body)
        if rm:
            funcs[fm.group(1)] = (fm.group(2).strip(), _norm(rm.group(1)))
    matches = []
    for mm in re.finditer(r'\bmatch\s+((?:/(?:\{[^{}\n]*\}|[^/\s{}]+))+)\s*\{', m):
        o = mm.end() - 1
        c = braces.get(o)
        if c is not None:
            matches.append((o, c, rf.code[mm.start(1):mm.end(1)].strip()))
    out = []
    for am in re.finditer(r'\ballow\s+([A-Za-z,\s]+?)\s*(:|;|\})', m):
        ops = {x.strip().lower() for x in am.group(1).split(',') if x.strip()}
        if not ops <= (WRITE_OPS | READ_OPS):
            continue
        cond = None
        if am.group(2) == ':':
            j = am.end()
            im = re.match(r'\s*if\b', m[j:])
            if not im:
                continue
            j += im.end()
            depth, k = 0, j
            while k < len(m):
                ch = m[k]
                if ch in '([':
                    depth += 1
                elif ch in ')]':
                    depth -= 1
                elif depth <= 0 and ch in ';}':
                    break
                elif depth <= 0 and ch == '\n' and re.match(r'\n\s*(allow|match|function)\b', m[k:]):
                    break
                k += 1
            cond = _norm(rf.code[j:k])
        enclosing = sorted([x for x in matches if x[0] < am.start() < x[1]], key=lambda x: x[0])
        path = ''.join(x[2] for x in enclosing)
        out.append({'pos': am.start(), 'ops': ops, 'cond': cond, 'path': path, 'funcs': funcs})
    return out


def cond_is_true(cond, funcs, depth=0):
    if cond is None:
        return True
    terms = _split_bool(cond, '||')
    for t in terms:
        if t == 'true':
            return True
        cm = re.match(r'^(\w+)\s*\(\s*\)$', t)
        if cm and cm.group(1) in funcs and not funcs[cm.group(1)][0] and depth < 3:
            if cond_is_true(funcs[cm.group(1)][1], funcs, depth + 1):
                return True
    return False


def cond_auth_only(cond, funcs, depth=0):
    if cond is None:
        return False
    ors = _split_bool(cond, '||')
    if len(ors) > 1:
        return all(cond_auth_only(t, funcs, depth) for t in ors)
    terms = _split_bool(cond, '&&')
    if not terms:
        return False
    for t in terms:
        if AUTH_NULL_RE.match(t):
            continue
        cm = re.match(r'^(\w+)\s*\(\s*\)$', t)
        if cm and cm.group(1) in funcs and not funcs[cm.group(1)][0] and depth < 3 and \
                cond_auth_only(funcs[cm.group(1)][1], funcs, depth + 1):
            continue
        return False
    return True


def cond_time_bomb(cond, funcs, depth=0):
    if cond is None:
        return None
    tm = TIME_BOMB_RE.search(cond)
    if tm:
        try:
            return datetime.date(int(tm.group(1)), int(tm.group(2)), int(tm.group(3)))
        except ValueError:
            return datetime.date(int(tm.group(1)), 1, 1)
    if depth < 3:
        for name in re.findall(r'\b(\w+)\s*\(\s*\)', cond):
            if name in funcs and not funcs[name][0]:
                d = cond_time_bomb(funcs[name][1], funcs, depth + 1)
                if d:
                    return d
    return None


class _JsonScanner(object):
    """Tiny JSON reader that keeps the position of every key (for line numbers)."""

    def __init__(self, text):
        self.t = text
        self.i = 0
        self.items = []    # (path tuple, value, key position)

    def ws(self):
        while self.i < len(self.t) and self.t[self.i] in ' \t\r\n':
            self.i += 1

    def string(self):
        assert self.t[self.i] == '"'
        j = self.i + 1
        buf = []
        while j < len(self.t) and self.t[j] != '"':
            if self.t[j] == '\\':
                j += 1
            buf.append(self.t[j])
            j += 1
        self.i = j + 1
        return ''.join(buf)

    def value(self, path):
        self.ws()
        c = self.t[self.i]
        if c == '{':
            self.i += 1
            self.ws()
            if self.t[self.i] == '}':
                self.i += 1
                return {}
            while True:
                self.ws()
                kpos = self.i
                k = self.string()
                self.ws()
                if self.t[self.i] != ':':
                    raise ValueError('expected :')
                self.i += 1
                v = self.value(path + (k,))
                if not isinstance(v, (dict, list)):
                    self.items.append((path + (k,), v, kpos))
                self.ws()
                if self.t[self.i] == ',':
                    self.i += 1
                    continue
                if self.t[self.i] == '}':
                    self.i += 1
                    return {}
                raise ValueError('expected , or }')
        if c == '[':
            self.i += 1
            while True:
                self.ws()
                if self.t[self.i] == ']':
                    self.i += 1
                    return []
                self.value(path)
                self.ws()
                if self.t[self.i] == ',':
                    self.i += 1
            return []
        if c == '"':
            return self.string()
        mm = re.compile(r'true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?').match(self.t, self.i)
        if not mm:
            raise ValueError('bad value')
        self.i = mm.end()
        tok = mm.group(0)
        return True if tok == 'true' else False if tok == 'false' else None if tok == 'null' else tok


def parse_rtdb_rules(rf):
    sc = _JsonScanner(rf.code)
    try:
        sc.value(())
    except (ValueError, IndexError, AssertionError):
        return None
    return sc.items


def load_firebase_json(path):
    """Rules paths named by a firebase.json: {'firestore': [...], 'storage': [...], 'database': [...]}."""
    out = {'firestore': [], 'storage': [], 'database': [], 'indexes': []}
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for key in ('firestore', 'storage', 'database'):
        v = data.get(key)
        for item in (v if isinstance(v, list) else [v]):
            if isinstance(item, dict):
                if isinstance(item.get('rules'), str):
                    out[key].append(item['rules'])
                if key == 'firestore' and isinstance(item.get('indexes'), str):
                    out['indexes'].append(item['indexes'])
    return out


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, root, files, profile, deps, platforms, sample, sample_reason, only):
        self.root = root
        self.files = files
        self.profile = profile
        self.deps = deps
        self.platforms = platforms
        self.sample = sample
        self.sample_reason = sample_reason
        self.only = only
        self.findings = []
        self.suppressed = []
        self.stats = {'emulator_calls': 0, 'initialize_calls': 0, 'background_handlers': 0, 'queries': 0,
                      'listeners': 0, 'remote_config_reads': 0, 'writes': 0, 'rules_files': [],
                      'rules_statements': 0, 'index_files': [], 'app_check': False}
        self._decl_cache = {}
        self._if_cache = {}

    # -- reporting
    def add(self, src, rid, line, evidence, note='', severity=None):
        sev = severity or RULES[rid][1]
        reason = src.suppress_file.get(rid) if src is not None else None
        if reason is None and src is not None:
            for l in (line, line - 1):
                if rid in src.suppress_line.get(l, {}):
                    reason = src.suppress_line[l][rid]
                    break
        rel = src.rel if src is not None else 'pubspec.yaml'
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': rel, 'line': line, 'reason': reason})
            return
        if rid in SAMPLE_RULES and self.sample and sev != 'info':
            note = 'sample app (%s): graded info, not %s. %s' % (self.sample_reason, sev, note)
            sev = 'info'
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': rel, 'line': line,
                              'evidence': evidence[:160], 'message': RULES[rid][2], 'note': note.strip()})

    def pnote(self, table):
        return table.get(self.profile, table['unknown'])

    # -- Dart helpers
    @staticmethod
    def skip_ws_back(m, j):
        while j >= 0 and m[j] in ' \t\n':
            j -= 1
        return j

    def chain_start(self, df, dot):
        """Start of the member chain that ends at the '.' at position dot (a.b(c).d<T>(e) . ...)."""
        m = df.masked
        if df.brackets is None:
            df.brackets = match_pairs(m, '[', ']')
        start = dot
        i = dot
        while True:
            j = self.skip_ws_back(m, i - 1)
            while j >= 0 and m[j] in '!?':
                j = self.skip_ws_back(m, j - 1)
            group = None
            while j >= 0 and m[j] in ')]':
                o = (df.parens if m[j] == ')' else df.brackets).get(j)
                if o is None:
                    return start
                group = o
                j = self.skip_ws_back(m, o - 1)
                if j >= 0 and m[j] == '>':
                    depth, k = 0, j
                    while k >= 0:
                        if m[k] == '>':
                            depth += 1
                        elif m[k] == '<':
                            depth -= 1
                            if depth == 0:
                                break
                        elif m[k] in ';{}':
                            k = -1
                            break
                        k -= 1
                    if k < 0:
                        return start
                    j = self.skip_ws_back(m, k - 1)
            if j >= 0 and _ident(m, j):
                k = j
                while k >= 0 and _ident(m, k):
                    k -= 1
                word = m[k + 1:j + 1]
                if word in ('await', 'return', 'yield', 'else', 'throw', 'new', 'const', 'in', 'case', 'is', 'as'):
                    return group if group is not None else start
                start = k + 1
            else:
                return group if group is not None else start
            k2 = self.skip_ws_back(m, start - 1)
            if k2 >= 0 and m[k2] == '.':
                if k2 >= 1 and m[k2 - 1] == '.':
                    return start
                if k2 >= 1 and m[k2 - 1] == '?':
                    k2 -= 1
                i = k2
                continue
            return start

    def element_start(self, df, pos):
        """Start of the argument (or statement) that contains pos: a ternary guard must sit in it."""
        m = df.masked
        st = self.stmt_start(m, pos)
        best = None
        for po, pc in df.parens.items():
            if m[po] == '(' and st <= po < pos < pc and (best is None or po > best):
                best = po
        if best is None:
            return st
        for a, b in split_top(m, best + 1, df.parens[best]):
            if a <= pos < b:
                return a
        return st

    @staticmethod
    def stmt_start(m, pos):
        best = -1
        for ch in ';{}':
            best = max(best, m.rfind(ch, 0, pos))
        return best + 1

    def if_blocks(self, df):
        if df.rel in self._if_cache:
            return self._if_cache[df.rel]
        m = df.masked
        out = []
        for im in re.finditer(r'(?<![\w$.])if\s*\(', m):
            po = im.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            cond = df.code[po + 1:pc]
            j = pc + 1
            while j < len(m) and m[j] in ' \t\n':
                j += 1
            if j < len(m) and m[j] == '{':
                te = df.braces.get(j, j)
            else:
                te = expr_end(m, j)
            k = te + 1
            while k < len(m) and m[k] in ' \t\n':
                k += 1
            es = ee = None
            if m.startswith('else', k) and not _ident(m, k + 4):
                es = k + 4
                q = es
                while q < len(m) and m[q] in ' \t\n':
                    q += 1
                ee = df.braces.get(q, q) if q < len(m) and m[q] == '{' else expr_end(m, q)
            out.append((cond, j, te, es, ee))
        self._if_cache[df.rel] = out
        return out

    def find_decl_init(self, name):
        """Initializer text of a variable/getter named name anywhere in the project (first hit), or None."""
        if name in self._decl_cache:
            return self._decl_cache[name]
        rx = re.compile(r'(?:^|[;{}\s])(?:static\s+)?(?:const|final|var|late|bool)\s+(?:bool\s+)?' + re.escape(name) +
                        r'\s*=(?!=)\s*([^;]+);|\bget\s+' + re.escape(name) + r'\s*=>\s*([^;]+);|'
                        r'(?:^|[;{}\s])bool\s+' + re.escape(name) + r'\s*=(?!=)\s*([^;]+);')
        res = None
        for df in self.files:
            mm = rx.search(df.code)
            if mm:
                res = ' '.join((mm.group(1) or mm.group(2) or mm.group(3) or '').split())
                break
        self._decl_cache[name] = res
        return res

    def cond_kind(self, cond):
        """'debug' (a build-mode/flavor guard), 'release', 'toggle-true', 'toggle-false' or None."""
        c = ' '.join(cond.split())
        if re.search(r'!\s*kReleaseMode\b|\bkReleaseMode\s*==\s*false|\bkDebugMode\b(?!\s*==\s*false)|\bkProfileMode\b',
                     c) and not re.search(r'!\s*kDebugMode\b', c):
            return 'debug'
        if re.search(r'!\s*kDebugMode\b|\bkReleaseMode\b', c):
            return 'release'
        if re.search(r'fromEnvironment|hasEnvironment|\bappFlavor\b', c):
            return 'debug'
        kinds = []
        for ident in re.findall(r'[A-Za-z_$][\w$]*', re.sub(r'([\'"]).*?\1', ' ', c)):
            if ident in PLATFORM_IDENTS or ident in KEYWORDS:
                continue
            if CONFIG_WORD_RE.search(ident):
                kinds.append('debug')
                continue
            init = self.find_decl_init(ident)
            if init is None:
                kinds.append('debug')          # a parameter, field or injected config: trust it
            elif init in ('true', 'false'):
                kinds.append('toggle-' + init)
            elif re.search(r'kDebugMode|!\s*kReleaseMode|fromEnvironment|hasEnvironment|appFlavor', init) or \
                    CONFIG_WORD_RE.search(init):
                kinds.append('debug')
            elif re.search(r'kReleaseMode', init):
                kinds.append('release')
            else:
                kinds.append('debug')
        for k in ('debug', 'toggle-true', 'toggle-false', 'release'):
            if k in kinds:
                return k
        return None

    def guard_at(self, df, pos, depth=0):
        """'guarded', 'toggle-true', 'toggle-false', 'unguarded' or 'unknown' for code at pos."""
        if FLAVOR_FILE_RE.search(df.rel):
            return 'guarded'
        toggles = []
        for cond, ts, te, es, ee in self.if_blocks(df):
            if ts <= pos <= te:
                k = self.cond_kind(cond)
                if k == 'debug':
                    return 'guarded'
                if k and k.startswith('toggle'):
                    toggles.append(k)
            elif es is not None and es <= pos <= ee:
                if self.cond_kind(cond) == 'release':
                    return 'guarded'
        for name, po in df.enclosing_calls(pos):
            if name == 'assert':
                return 'guarded'
        fs = df.enclosing_callables(pos)
        if fs:
            body = df.code[fs[-1].bo:pos] if fs else ''
            for em in re.finditer(r'(?<![\w$.])if\s*\(([^;{}]*?)\)\s*\{?\s*return\b', body):
                if self.cond_kind(em.group(1)) == 'release':
                    return 'guarded'
        a = self.element_start(df, pos)
        if re.search(r'\bkDebugMode\s*\?|!\s*kReleaseMode\s*\?|\bkReleaseMode\s*\?', df.code[a:pos]):
            return 'guarded'
        if toggles:
            return 'toggle-true' if 'toggle-true' in toggles else 'toggle-false'
        named = [f for f in fs if f.name and f.name not in KEYWORDS]
        if not named:
            return 'unguarded'
        fn = named[0]
        if fn.name == 'main':
            return 'unguarded'
        if depth >= 2:
            return 'unknown'
        calls = []
        rx = re.compile(r'(?<![\w$])' + re.escape(fn.name) + r'\s*\(')
        tear = re.compile(r'(?<=[(,:=])\s*' + re.escape(fn.name) + r'(?=\s*[),;])')
        for other in self.files:
            decl_starts = set(f.start for f in other.callables if f.name == fn.name)
            for cm in rx.finditer(other.masked):
                if cm.start() in decl_starts:
                    continue
                calls.append((other, cm.start()))
            for tm in tear.finditer(other.masked):
                calls.append((other, tm.end() - 1))
        if not calls:
            return 'unknown'
        results = [self.guard_at(o, p, depth + 1) for o, p in calls]
        for r in ('unguarded', 'toggle-true', 'toggle-false', 'unknown'):
            if r in results:
                return r
        return 'guarded'

    def class_holder(self, df, pos):
        """(kind, class name) of a lifecycle-bound holder at pos, or (None, name)."""
        cls = df.enclosing_class(pos)
        if cls is None:
            return None, None
        name, o, c, hdr, hs = cls
        if re.match(r'\s*extension\b', hdr) or re.search(r'\bextension\b', hdr.split('{')[0][:30]):
            return None, name
        body = df.masked[o:c]
        if re.search(r'\bextends\s+(?:\w+\s*\.\s*)?(?:State|ConsumerState|HookState)\s*<', hdr):
            return 'state', name
        if re.search(r'\b(?:extends|with)\s+(?:Hydrated)?(?:Bloc|Cubit)\b', hdr):
            return 'bloc', name
        if re.search(r'\b(?:extends|with)\s+(?:GetxController|FullLifeCycleController)\b', hdr):
            return 'getx', name
        if CODEGEN_NOTIFIER.search(hdr):
            ann = df.code[max(0, hs - 120):hs]
            if re.search(r'keepAlive\s*:\s*true', ann):
                return None, name
            return 'notifier', name
        if DISPOSE_METHOD_RE.search(body) or re.search(r'@override\s+(?:void|Future<void>)\s+(?:dispose|close|onClose)\b',
                                                     body):
            return 'disposable', name
        return None, name

    # -- run
    def run(self, rules_files, pubspec_text):
        if any(dep in self.deps for dep in ('firebase_app_check',)):
            self.stats['app_check'] = True
        for df in self.files:
            self.check_emulators(df)
            self.check_init(df)
            self.check_background(df)
            self.check_queries(df)
            self.check_listeners(df)
            self.check_remote_config(df)
            self.check_writes(df)
            self.check_debug_provider(df)
        self.check_app_check(pubspec_text)
        for rf in rules_files:
            if rf.kind == 'rtdb':
                self.check_rtdb(rf)
            else:
                self.check_rules(rf)

    # FIRE-004
    def check_emulators(self, df):
        for mm in EMU_RE.finditer(df.masked):
            self.stats['emulator_calls'] += 1
            pos = mm.start(1)
            g = self.guard_at(df, pos)
            if g in ('guarded', 'unknown'):
                continue
            ev = df.line_text(pos)
            if g == 'toggle-false':
                sev, why = 'low', 'it sits behind a hand-set constant that is false today; one edit ships it.'
            elif g == 'toggle-true':
                sev, why = 'high', 'it sits behind a hand-set constant that is true, so release builds connect too.'
            else:
                sev, why = 'high', 'nothing keeps it out of release builds.'
            note = '%s is called and %s Wrap it in `if (kDebugMode) { ... }` (or move it to main_dev.dart / read ' \
                   'bool.fromEnvironment(\'USE_EMULATORS\')), and connect before the first Firebase call. %s' % (
                       mm.group(1), why, self.pnote(ROOT_NOTE))
            self.add(df, 'FIRE-004', df.line_of(pos), ev, note, severity=sev)

    # FIRE-005
    def check_init(self, df):
        m = df.masked
        inits = [mm.start() for mm in INIT_RE.finditer(m)]
        self.stats['initialize_calls'] += len(inits)
        if not inits:
            return
        mobile = bool({'android', 'ios', 'macos', 'windows', 'linux'} & set(self.platforms)) or \
            not self.platforms
        main_has_ensure = self.main_calls_ensure()
        done = set()
        for p in inits:
            fs = df.enclosing_callables(p)
            named = [f for f in fs if f.name and f.name not in KEYWORDS]
            if not named:
                continue
            fn = named[0]
            body_s, body_e = fn.bo, fn.bc
            runs = [r.start() + body_s for r in RUNAPP_RE.finditer(m[body_s:body_e])]
            st = self.stmt_start(m, p)
            prefix = m[st:p]
            if 'runApp(' in prefix.replace(' ', ''):
                continue                       # runApp(FutureBuilder(future: Firebase.initializeApp(), ...))
            pc = df.parens.get(p + m[p:].find('('))
            then_range = None
            if pc is not None:
                tm = re.match(r'\s*\.\s*then\s*\(', m[pc + 1:pc + 40])
                if tm:
                    to = pc + 1 + tm.end() - 1
                    then_range = (to, df.parens.get(to, to))
            awaited = bool(re.search(r'\bawait\b', prefix))
            if not awaited and re.search(r'(?<![=!<>])=(?![=>])', prefix):
                continue                       # final init = Firebase.initializeApp(); used by a FutureBuilder later
            ev = df.line_text(p)
            if runs and (fn.bo, 'order') not in done:
                before = [r for r in runs if r < st]
                after = [r for r in runs if r > p and not (then_range and then_range[0] < r < then_range[1])]
                if before:
                    done.add((fn.bo, 'order'))
                    self.add(df, 'FIRE-005', df.line_of(p), ev,
                             'runApp is called (line %d) before Firebase.initializeApp in %s(): the first frame can '
                             'read a Firebase instance that does not exist yet. Await initializeApp first. %s' % (
                                 df.line_of(before[0]), fn.name, self.pnote(ROOT_NOTE)))
                    continue
                if after and not awaited:
                    done.add((fn.bo, 'order'))
                    self.add(df, 'FIRE-005', df.line_of(p), ev,
                             'Firebase.initializeApp is not awaited before runApp (line %d) in %s(), so widgets can '
                             'build before Firebase is ready ("No Firebase App \'[DEFAULT]\' has been created"). Write '
                             '`await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);`. %s' % (
                                 df.line_of(after[0]), fn.name, self.pnote(ROOT_NOTE)))
                    continue
            if fn.name == 'main' and mobile and (fn.bo, 'ensure') not in done:
                pre = df.masked[fn.bo:p]
                if not ENSURE_RE.search(pre):
                    done.add((fn.bo, 'ensure'))
                    self.add(df, 'FIRE-005', df.line_of(p), ev,
                             'main() calls Firebase.initializeApp before WidgetsFlutterBinding.ensureInitialized(). On '
                             'Android, iOS and desktop the plugin needs the binding for its platform channel, so start-up '
                             'throws "Binding has not yet been initialized". Call ensureInitialized() first (web-only '
                             'apps are not reported).', severity='medium')
            elif runs and fn.name != 'main' and mobile and (fn.bo, 'ensure') not in done:
                pre = df.masked[fn.bo:p]
                if not ENSURE_RE.search(pre) and not main_has_ensure:
                    done.add((fn.bo, 'ensure'))
                    self.add(df, 'FIRE-005', df.line_of(p), ev,
                             '%s() initialises Firebase and calls runApp, but nothing calls '
                             'WidgetsFlutterBinding.ensureInitialized() before it. Call it first.' % fn.name,
                             severity='medium')

    def main_calls_ensure(self):
        for df in self.files:
            if not re.search(r'(^|/)main[^/]*\.dart$', df.rel):
                continue
            for f in df.callables:
                if f.name == 'main' and ENSURE_RE.search(df.masked[f.bo:f.bc]):
                    return True
        return False

    # FIRE-006
    def check_background(self, df):
        m = df.masked
        for mm in BG_RE.finditer(m):
            self.stats['background_handlers'] += 1
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            args = split_top(m, po + 1, pc)
            if not args:
                continue
            a, b = strip_range(m, *args[0])
            arg = df.code[a:b].strip()
            ev = df.line_text(mm.start())
            if arg.startswith('(') or '=>' in m[a:b] or re.search(r'\basync\s*\{|\)\s*\{', m[a:b]):
                self.add(df, 'FIRE-006', df.line_of(mm.start()), ev,
                         'the handler is a closure. Declare a top-level (or static) function annotated with '
                         '@pragma(\'vm:entry-point\') and pass its name; the background isolate cannot call a closure.')
                continue
            im = re.match(r'^(?:([A-Z]\w*)\s*\.\s*)?([A-Za-z_$][\w$]*)$', arg)
            if not im:
                continue
            name = im.group(2)
            fs = df.enclosing_callables(mm.start())
            if any(name == p[0] for f in fs for p in f.params):
                continue                       # a parameter: resolved by the caller
            decl = self.find_function(name, df, im.group(1))
            if decl is None:
                continue
            ddf, f = decl
            cls = ddf.enclosing_class(f.start)
            pre_s = max(ddf.masked.rfind(ch, 0, f.start) for ch in ';{}') + 1
            header = ddf.code[pre_s:f.start]
            if cls is not None and not re.search(r'\bstatic\b', header):
                self.add(df, 'FIRE-006', df.line_of(mm.start()), ev,
                         '`%s` is an instance method of %s. Make it a top-level function (or static) annotated with '
                         '@pragma(\'vm:entry-point\').' % (name, cls[0]))
            elif not PRAGMA_RE.search(header):
                self.add(df, 'FIRE-006', df.line_of(mm.start()), ev,
                         '`%s` (%s:%d) has no @pragma(\'vm:entry-point\'). Since Flutter 3.3 release builds tree-shake '
                         'it, so the background isolate cannot find it. Add the annotation on the line above the '
                         'declaration.' % (name, ddf.rel, ddf.line_of(f.start)))

    def find_function(self, name, prefer, owner=None):
        """(file, Callable) declaring a function or method called name (in class owner when given);
        the preferred file first."""
        order = [prefer] + [d for d in self.files if d is not prefer]
        for df in order:
            for f in df.callables:
                if f.name != name:
                    continue
                j = self.skip_ws_back(df.masked, f.start - 1)
                if j >= 0 and df.masked[j] == '.':
                    continue
                if owner:
                    cls = df.enclosing_class(f.start)
                    if cls is None or cls[0] != owner:
                        continue
                return df, f
        return None

    # FIRE-007
    def resolve_root(self, df, root_ident):
        rx = re.compile(r'(?<![\w$.])' + re.escape(root_ident) + r'\s*(?:=(?!=)|=>)\s*([^;]+);')
        mm = rx.search(df.code)
        return mm.group(1) if mm else ''

    def check_queries(self, df):
        m = df.masked
        if not FIREBASE_IMPORT_RE.search(df.code) and '.collection(' not in m.replace(' ', ''):
            return
        for mm in QUERY_END_RE.finditer(m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            if mm.group(1) == 'get' and m[po + 1:pc].strip() and not re.match(r'\s*(?:const\s+)?GetOptions\b',
                                                                                m[po + 1:pc]):
                continue
            s = self.chain_start(df, mm.start())
            chain = re.sub(r'\s+', '', df.code[s:mm.start()])
            if not chain:
                continue
            rootm = re.match(r'([A-Za-z_$][\w$]*)', chain)
            full = chain
            if rootm and '.collection(' not in chain and '.collectionGroup(' not in chain and \
                    not chain.startswith(('collection(', 'collectionGroup(')):
                full = re.sub(r'\s+', '', self.resolve_root(df, rootm.group(1))) + chain[len(rootm.group(1)):]
            last = max(full.rfind('.collection('), full.rfind('.collectionGroup('),
                       0 if full.startswith(('collection(', 'collectionGroup(')) else -1)
            if last < 0:
                continue
            tail = full[last:]
            tail2 = re.sub(r'^\.?collection(?:Group)?\([^)]*\)', '', tail)
            if '.doc(' in tail2 or '.add(' in tail2 or re.search(r'\.(limit|limitToLast|count|aggregate)\(', tail2):
                continue
            self.stats['queries'] += 1
            first = re.search(r'\.docs\s*\.\s*first\b|\.docs\s*\[\s*0\s*\]', m[pc:pc + 300])
            hint = 'Only the first document is used: add .limit(1).' if first else \
                'Add .limit(n) and page with startAfterDocument(lastDoc).'
            self.add(df, 'FIRE-007', df.line_of(mm.start()), df.snippet(s, pc + 1),
                     'this %s() reads every matching document (no limit); each one is a billed read%s. %s %s' % (
                         mm.group(1), ', again on every change and reconnect' if mm.group(1) == 'snapshots' else '',
                         hint, self.pnote(QUERY_NOTE)))

    # FIRE-008
    def check_listeners(self, df):
        m = df.masked
        if not FIREBASE_IMPORT_RE.search(df.code):
            return
        for mm in LISTEN_RE.finditer(m):
            s = self.chain_start(df, mm.start())
            chain = df.code[s:mm.start()]
            if not FB_STREAM_RE.search(chain):
                continue
            self.stats['listeners'] += 1
            j = self.skip_ws_back(m, s - 1)
            if j >= 0 and m[j] not in ';{}':
                continue
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            k = pc + 1
            while k < len(m) and m[k] in ' \t\n':
                k += 1
            if k >= len(m) or m[k] != ';':
                continue
            kind, cname = self.class_holder(df, mm.start())
            if not kind:
                continue
            what = {'state': 'the State', 'bloc': 'the bloc/cubit', 'getx': 'the controller',
                    'notifier': 'the auto-dispose notifier', 'disposable': cname}.get(kind, cname)
            hook = {'state': 'dispose()', 'bloc': 'close()', 'getx': 'onClose()',
                    'notifier': 'ref.onDispose', 'disposable': 'its dispose()/close()'}.get(kind, 'dispose()')
            stream = FB_STREAM_RE.search(chain).group(0).strip('. (')
            self.add(df, 'FIRE-008', df.line_of(s), df.line_text(s),
                     '%s listens to %s and discards the subscription, so %s cannot cancel it. %s' % (
                         cname, stream, hook, self.pnote(LISTEN_NOTE)))

    # FIRE-009
    def check_remote_config(self, df):
        if 'firebase_remote_config' not in df.imports:
            return
        m = df.masked
        hits = []
        for mm in RC_GET_RE.finditer(df.code):
            s = self.chain_start(df, mm.start())
            recv = df.code[s:mm.start()]
            last = re.findall(r'[A-Za-z_$][\w$]*', recv)
            if not ('RemoteConfig' in recv or (last and re.search(r'(?i)remote|config|^rc', last[-1]))):
                continue
            self.stats['remote_config_reads'] += 1
            hits.append((mm.start(), mm.group(3), mm.group(1)))
        for mm in RC_DEFAULTS_RE.finditer(m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            for km in re.finditer(r'''(['"])([^'"\n]+)\1\s*:''', df.code[po:pc]):
                hits.append((po + km.start(), km.group(2), 'setDefaults'))
        seen = set()
        for pos, key, how in hits:
            if (key, df.line_of(pos)) in seen:
                continue
            kind = None
            if SECRET_KEY_RE.search(key):
                kind = 'secret'
            elif GATE_KEY_RE.search(key) and (how in ('getBool', 'setDefaults', 'getString', 'getValue')):
                kind = 'gate'
            if not kind:
                continue
            seen.add((key, df.line_of(pos)))
            if kind == 'secret':
                note = 'the key "%s" looks like a secret. Every install downloads Remote Config, so its values are ' \
                       'public. Keep the secret on your server (a Cloud Function that calls the third party) and use ' \
                       'Remote Config only for non-sensitive tuning.' % key
            else:
                note = 'the key "%s" looks like a security decision. A user can change what the client sees ' \
                       '(proxy, patched app), so gate only UI with it, and enforce access with custom claims in ' \
                       'security rules or a Cloud Function. %s' % (key, self.pnote(TRUST_NOTE))
            self.add(df, 'FIRE-009', df.line_of(pos), df.line_text(pos), note)

    # FIRE-010
    def check_writes(self, df):
        if not ({'cloud_firestore', 'firebase_database'} & df.imports):
            return
        m = df.masked
        for mm in WRITE_RE.finditer(m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            s = self.chain_start(df, mm.start())
            recv = re.sub(r'\s+', '', df.code[s:mm.start()])
            idents = re.findall(r'[A-Za-z_$][\w$]*', recv)
            last = idents[-1] if idents else ''
            txn = bool(re.match(r'^(transaction|tx|txn|t|batch|writeBatch|wb)$', last))
            fs_like = txn or bool(re.search(r'\.(doc|collection|collectionGroup|ref|child|reference)\(|'
                                            r'FirebaseFirestore|FirebaseDatabase|\.reference\b', recv)) or \
                bool(re.search(r'(?i)(ref|reference|doc|document|collection)$', last))
            if not fs_like:
                continue
            self.stats['writes'] += 1
            for a, b in split_top(m, po + 1, pc):
                a, b = strip_range(m, a, b)
                bm = re.match(r'(?:const\s+)?(?:<[^>]*>\s*)?\{', m[a:b])
                if not bm:
                    continue
                o = a + bm.end() - 1
                c = df.braces.get(o)
                if c is None:
                    continue
                for ea, eb in split_top(m, o + 1, c):
                    ea, eb = strip_range(m, ea, eb)
                    km = re.match(r'''(['"])([^'"\n]+)\1\s*:''', df.code[ea:eb])
                    if km and PRIV_KEY_RE.match(km.group(2)):
                        self.add(df, 'FIRE-010', df.line_of(ea), df.line_text(ea),
                                 'the client writes "%s". Make the rules reject it (for example '
                                 '`request.resource.data.diff(resource.data).affectedKeys().hasAny([\'%s\'])` denies '
                                 'the update) and set it from a trusted backend: custom claims via the Admin SDK, or a '
                                 'Cloud Function. %s' % (km.group(2), km.group(2), self.pnote(TRUST_NOTE)))

    # FIRE-012
    def check_debug_provider(self, df):
        for mm in DEBUG_PROVIDER_RE.finditer(df.masked):
            pos = mm.start()
            g = self.guard_at(df, pos)
            if g == 'guarded':
                continue                       # 'unknown' (no visible caller) still reports: the provider is the defect
            sev = 'low' if g == 'toggle-false' else None
            self.add(df, 'FIRE-012', df.line_of(pos), df.line_text(pos),
                     'write `providerAndroid: kDebugMode ? const AndroidDebugProvider() : const '
                     'AndroidPlayIntegrityProvider()` (and AppleDebugProvider / AppleAppAttestProvider; older API: '
                     '`androidProvider: kDebugMode ? AndroidProvider.debug : AndroidProvider.playIntegrity`), and '
                     'register debug tokens only for developer devices.%s %s' % (
                         ' It sits behind a hand-set constant that is false today.' if sev else '',
                         self.pnote(ROOT_NOTE)), severity=sev)

    # FIRE-011
    def check_app_check(self, pubspec_text):
        used = [d for d in PROTECTED_DEPS if d in self.runtime_deps]
        if not used or not self.has_app:
            return
        activated = any(APPCHECK_ACTIVATE_RE.search(df.masked) for df in self.files)
        self.stats['app_check'] = activated
        if activated:
            return
        line = 1
        for i, l in enumerate(pubspec_text.split('\n'), 1):
            if re.match(r'^\s+' + re.escape(used[0]) + r'\s*:', l):
                line = i
                break
        pub = _PubSrc(pubspec_text)
        if 'firebase_app_check' in self.runtime_deps:
            note = 'firebase_app_check is a dependency but FirebaseAppCheck.instance.activate(...) is never called ' \
                   'in lib/. '
        else:
            note = 'uses %s without firebase_app_check. ' % ', '.join(used)
        note += 'Activate it right after Firebase.initializeApp. %s' % self.pnote(ROOT_NOTE)
        self.add(pub, 'FIRE-011', line, '%s: (no App Check)' % used[0], note)

    # FIRE-001/002/003 in .rules
    def check_rules(self, rf):
        stmts = parse_security_rules(rf)
        self.stats['rules_statements'] += len(stmts)
        today = datetime.date.today()
        for st in stmts:
            ops, cond, path, funcs = st['ops'], st['cond'], st['path'], st['funcs']
            line = rf.line_of(st['pos'])
            ev = rf.line_text(st['pos'])
            recursive = bool(re.search(r'\{\w+=\*\*\}', path))
            writes = sorted(ops & WRITE_OPS)
            where = path or '(top level)'
            bomb = cond_time_bomb(cond, funcs)
            if bomb:
                state = 'expired on %s: every request is now denied and the app is broken; before that date ' \
                        'anyone could read and write' % bomb.isoformat() if bomb < today else \
                    'until %s anyone can read and write, then every request is denied' % bomb.isoformat()
                self.add(rf, 'FIRE-002', line, ev,
                         '%s (%s at %s). Replace the template with per-path rules: deny by default, allow the owner '
                         '(request.auth.uid == userId), validate request.resource.data, and test them with '
                         '@firebase/rules-unit-testing on the emulator.' % (state, ', '.join(sorted(ops)), where))
                continue
            if cond_is_true(cond, funcs):
                if writes:
                    self.add(rf, 'FIRE-001', line, ev,
                             'anyone can %s %s%s. Scope writes to the owner and validate the data, for example '
                             '`allow write: if request.auth != null && request.auth.uid == userId && '
                             'request.resource.data.keys().hasOnly([...])`.' % (
                                 '/'.join(writes), where, ' and everything below it' if recursive else ''))
                elif recursive:
                    self.add(rf, 'FIRE-001', line, ev,
                             'anyone, signed in or not, can %s every document or file under %s. Make public data '
                             'public on purpose: match the public path only (match /public/{file}) and keep the '
                             'rest closed.' % ('/'.join(sorted(ops)), where), severity='medium')
                continue
            if cond_auth_only(cond, funcs):
                if writes:
                    sev = 'medium' if recursive else 'low'
                    self.add(rf, 'FIRE-003', line, ev,
                             'any signed-in user (anonymous accounts included) can %s %s%s. Check ownership '
                             '(request.auth.uid == resource.data.ownerId, or the {userId} in the path) and validate '
                             'request.resource.data.' % ('/'.join(writes), where,
                                                         ' and everything below it' if recursive else ''),
                             severity=sev)
                elif recursive:
                    self.add(rf, 'FIRE-003', line, ev,
                             'any signed-in user (anonymous accounts included) can %s everything under %s. Scope '
                             'reads to the paths users need.' % ('/'.join(sorted(ops)), where), severity='low')

    # FIRE-001/002/003 in database.rules.json
    def check_rtdb(self, rf):
        items = parse_rtdb_rules(rf)
        if items is None:
            return
        self.stats['rules_statements'] += len(items)
        today = datetime.date.today()
        for path, value, kpos in items:
            if not path or path[-1] not in ('.read', '.write'):
                continue
            if not path or path[0] != 'rules':
                continue
            where = '/' + '/'.join(path[1:-1])
            depth = len(path) - 2
            only_wild = all(p.startswith('$') for p in path[1:-1])
            line = rf.line_of(kpos)
            ev = rf.line_text(kpos)
            v = value if isinstance(value, bool) else (' '.join(value.split()) if isinstance(value, str) else None)
            op = path[-1][1:]
            if isinstance(v, str):
                bm = RTDB_BOMB_RE.match(v)
                if bm:
                    try:
                        d = (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=int(bm.group(1)))).date()
                    except (ValueError, OverflowError, OSError):
                        d = today
                    state = 'expired on %s: every request is now denied' % d.isoformat() if d < today else \
                        'until %s anyone can %s it' % (d.isoformat(), op)
                    self.add(rf, 'FIRE-002', line, ev, '%s (%s at %s). Write per-path rules with auth.uid checks '
                             'and .validate.' % (state, op, where))
                    continue
            if v is True or v == 'true':
                if op == 'write' or depth == 0:
                    self.add(rf, 'FIRE-001', line, ev,
                             'anyone can %s %s and everything below it. Use "auth != null && auth.uid === $uid" on '
                             'per-user paths and add .validate rules.' % (op, where))
                continue
            if isinstance(v, str) and AUTH_NULL_RE.match(v) and (depth == 0 or only_wild):
                sev = 'medium' if op == 'write' else 'low'
                self.add(rf, 'FIRE-003', line, ev,
                         'any signed-in user can %s %s and everything below it. Compare auth.uid with the $uid in '
                         'the path and validate the data.' % (op, where), severity=sev)


class _PubSrc(object):
    """pubspec.yaml as a finding source; honours `# fire-ignore: FIRE-011 <reason>` comments."""
    rel = 'pubspec.yaml'

    def __init__(self, text):
        self.suppress_file, self.suppress_line = {}, {}
        for i, l in enumerate(text.split('\n'), 1):
            if '#' not in l:
                continue
            sm = SUPPRESS_RE.search(l[l.index('#'):])
            if not sm:
                continue
            reason = sm.group(3).strip() or '(no reason given)'
            for rid in [x.strip() for x in sm.group(2).split(',')]:
                if sm.group(1):
                    self.suppress_file[rid] = reason
                else:
                    self.suppress_line.setdefault(i, {})[rid] = reason


# ---------------------------------------------------------------------------------------- support

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
    segs = path_segs(rel)
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
    sys.stderr.write('%s: %s\n' % (TOOL, msg))
    sys.stderr.write('usage: python3 -I %s <project-root> [--json] [--files <list>] '
                     '[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]\n' % TOOL)
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
    """(all dependency names, runtime dependency names)."""
    deps, runtime = set(), set()
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
            if section == 'dependencies':
                runtime.add(mm.group(1))
    return deps, runtime


def walk_dart(root, top):
    out = []
    base = os.path.join(root, top)
    if not os.path.isdir(base):
        return out
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if not d.startswith('.') and d not in ('generated', 'build'))
        for fn in sorted(fns):
            if fn.endswith('.dart'):
                out.append(os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/'))
    return out


def find_git_root(root):
    p = root
    while True:
        if os.path.exists(os.path.join(p, '.git')):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def discover_rules(root, git_root):
    """[(abs path, rel path, kind)] for the rules files of the project and its repository root."""
    bases = [root]
    if git_root and os.path.realpath(git_root) != os.path.realpath(root):
        bases.append(git_root)
    found, seen, indexes = [], set(), []
    for base in bases:
        named = load_firebase_json(os.path.join(base, 'firebase.json'))
        cands = [(p, 'firestore') for p in named['firestore']] + [(p, 'storage') for p in named['storage']] + \
                [(p, 'rtdb') for p in named['database']] + \
                [('firestore.rules', 'firestore'), ('storage.rules', 'storage'), ('database.rules.json', 'rtdb')]
        for rel, kind in cands:
            ap = os.path.normpath(os.path.join(base, rel))
            if not os.path.isfile(ap):
                continue
            rp = os.path.realpath(ap)
            if rp in seen:
                continue
            seen.add(rp)
            found.append((ap, os.path.relpath(ap, root).replace(os.sep, '/'), kind))
        for rel in named['indexes'] + ['firestore.indexes.json']:
            ap = os.path.normpath(os.path.join(base, rel))
            if os.path.isfile(ap):
                r = os.path.relpath(ap, root).replace(os.sep, '/')
                if r not in indexes:
                    indexes.append(r)
    return found, indexes


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
    deps, runtime = pubspec_deps(pubspec)
    fb_deps = sorted(d for d in runtime if FIREBASE_DEP_RE.match(d))
    only = read_files_arg(root, opts['files']) if opts['files'] else None
    platforms = [p for p in ('android', 'ios', 'web', 'macos', 'windows', 'linux')
                 if os.path.isdir(os.path.join(root, p))]
    git_root = find_git_root(root)
    relp = os.path.relpath(root, git_root) if git_root else os.sep.join(root.split(os.sep)[-2:])
    segs = [s.lower() for s in relp.replace(os.sep, '/').split('/')]
    sample = any(s in EXAMPLE_SEGS for s in segs)
    sample_reason = 'inside an example/samples folder' if sample else ''

    rels = walk_dart(root, 'lib') if fb_deps else []
    skipped = {'generated': 0, 'barrel': 0}
    kept = []
    for rel in rels:
        if GENERATED_RE.search(rel):
            skipped['generated'] += 1
        else:
            kept.append(rel)
    rels = kept

    if not fb_deps:
        arch, classification = None, 'not needed (no Firebase dependency)'
    elif not rels:
        arch, classification = None, 'no lib/ directory' if not os.path.isdir(os.path.join(root, 'lib')) else \
            'no Dart files to classify'
    else:
        arch, classification = run_arch_check(root, opts['profile'])
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

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(deps, rels), 'fallback detection from pubspec and folders'
    aprof = arch['profile'] if arch and isinstance(arch.get('profile'), dict) else {}
    clean = bool(aprof.get('clean_architecture'))

    rules_found, indexes = discover_rules(root, git_root) if fb_deps else ([], [])
    rules_files = []
    for ap, rel, kind in rules_found:
        try:
            rules_files.append(RulesFile(ap, rel, kind))
        except OSError:
            pass

    ck = Checker(root, files, profile, deps, platforms, sample, sample_reason, only)
    ck.runtime_deps = runtime
    ck.has_app = any(re.search(r'^lib/main[^/]*\.dart$', r) for r in rels)
    if fb_deps:
        ck.run(rules_files, pubspec)
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))

    stats = dict(ck.stats)
    stats['files'] = len(files)
    stats['skipped_generated'] = skipped['generated']
    stats['skipped_barrels'] = skipped['barrel']
    stats['firebase_packages'] = fb_deps
    stats['rules_files'] = [rf.rel for rf in rules_files]
    stats['index_files'] = indexes
    stats['platforms'] = platforms
    stats['sample'] = sample
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

    out = ['== FIREBASE',
           '  profile: %s%s (%s)' % (profile, ' + clean' if clean else '', psource),
           '  classification: %s' % classification]
    if not fb_deps:
        out.append('  scanned: 0 files; no Firebase dependency in pubspec.yaml, nothing to check')
    else:
        out.append('  scanned: %d files (%d generated skipped); packages: %s; rules: %s; %d emulator calls, '
                   '%d initializeApp, %d listeners, %d unbounded queries, App Check: %s%s' % (
                       len(files), skipped['generated'], ', '.join(fb_deps[:6]) + (' ...' if len(fb_deps) > 6 else ''),
                       ', '.join(stats['rules_files']) or 'none found', stats['emulator_calls'],
                       stats['initialize_calls'], stats['listeners'], stats['queries'],
                       'activated' if stats['app_check'] else 'not activated', '; sample app' if sample else ''))
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no firebase findings')
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
