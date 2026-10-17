#!/usr/bin/env python3
"""check_errors.py: find error-handling bugs in a Flutter/Dart project (read-only).

Usage:
  python3 -I check_errors.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (some rules look across files);
             only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Layers and roles come from ../flutter-architecture/scripts/arch_check.py --json
("files" array) when that sibling skill is installed; otherwise a path-based
fallback is used and the output says so.

Suppression (in the analysed code):
  // err-ignore: ERR-001 <reason>        on the reported line, the line above or the line below
  // err-ignore-file: ERR-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/error-check@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

RULES = {
    'ERR-001': ('swallowed-catch', 'high',
                "A catch (or catchError/onError handler) discards the error: empty, comment-only, "
                "print-only or `return <default>;`. Log/report it, rethrow it, or map it to a typed failure."),
    'ERR-002': ('untyped-catch-unmapped', 'medium',
                "Catch-all (`catch (e)` / `on Object`) in the data or domain layer that never uses the error, "
                "never rethrows and never maps it to a failure. Catch the specific types and map them."),
    'ERR-003': ('catches-error', 'medium',
                "Catches an `Error` subtype (StateError, TypeError, ArgumentError ...). Errors are programming "
                "bugs: fix the code instead of catching them (Effective Dart, avoid_catching_errors)."),
    'ERR-004': ('repository-leaks-transport-exception', 'medium',
                "Repository method awaits a transport/persistence call with no try/catch mapping, so "
                "DioException/SocketException/FormatException reach the logic layer (AP-exceptions-across-layers)."),
    'ERR-005': ('throws-non-exception', 'medium',
                "Throws (or Future.error/completeError) a String, Map, List or number. Throw a typed "
                "Exception subclass so callers can `on` it and the stack trace means something (only_throw_errors)."),
    'ERR-006': ('domain-throws-transport', 'high',
                "Domain/use-case code throws or catches transport types (DioException, SocketException, "
                "PlatformException ...). The domain should only see domain failures; map in the repository."),
    'ERR-007': ('repository-null-on-failure', 'medium',
                "Repository turns a failure into `null` (catch returns null / catchError => null). Callers "
                "can't tell 'not found' from 'network down'; return a Result or throw a typed failure."),
    'ERR-008': ('raw-error-shown-to-user', 'medium',
                "Raw exception text (`e.toString()`, `'$e'`, `error.toString()`) goes into UI or UI state. "
                "Users see 'DioException [connection error]...'; map failures to user-safe, localized messages."),
    'ERR-009': ('mixed-result-and-throw', 'medium',
                "Repository mixes error styles: a Result/Either-returning method still throws/rethrows, or "
                "the same repository exposes both Result and throwing APIs. Callers can't know which to expect."),
    'ERR-010': ('loading-without-error-path', 'high',
                "Logic sets a loading state, then awaits outside any try/catch with no Result handling: on "
                "failure the UI stays loading forever and the error goes unhandled."),
    'ERR-011': ('rethrow-loses-stack', 'low',
                "`throw e;` re-throws the caught object and resets the stack trace. Use `rethrow;` "
                "(use_rethrow_when_possible), or Error.throwWithStackTrace when mapping."),
    'ERR-012': ('missing-global-error-handler', 'medium',
                "The app does not install both global handlers (FlutterError.onError for framework errors and "
                "PlatformDispatcher.instance.onError or runZonedGuarded for async errors). Uncaught errors are only printed."),
    'ERR-013': ('zone-mismatch', 'medium',
                "WidgetsFlutterBinding.ensureInitialized() runs outside the runZonedGuarded zone that calls runApp(): "
                "Flutter reports a 'Zone mismatch' and errors can escape the zone handler. Initialize inside the zone."),
    'ERR-014': ('unguarded-io-in-ui', 'medium',
                "A widget or State callback awaits a network call (http/dio client) with no try/catch: a timeout or "
                "offline error is unhandled and the user gets no feedback. Catch it, or move the call into logic."),
}

FIX_BY_PROFILE = {
    'mvn': "MVN: catch in the notifier and set the sealed XError state (user-safe message); one-time snackbars via ref.listen in the view.",
    'riverpod': "Riverpod: `state = await AsyncValue.guard(() => ...)`; render AsyncError in the switch; snackbars via ref.listen.",
    'bloc': "Bloc: try/catch around the await and emit(XFailure(...)) (or status: failure); snackbars via BlocListener.",
    'mvvm': "MVVM: repository returns Result; run the action through a Command and let the view listen for command.error.",
    'provider': "Provider: catch, store a typed failure, notifyListeners() in finally; the view shows it.",
    'getx': "GetX: try/catch, set an error observable, show Get.snackbar from a worker (ever).",
    'mvc': "MVC: catch in the controller, store a typed failure, notify the view.",
    'setstate': "setState: try/catch, then `if (!mounted) return; setState(() => _error = failure)`.",
    'unknown': "Catch at the logic boundary and turn the failure into UI state the view renders.",
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
IO_PACKAGES = {'dio', 'http', 'retrofit', 'chopper', 'graphql', 'graphql_flutter', 'sqflite', 'drift', 'hive',
               'hive_flutter', 'isar', 'objectbox', 'shared_preferences', 'flutter_secure_storage', 'cloud_firestore',
               'firebase_database', 'firebase_storage', 'firebase_auth', 'supabase_flutter', 'supabase',
               'web_socket_channel', 'grpc', 'path_provider', 'dart:io'}
TRANSPORT_TYPES = ('DioException', 'DioError', 'SocketException', 'HttpException', 'ClientException',
                   'HandshakeException', 'TlsException', 'FormatException', 'FirebaseException',
                   'FirebaseAuthException', 'PlatformException', 'MissingPluginException', 'DatabaseException',
                   'SqfliteDatabaseException', 'PostgrestException', 'GrpcError', 'FileSystemException',
                   'PathNotFoundException', 'HiveError', 'IsarError')
NETWORK_PACKAGES = {'dio', 'http', 'retrofit', 'chopper', 'graphql', 'graphql_flutter', 'web_socket_channel', 'grpc',
                    'supabase', 'supabase_flutter', 'cloud_firestore', 'firebase_database', 'firebase_storage',
                    'firebase_auth', 'cloud_functions', 'appwrite', 'ferry', 'socket_io_client'}
# For ERR-006, FormatException is a plain dart:core type that domain code may legitimately use.
DOMAIN_TRANSPORT_TYPES = tuple(t for t in TRANSPORT_TYPES if t != 'FormatException')
ERROR_TYPES = ('Error', 'StateError', 'TypeError', 'ArgumentError', 'RangeError', 'IndexError', 'AssertionError',
               'NoSuchMethodError', 'UnimplementedError', 'UnsupportedError', 'ConcurrentModificationError',
               'StackOverflowError', 'OutOfMemoryError', 'CastError', 'LateInitializationError', 'NullThrownError',
               'CyclicInitializationError', 'AbstractClassInstantiationError', 'FallThroughError',
               'JsonUnsupportedObjectError', 'JsonCyclicError')
CATCH_ALL_TYPES = ('', 'Object', 'dynamic', 'Object?')
# files[].role values (arch_check, phase 3) with nothing to check: export-only barrels and DI/composition files.
SKIP_ROLES = ('barrel', 'di')
REPORTERS = ('firebase_crashlytics', 'sentry_flutter', 'sentry', 'bugsnag_flutter', 'datadog_flutter_plugin',
             'instabug_flutter', 'newrelic_mobile', 'appcenter_crashes', 'raygun4flutter')
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'on', 'return', 'assert', 'super', 'this', 'new', 'await',
            'throw', 'else', 'do', 'try', 'when', 'in', 'is', 'as', 'yield', 'case', 'default', 'with'}
GUARD_NAMES = {'guard', 'runGuarded', 'safeCall', 'safeApiCall', 'tryCatch', 'runCatching', 'attempt',
               'catching', 'guarded', 'withErrorHandling', 'handleErrors', 'wrap', 'safely', 'runSafe'}

LOG_CALL = re.compile(r'(?<![\w.])(?:print|debugPrint|log|logError|logWarning|reportError|report|recordError|'
                      r'captureException|captureMessage|addBreadcrumb|onError|_log|_logError|_report|logger|_logger|'
                      r'talker|_talker|Log|Logger|developer|Sentry|FirebaseCrashlytics|crashlytics|_crashlytics|'
                      r'Crashlytics|errorReporter|_errorReporter|reporter|_reporter|FlutterError)\b\s*[.(]')
PRINT_ONLY_STMT = re.compile(r'^(?:print|debugPrint)\s*\(.*\)$', re.S)
DEFAULT_VALUE = (r'(?:null|false|true|-?\d+(?:\.\d+)?|\'\'|""|Duration\.zero|\w+\.empty\(\)|'
                 r'(?:const\s+)?(?:<[^>]*>\s*)?(?:\[\s*\]|\{\s*\})|const\s+\w+\(\s*\))')
RETURN_DEFAULT = re.compile(r'^return(?:\s+' + DEFAULT_VALUE + r')?\s*;$')
CLEANUP_STMT = re.compile(r'^(?:await\s+)?(?:unawaited\s*\(\s*)?[\w.?!()\[\]\s]*?\b(?:dispose|cancel|close|stop|kill|'
                          r'release|clear|detach|unsubscribe|unregister|remove\w*|delete\w*|_delete\w*|cleanup|cleanUp|'
                          r'flush|terminate|pause|unlisten|disconnect|reset)\w*\s*\(.*\)\s*\)?$', re.S)
PARSE_HINT = re.compile(r'\b(?:jsonDecode|json\.decode|\w*[pP]arse|fromJson|decode|base64Decode|utf8\.decode)\s*[(<]')
MAPPED_HINT = re.compile(r'\brethrow\b|\bthrow\b|Error\.throwWithStackTrace|completeError|addError|'
                         r'\b\w*(?:Failure|Failed|Error|Exception)\w*\s*(?:<[^>]*>)?\s*[.(]|\bResult\s*\.\s*\w+\s*\(|'
                         r'\b(?:Left|Err|Fail)\s*\(|handler\s*\.\s*(?:reject|next)\s*\(')
RESULT_AWARE = re.compile(r'\b(?:case|is)\s+(?:Ok|Error|Success|Failure|Left|Right|Err|Failed|ResultOk|ResultError)\b|'
                          r'\.fold\s*\(|\.match\s*\(|\.when\s*\(\s*(?:ok|success|data|left|right|failure|error)\s*:|'
                          r'\b(?:isOk|isError|isErr|isSuccess|isFailure|isLeft|isRight)\b|AsyncValue\s*\.\s*guard')
RESULT_TYPE = re.compile(r'^(?:Future|FutureOr)?\s*<?\s*(?:Result|Either|TaskEither|AsyncResult|ResultDart|Outcome|Try)\s*<|'
                         r'^(?:Result|Either|TaskEither|AsyncResult|ResultDart|Outcome)\s*<')
# `Future<Result>` (no type argument) and `Result<T>` after typedef resolution.
RESULT_BARE = re.compile(r'^(?:(?:Future|FutureOr)\s*<\s*)?(?:Result|Either|TaskEither|AsyncResult|ResultDart|Outcome)\b')
# Logging sinks: any callee or receiver whose name is a logger (`loggy.error(`, `_log.warning(`, `appLogger.e(`,
# `logError(`, `dPrint(`). `Dialog`/`catalog`/`login` don't match because `Log` must be capitalised mid-word.
LOG_ANY = re.compile(r'(?<![\w.])(?:_?[A-Za-z]\w*?(?:Log|Logger|Loggy|Logging)|_?[lL]og(?:ger|gy|ging|s)?|_?log[A-Z_]\w*|'
                     r'dPrint|talker|_talker)\s*(?:\(|\.\s*\w+\s*\()')
# Statements a best-effort UI call can fail on without anyone needing to know (K2: animateTo/jumpTo).
BEST_EFFORT_STMT = re.compile(r'^(?:await\s+)?[\w.?!()\[\]\s]*?\b(?:animateTo|jumpTo|animateToPage|jumpToPage|nextPage|previousPage|'
                              r'ensureVisible|scrollTo\w*|precacheImage|vibrate|HapticFeedback\s*\.\s*\w+|'
                              r'SystemChrome\s*\.\s*\w+|SystemSound\s*\.\s*\w+)\s*\(.*\)$', re.S)
COLLECTION_LOOKUP = re.compile(r'\.\s*(?:firstWhere|lastWhere|singleWhere|elementAt|reduce)\s*\(|\.\s*(?:first|last|single)\b(?!\s*\()')
ORNULL_NAME = re.compile(r'OrNull$|^_?try[A-Z_]')
PROBE_NAME = re.compile(r'^_?(?:is|has|can|check|supports|should|was)[A-Z_]')
WIDGET_HDR = re.compile(r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|HookWidget|'
                        r'HookConsumerWidget|StatefulHookWidget|StatefulHookConsumerWidget|GetView|GetWidget|'
                        r'(?:Consumer)?State\s*<|\w+State\s*<)')
STATE_HDR = re.compile(r'\bextends\s+(?:Consumer)?State\s*<|\bextends\s+\w+State\s*<')
UI_SINK = re.compile(r'\bGet\s*\.\s*(?:snackbar|dialog|defaultDialog|showSnackbar|bottomSheet|rawSnackbar)\b|'
                     r'\b\w*Toast\w*\s*[.(]|\bshowSnackBar\b|\bSnackBar\s*\(|\bshowDialog\s*[<(]')
ASYNC_PROVIDER = re.compile(r'\b(?:FutureProvider|StreamProvider|AsyncNotifierProvider|AsyncNotifier|StreamNotifier)\b|'
                            r'@riverpod\s+(?:Future|Stream)\s*<|AsyncValue\s*\.\s*guard')
NET_CALL = re.compile(r'\s*(?:widget\s*\.\s*)?(?:this\s*\.\s*)?_?\w*(?:[hH]ttp|[cC]lient|[dD]io|[aA]pi)\w*\s*[!?]?\s*\.\s*'
                      r'(?:get|post|put|patch|delete|head|send|request|fetch|download|upload)\w*\s*[<(]|'
                      r'\s*http\s*\.\s*(?:get|post|put|patch|delete|head|read)\s*\(')
PURE_CALLS = {'where', 'map', 'toList', 'toSet', 'contains', 'containsKey', 'any', 'every', 'fold', 'join', 'add', 'addAll',
              'remove', 'sort', 'copyWith', 'toString', 'expand', 'take', 'skip', 'forEach', 'putIfAbsent', 'delayed',
              'value', 'emit', 'notifyListeners', 'setState', 'print', 'debugPrint', 'unmodifiable', 'of', 'from',
              'generate', 'filled', 'empty', 'toUpperCase', 'toLowerCase', 'trim', 'split', 'substring', 'replaceAll',
              'isEmpty', 'isNotEmpty', 'clamp', 'abs', 'round', 'floor', 'ceil', 'now', 'max', 'min', 'identical'}
TYPEDEF_NEW_RE = re.compile(r'\btypedef\s+([A-Za-z_]\w*)\s*(?:<[^=;]*>)?\s*=\s*([^;]+);')
TYPEDEF_OLD_RE = re.compile(r'\btypedef\s+([^;=()]*?)\s*\b([A-Za-z_]\w*)\s*(?:<[^>;()]*>)?\s*\(([^;]*)\)\s*;')


# --------------------------------------------------------------------------- lexing

def lex(text):
    """Return (code, masked, comments, strings).

    code:    comments blanked (newlines kept), strings intact.
    masked:  comments and string *contents* blanked (quotes kept); safe for brace matching.
    comments/strings: lists of (start, end) spans.
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
            strings.append((i, j))
            i = j
        else:
            i += 1
    return ''.join(code), ''.join(masked), comments, strings


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


# --------------------------------------------------------------------------- per-file model

class DartFile(object):
    def __init__(self, root, rel):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.masked, self.comments, self.strings = lex(self.raw)
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
        self.comment_starts = [s for s, _ in self.comments]
        self.layer, self.role, self.feature = 'other', 'other', None
        self.imports = []          # (target, line) target: lib-relative path, package name or dart:x
        self.classes = []          # dicts
        self.funcs = []            # dicts
        self.tries = []            # dicts
        self.suppress_line = {}    # line -> {id: reason}
        self.suppress_file = {}    # id -> reason

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

    def has_comment(self, s, e):
        k = bisect.bisect_left(self.comment_starts, s)
        while k < len(self.comments) and self.comments[k][0] < e:
            txt = self.raw[self.comments[k][0]:self.comments[k][1]]
            if 'err-ignore' not in txt and 'ignore:' not in txt:
                return True
            k += 1
        return False


CLASS_RE = re.compile(r'\b((?:(?:abstract|sealed|final|base|interface|mixin)\s+)*)(class|mixin|enum|extension)\s+'
                      r'([A-Za-z_]\w*)?[^{;]*?\{')
IMPORT_RE = re.compile(r'^\s*(?:import|export)\s+[\'"]([^\'"]+)[\'"]', re.M)
TRY_RE = re.compile(r'\btry\s*\{')
CLAUSE_RE = re.compile(r'\s*(?:on\s+([A-Za-z_][\w.]*(?:\s*<[^{}()]*?>)?\??)\s*)?'
                       r'(?:catch\s*\(\s*(\w+)\s*(?:,\s*(\w+)\s*)?\))?\s*\{')
FINALLY_RE = re.compile(r'\s*finally\s*\{')
SUPPRESS_RE = re.compile(r'err-ignore(-file)?\s*:\s*((?:ERR-\d{3})(?:\s*,\s*ERR-\d{3})*)\s*(.*)')
ANNOT_RE = re.compile(r'@\w+(?:\.\w+)*(?:\s*\([^()]*(?:\([^()]*\)[^()]*)*\))?')


def parse_file(df, package):
    m, raw = df.masked, df.raw
    for mm in IMPORT_RE.finditer(df.code):
        uri = mm.group(1)
        ln = df.line_of(mm.start())
        if uri.startswith('dart:'):
            tgt = uri
        elif uri.startswith('package:'):
            pkg, _, rest = uri[8:].partition('/')
            tgt = 'lib/' + rest if pkg == package else pkg
        else:
            tgt = os.path.normpath(os.path.join(os.path.dirname(df.rel), uri)).replace(os.sep, '/')
        df.imports.append((tgt, ln))
    # suppressions
    for s, e in df.comments:
        sm = SUPPRESS_RE.search(raw[s:e])
        if not sm:
            continue
        ids = [x.strip() for x in sm.group(2).split(',')]
        reason = sm.group(3).strip().rstrip('*/').strip() or '(no reason given)'
        if sm.group(1):
            for i in ids:
                df.suppress_file[i] = reason
        else:
            ln = df.line_of(s)
            for i in ids:
                df.suppress_line.setdefault(ln, {})[i] = reason
    # classes
    for cm in CLASS_RE.finditer(m):
        o = cm.end() - 1
        if o not in df.braces:
            continue
        mods = cm.group(1) or ''
        df.classes.append({'name': cm.group(3) or '', 'kind': cm.group(2), 'open': o, 'close': df.braces[o],
                           'abstract': bool(re.search(r'\b(abstract|interface|sealed)\b', mods)) or cm.group(2) != 'class',
                           'header': m[cm.start():o]})
    class_opens = {c['open']: c for c in df.classes}
    # functions with block bodies
    for o in df.brace_opens:
        f = _func_header(df, o, class_opens)
        if f:
            f.update({'body_open': o, 'body_close': df.braces[o], 'arrow': False})
            df.funcs.append(f)
    # arrow functions
    for am in re.finditer(r'=>', m):
        f = _func_header(df, am.start(), class_opens, arrow=True)
        if f:
            end = _expr_end(df, am.end())
            f.update({'body_open': am.end(), 'body_close': end, 'arrow': True})
            df.funcs.append(f)
    df.funcs.sort(key=lambda f: f['body_open'])
    # try / catch
    for tm in TRY_RE.finditer(m):
        o = tm.end() - 1
        c = df.braces.get(o)
        if c is None:
            continue
        t = {'open': o, 'close': c, 'clauses': [], 'finally': None, 'start': tm.start()}
        pos = c + 1
        while True:
            cm = CLAUSE_RE.match(m, pos)
            if not cm or not (cm.group(1) or cm.group(2)):
                break
            bo = cm.end() - 1
            bc = df.braces.get(bo)
            if bc is None:
                break
            typ = (cm.group(1) or '').replace(' ', '')
            kw = cm.start(0) + len(cm.group(0)) - len(cm.group(0).lstrip())
            t['clauses'].append({'type': typ, 'var': cm.group(2), 'st': cm.group(3), 'start': kw,
                                 'body_open': bo, 'body_close': bc, 'line': df.line_of(kw)})
            pos = bc + 1
        fm = FINALLY_RE.match(m, pos)
        if fm and df.braces.get(fm.end() - 1):
            t['finally'] = (fm.end() - 1, df.braces[fm.end() - 1])
        if t['clauses'] or t['finally']:
            df.tries.append(t)


def _skip_back_ws(m, i):
    while i >= 0 and m[i] in ' \t\n\r':
        i -= 1
    return i


def _func_header(df, pos, class_opens, arrow=False):
    """If the `{` (or `=>`) at pos starts a function body, describe the function."""
    m = df.masked
    i = _skip_back_ws(m, pos - 1)
    for kw in ('async*', 'async', 'sync*'):
        if m[max(0, i - len(kw) + 1):i + 1] == kw and not _ident(m, i - len(kw)):
            i = _skip_back_ws(m, i - len(kw))
            break
    is_async = 'async' in m[i + 1:pos]
    if i < 0 or m[i] != ')':
        return None
    po = df.parens.get(i)
    if po is None:
        return None
    j = _skip_back_ws(m, po - 1)
    if j >= 0 and m[j] == '>':           # generic method: name<T>(
        depth = 0
        while j >= 0:
            if m[j] == '>':
                depth += 1
            elif m[j] == '<':
                depth -= 1
                if depth == 0:
                    break
            j -= 1
        j = _skip_back_ws(m, j - 1)
    e = j + 1
    while j >= 0 and _ident(m, j):
        j -= 1
    name = m[j + 1:e]
    if name and name in KEYWORDS:
        return None
    if name and name[0].isdigit():
        return None
    encl = df.innermost_brace(pos)
    if encl is not None:
        hdr = m[max(0, encl - 200):encl]
        if re.search(r'\bswitch\s*\([^{}]*\)\s*$', hdr):
            return None
    if not name:
        prev = m[_skip_back_ws(m, j)] if _skip_back_ws(m, j) >= 0 else ''
        if arrow and prev not in '(,:=[?{' and prev != '':
            return None
        return {'name': None, 'ret': '', 'header_start': po, 'is_async': is_async, 'lambda': True,
                'cls': None, 'member': False, 'line': df.line_of(po), 'params': (po, i)}
    # return type: text back to the previous statement boundary
    k = j
    while k >= 0 and m[k] not in ';{}':
        k -= 1
    ret = ANNOT_RE.sub(' ', m[k + 1:j + 1])
    ret = re.sub(r'\b(static|external|override|factory|const|late|final|covariant|required)\b', ' ', ret)
    ret = ' '.join(ret.split())
    if arrow and ret.endswith(('.', '?.', '!')):
        return None
    if arrow and not ret and m[_skip_back_ws(m, j)] not in ';{}' and _skip_back_ws(m, j) >= 0:
        return None
    cls = None
    member = False
    if encl is not None and encl in class_opens:
        cls = class_opens[encl]
        member = True
    return {'name': name, 'ret': ret, 'header_start': j + 1, 'is_async': is_async, 'lambda': False,
            'cls': cls, 'member': member, 'line': df.line_of(j + 1), 'params': (po, i)}


def _expr_end(df, i):
    m, n, depth = df.masked, len(df.masked), 0
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


# --------------------------------------------------------------------------- classification

def classify_fallback(rel, df):
    p = rel.lower()
    segs = p.split('/')
    dirs = segs[1:-1]
    base = segs[-1]
    layer = None
    for seg in dirs:
        if seg == 'domain':
            layer = 'domain'
            break
        if seg == 'data':
            layer = 'data'
            break
        if seg in ('presentation', 'ui', 'view', 'views', 'screens', 'pages', 'widgets'):
            layer = 'presentation'
            break
    if layer is None:
        if re.match(r'main[\w]*\.dart$', base) and len(segs) == 2:
            layer = 'app'
        elif any(s in ('di', 'injection', 'router', 'routes', 'routing') for s in dirs) or (dirs[:1] == ['app'] and len(dirs) == 1):
            layer = 'app'
        elif any(s in ('models', 'services', 'repositories', 'api', 'datasources', 'data_sources', 'sources') for s in dirs):
            layer = 'data'
        elif any(s in ('core', 'shared', 'common', 'utils') for s in dirs):
            layer = 'core'
    role = 'other'
    stem = base[:-5]
    if 'usecases' in dirs or 'use_cases' in dirs or stem.endswith(('_usecase', '_use_case')):
        role = 'usecase'
    elif 'entities' in dirs or stem.endswith('_entity'):
        role = 'entity'
    elif stem.endswith('_repository_impl') or (('repositories' in dirs) and layer != 'domain') or (stem.endswith('_repository') and layer == 'data'):
        role = 'repository-impl'
    elif stem.endswith('_repository') or 'repositories' in dirs:
        role = 'repository-contract'
    elif stem.endswith(('_dto', '_request', '_response')):
        role = 'dto'
    elif any(s in ('sources', 'datasources', 'data_sources', 'api', 'remote', 'local') for s in dirs) or \
            stem.endswith(('_source', '_api', '_client', '_datasource', '_data_source')):
        role = 'source'
    elif 'services' in dirs or stem.endswith('_service'):
        role = 'service'
    elif any(s in ('notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
                   'cubit', 'cubits', 'controller', 'controllers') for s in dirs) or \
            stem.endswith(('_notifier', '_view_model', '_viewmodel', '_bloc', '_cubit', '_controller', '_store')):
        role = 'logic'
    elif stem.endswith(('_event', '_events')):
        role = 'event'
    elif 'state' in dirs or stem.endswith('_state'):
        role = 'state'
    elif any(s in ('view', 'views', 'screens', 'pages') for s in dirs) or stem.endswith(('_screen', '_page', '_view')):
        role = 'view'
    elif 'widget' in dirs or 'widgets' in dirs:
        role = 'widget'
    feature = None
    for k, s in enumerate(dirs):
        if s in ('features', 'feature', 'modules') and k + 1 < len(dirs):
            feature = dirs[k + 1]
            break
    if layer is None:
        layer = {'usecase': 'domain', 'entity': 'domain', 'repository-contract': 'domain',
                 'repository-impl': 'data', 'dto': 'data', 'source': 'data', 'service': 'data',
                 'logic': 'presentation', 'state': 'presentation', 'view': 'presentation',
                 'widget': 'presentation', 'event': 'presentation'}.get(role, 'other')
    return layer, role, feature


LOGIC_CONTENT = re.compile(r'@riverpod\s+class\b|\bextends\s+_\$\w+|\bextends\s+(?:Cubit|Bloc|HydratedCubit|HydratedBloc|'
                           r'ChangeNotifier|StateNotifier|GetxController|AsyncNotifier|Notifier|FamilyAsyncNotifier|'
                           r'AutoDisposeAsyncNotifier|AutoDisposeNotifier|ValueNotifier)\b|\bwith\s+ChangeNotifier\b')
WIDGET_CONTENT = re.compile(r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|'
                            r'HookWidget|HookConsumerWidget|State<|ConsumerState<)')


def refine_role(df):
    """Content checks that both classification modes apply."""
    if df.role in ('other', 'service', 'widget') and LOGIC_CONTENT.search(df.masked) and df.layer not in ('domain', 'data'):
        df.role = 'logic'
    if df.role == 'other' and df.layer == 'presentation' and WIDGET_CONTENT.search(df.masked):
        df.role = 'widget'
    df.repo_classes = [c for c in df.classes if c['kind'] == 'class' and re.search(r'Repository', c['name'])]
    # `repository` (FX-A, phase 3): a concrete repository with no contract; same rules as an impl.
    df.is_repo_impl = df.role in ('repository-impl', 'repository') or (
        df.layer in ('data', 'core', 'other') and any(not c['abstract'] for c in df.repo_classes))
    df.is_repo_any = df.is_repo_impl or df.role == 'repository-contract' or bool(df.repo_classes)


# --------------------------------------------------------------------------- helpers

def body_text(df, s, e):
    return df.masked[s:e]


def stmts(text):
    return [x.strip() for x in re.split(r';', text) if x.strip()] if text.strip() else []


def is_catch_all(t):
    return t in CATCH_ALL_TYPES


def is_error_type(t):
    base = re.sub(r'<.*', '', t).rstrip('?')
    return base.split('.')[-1] in ERROR_TYPES


def inside_guard(df, pos, lo=0, hi=None):
    """pos is inside a try body (between lo/hi) with a catch clause that is not an Error-only catch."""
    for t in df.tries:
        if t['open'] < pos < t['close'] and (hi is None or (t['open'] >= lo and t['close'] <= hi)):
            if any(not is_error_type(c['type']) for c in t['clauses']):
                return True
    return False


def inside_any_catch(df, pos):
    for t in df.tries:
        for c in t['clauses']:
            if c['body_open'] < pos < c['body_close']:
                return True
    return False


def innermost_func(df, pos):
    best = None
    for f in df.funcs:
        if f['body_open'] <= pos < f['body_close']:
            if best is None or f['body_open'] >= best['body_open']:
                best = f
    return best


def f_ret_nullable(df, pos):
    f = innermost_func(df, pos)
    return bool(f and f['ret'].rstrip('>').rstrip().endswith('?'))


def stmt_start(df, pos):
    m = df.masked
    k = pos - 1
    depth = 0
    while k >= 0:
        ch = m[k]
        if ch in ')]':
            depth += 1
        elif ch in '([':
            if depth == 0:
                pass
            else:
                depth -= 1
        elif ch in ';{}' and depth <= 0:
            return k + 1
        k -= 1
    return 0


def raw_snippet(df, s, e, limit=120):
    return ' '.join(df.raw[s:e].split())[:limit]


def parse_params(text):
    """`(A a, {required B b, this.c})` contents -> {name: type or None}."""
    out, depth, buf, chunks = {}, 0, [], []
    for ch in text:
        if ch in '<(':
            depth += 1
        elif ch in '>)':
            depth -= 1
        if depth <= 0 and ch in ',{}[]':
            chunks.append(''.join(buf))
            buf = []
            continue
        buf.append(ch)
    chunks.append(''.join(buf))
    for c in chunks:
        c = ANNOT_RE.sub(' ', c)
        c = re.split(r'=(?![=>])', c)[0]
        c = re.sub(r'\b(?:required|final|covariant|var|late)\b', ' ', c).strip()
        if not c:
            continue
        m = re.match(r'(?s).*?\b(?:this|super)\s*\.\s*(\w+)$', c)
        if m:
            out[m.group(1)] = None
            continue
        m = re.match(r'(?s)(.+?)\s+([A-Za-z_$]\w*)$', c)
        if m:
            out[m.group(2)] = ' '.join(m.group(1).split())
    return out


def flatten_body(m, o, c):
    """Class body text at its own depth only: nested {...} collapse to {}."""
    out, depth, i = [], 0, o + 1
    while i < c:
        ch = m[i]
        if ch == '{':
            if depth == 0:
                out.append('{')
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                out.append('}')
        elif depth == 0:
            out.append(ch)
        i += 1
    return ''.join(out)


def class_members(df, cls):
    """Fields and method/getter signatures declared directly in a class body (including abstract ones)."""
    flat = flatten_body(df.masked, cls['open'], cls['close'])
    fields, methods = {}, {}
    for chunk in re.split(r'[;{}]', flat):
        ch = ANNOT_RE.sub(' ', chunk)
        ch = ch.split('=>')[0]
        ch = re.sub(r'\b(?:static|external|late|covariant|override|const|factory)\b', ' ', ch)
        ch = re.sub(r'\b(?:async\*?|sync\*)\s*$', '', ch.strip()).strip()
        if not ch:
            continue
        g = re.match(r'(?s)(.+?)\s+get\s+([A-Za-z_]\w*)$', ch)
        if g:
            methods[g.group(2)] = ' '.join(g.group(1).split())
            continue
        if ch.endswith(')'):
            depth, k = 0, len(ch) - 1
            while k >= 0:
                if ch[k] == ')':
                    depth += 1
                elif ch[k] == '(':
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            head = ch[:k].rstrip()
            head = re.sub(r'<[^<>]*(?:<[^<>]*>[^<>]*)*>$', '', head).rstrip()
            nm = re.match(r'(?s)(.*?)\s*\b([A-Za-z_]\w*)$', head)
            if nm and nm.group(1).strip() and nm.group(2) != cls['name'] and not nm.group(1).rstrip().endswith('.'):
                methods[nm.group(2)] = ' '.join(nm.group(1).split())
            continue
        decl = re.split(r'=(?![=>])', re.sub(r'^\s*(?:final|var)\s+', '', ch))[0].strip()
        fm = re.match(r'(?s)(.+?)\s+(_?[A-Za-z]\w*)$', decl)
        if fm and not re.search(r'\b(?:return|await|if|for|while|switch|case|throw|else)\b', fm.group(1)):
            fields[fm.group(2)] = ' '.join(fm.group(1).split())
    return {'fields': fields, 'methods': methods}


def class_supers(cls):
    hdr = re.sub(r'<[^{}]*?>', '', cls['header'])
    out = []
    for kw in ('extends', 'implements', 'with', 'on'):
        m = re.search(r'\b' + kw + r'\s+([\w\s,.]+?)(?=\b(?:extends|implements|with|on)\b|$)', hdr)
        if m:
            out += [x.strip().split('.')[-1] for x in m.group(1).split(',') if x.strip()]
    return out


# --------------------------------------------------------------------------- analysis

class Checker(object):
    def __init__(self, root, files, package, pubspec, profile):
        self.root, self.files, self.package, self.pubspec, self.profile = root, files, package, pubspec, profile
        self.by_rel = {f.rel: f for f in files}
        self.findings = []
        self.suppressed = []
        self._exposes = {}
        self.guard_names = set(GUARD_NAMES)
        for df in files:
            for f in df.funcs:
                if f['name'] and not f['lambda']:
                    seg = df.masked[f['header_start']:f['body_close']]
                    if 'catch' in seg and re.search(r'\bFunction\b|\(\s*\)\s*(?:async\s*)?=>', df.masked[f['header_start']:f['body_open']]):
                        self.guard_names.add(f['name'])
        self.handled_catches = set()
        # project indexes: typedefs, classes (+ who implements them), top-level functions
        self.typedefs = {}
        self.classes = {}
        self.implementors = {}
        self.top_funcs = {}
        self._members = {}
        self._infallible = {}
        self.loading_funcs = set()
        for df in files:
            for tm in TYPEDEF_NEW_RE.finditer(df.masked):
                self.typedefs.setdefault(tm.group(1), ' '.join(tm.group(2).split()))
            for tm in TYPEDEF_OLD_RE.finditer(df.masked):
                ret = ' '.join(tm.group(1).split())
                if ret and not tm.group(1).strip().startswith('='):
                    self.typedefs.setdefault(tm.group(2), '%s Function(%s)' % (ret, ' '.join(tm.group(3).split())))
            for c in df.classes:
                if c['name']:
                    self.classes.setdefault(c['name'], []).append((df, c))
                    for sup in class_supers(c):
                        self.implementors.setdefault(sup, []).append((df, c))
            for f in df.funcs:
                if f['name'] and not f['lambda'] and f['cls'] is None and df.innermost_brace(f['header_start']) is None:
                    self.top_funcs.setdefault(f['name'], []).append((df, f))

    # -- type resolution (typedefs, fields, parameters, project classes)
    def members(self, df, cls):
        k = (df.rel, cls['open'])
        if k not in self._members:
            self._members[k] = class_members(df, cls)
        return self._members[k]

    @staticmethod
    def class_of(df, pos):
        best = None
        for c in df.classes:
            if c['open'] < pos < c['close'] and (best is None or c['open'] > best['open']):
                best = c
        return best

    def resolve_alias(self, t, depth=0):
        t = ' '.join((t or '').split())
        if t.endswith('?') and t[:-1].strip() in self.typedefs:
            t = t[:-1].strip()
        m = re.match(r'([A-Za-z_]\w*)\s*(?:<.*>)?\s*$', t)
        if m and m.group(1) in self.typedefs and depth < 4:
            return self.resolve_alias(self.typedefs[m.group(1)], depth + 1)
        return t

    def call_return(self, t):
        """The value type of calling something of type t (a function type or a typedef of one)."""
        t = self.resolve_alias(t)
        k = t.rfind('Function')
        if k < 0:
            return None
        return t[:k].strip() or None

    def is_result(self, t, depth=0):
        if not t:
            return False
        t = ' '.join(t.split())
        if RESULT_TYPE.search(t) or RESULT_BARE.match(t):
            return True
        r = self.resolve_alias(t)
        if r != t and (RESULT_TYPE.search(r) or RESULT_BARE.match(r)):
            return True
        m = re.match(r'(?:Future|FutureOr)\s*<\s*(.*)>\s*\??$', r)
        if m and depth < 3:
            return self.is_result(m.group(1).strip(), depth + 1)
        return False

    def local_type(self, df, pos, cls, name):
        """Declared type of a parameter (of any enclosing function) or a field, else None."""
        for f in sorted((g for g in df.funcs if g['body_open'] <= pos < g['body_close']), key=lambda g: -g['body_open']):
            po, pc = f.get('params', (None, None))
            if po is not None:
                ps = parse_params(df.masked[po + 1:pc])
                if name in ps:
                    return ps[name]
        if cls is not None:
            t = self.members(df, cls)['fields'].get(name)
            if t:
                return t
        return None

    def lookup_class(self, typ):
        if not typ:
            return []
        m = re.match(r'([A-Za-z_]\w*)', self.resolve_alias(typ))
        return self.classes.get(m.group(1), []) if m else []

    def method_impls(self, df, cls, name, depth=0):
        """(df, func) bodies of `name` in cls or, for an abstract class, in its implementors."""
        out = [(df, f) for f in df.funcs if f['cls'] is cls and f['name'] == name and not f['lambda']]
        if not out and depth < 2:
            for d2, c2 in self.implementors.get(cls['name'], []):
                out += self.method_impls(d2, c2, name, depth + 1)
        return out

    def file_does_io(self, df):
        return any(t in IO_PACKAGES or t in NETWORK_PACKAGES for t, _ in df.imports)

    def infallible(self, df, f, depth=0):
        """The body can't fail with an I/O or parse error: no throw, no I/O import, only pure or infallible calls."""
        k = (df.rel, f['body_open'])
        if k in self._infallible:
            return self._infallible[k]
        self._infallible[k] = False
        ok = depth <= 2 and not self.file_does_io(df)
        body = df.masked[f['body_open']:f['body_close']]
        if ok and re.search(r'\bthrow\b|\brethrow\b|\bjsonDecode\b|json\s*\.\s*decode|completeError|Future\s*\.\s*error|!\s*[.;)]', body):
            ok = False
        if ok:
            for cm in re.finditer(r'([A-Za-z_]\w*)\s*(?:<[^<>()]*>)?\s*\(', body):
                nm = cm.group(1)
                if nm in KEYWORDS or nm in PURE_CALLS or nm[0].isupper():
                    continue
                before = body[:cm.start()].rstrip()
                if before.endswith('.'):
                    ok = False
                    break
                cands = self.top_funcs.get(nm, []) + [(df, g) for g in df.funcs if g['name'] == nm and g['cls'] is f['cls']
                                                      and not g['lambda'] and g is not f]
                if not cands or not all(self.infallible(d2, g, depth + 1) for d2, g in cands):
                    ok = False
                    break
        self._infallible[k] = ok
        return ok

    def callee_kind(self, df, f, q):
        """What the awaited call at q returns: 'result' (a Result, so it doesn't throw by convention),
        'infallible' (a project method that can't fail), or None (unknown: treat as throwing)."""
        expr = df.masked[q:_expr_end(df, q)]
        mm = re.match(r'\s*(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*(?:(?:\?\.|\.|!\s*\.)\s*([A-Za-z_]\w*))?\s*'
                      r'(?:<[^<>()]*(?:<[^<>()]*>)?[^<>()]*>)?\s*(\()?', expr)
        if not mm:
            return None
        a, b = mm.group(1), mm.group(2)
        cls = self.class_of(df, q)
        if b is None:
            t = self.local_type(df, q, cls, a)
            if t is not None:
                return 'result' if self.is_result(self.call_return(t)) else None
            if cls is not None:
                sig = self.members(df, cls)['methods'].get(a)
                if sig and self.is_result(sig):
                    return 'result'
                impls = [(df, g) for g in df.funcs if g['cls'] is cls and g['name'] == a and not g['lambda']]
                if impls:
                    return 'infallible' if all(self.infallible(d2, g) for d2, g in impls) else None
            tops = self.top_funcs.get(a, [])
            if tops:
                if all(self.is_result(g['ret']) for _, g in tops):
                    return 'result'
                if all(self.infallible(d2, g) for d2, g in tops):
                    return 'infallible'
            return None
        t = self.local_type(df, q, cls, a)
        for d2, c2 in self.lookup_class(t):
            sig = self.members(d2, c2)['methods'].get(b)
            if sig and self.is_result(sig):
                return 'result'
            impls = self.method_impls(d2, c2, b)
            if impls and all(self.infallible(d3, g) for d3, g in impls):
                return 'infallible'
        return None

    def receiver_is_safe(self, df, pos, name):
        """ERR-004: the receiver is a project class whose files neither do network I/O nor leak it."""
        cls = self.class_of(df, pos)
        hits = self.lookup_class(self.local_type(df, pos, cls, name))
        if not hits:
            return False
        for d2, c2 in hits:
            for d3, _ in [(d2, c2)] + self.implementors.get(c2['name'], []):
                if d3 is df or self.reaches_io(d3):
                    return False
        return True

    def reaches_io(self, df, depth=0, seen=None):
        """df, or a project file it imports (3 levels), does network I/O; mapping is not considered."""
        seen = set() if seen is None else seen
        if df.rel in seen:
            return False
        seen.add(df.rel)
        if self.uses_io(df):
            return True
        if depth >= 3:
            return False
        return any(self.reaches_io(self.by_rel[t], depth + 1, seen) for t, _ in df.imports if t in self.by_rel)

    # -- finding plumbing
    def add(self, df, rid, line, evidence, severity=None, note='', key=None):
        name, sev, msg = RULES[rid]
        sev = severity or sev
        reason = None
        if df is not None:
            reason = df.suppress_file.get(rid)
            if reason is None:
                for ln in (line, line - 1, line + 1):
                    r = df.suppress_line.get(ln, {}).get(rid)
                    if r is not None:
                        reason = r
                        break
        rel = df.rel if df is not None else 'lib/'
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': rel, 'line': line, 'reason': reason})
            return
        self.findings.append({'id': rid, 'name': name, 'severity': sev, 'file': rel, 'line': line,
                              'evidence': evidence, 'message': msg, 'note': note})

    def fix_hint(self):
        return FIX_BY_PROFILE.get(self.profile, FIX_BY_PROFILE['unknown'])

    # -- transport exposure across imports
    def uses_io(self, df):
        """Network transport only: local persistence failures (drift, hive, prefs) are not what ERR-004 is about."""
        for t, _ in df.imports:
            if t in NETWORK_PACKAGES:
                return True
            if t == 'dart:io' and re.search(r'\b(?:HttpClient|Socket|WebSocket|RawSocket|SecureSocket|InternetAddress)\b', df.masked):
                return True
        return False

    def network_imports(self, df):
        out = sorted(t for t, _ in df.imports if t in NETWORK_PACKAGES)
        if not out and self.uses_io(df):
            out = ['dart:io sockets/HttpClient']
        return out

    def maps_errors(self, df):
        """The file catches failures and turns them into something else (throw/Result/failure)."""
        for t in df.tries:
            for c in t['clauses']:
                if is_error_type(c['type']):
                    continue
                b = body_text(df, c['body_open'] + 1, c['body_close'])
                own = re.escape(c['var']) if c['var'] and c['var'] != '_' else r'(?!x)x'
                if re.search(r'\bthrow\s+(?!' + own + r'\s*;)|Error\.throwWithStackTrace|\bResult\s*\.\s*\w+\s*\(|'
                             r'\b\w*(?:Failure|Failed|Exception)\w*\s*[.(]|\b(?:Left|Err|Error)\s*\(', b):
                    return True
        if any(self.is_result(f['ret']) for f in df.funcs if f['member'] and f['name'] and not f['name'].startswith('_')):
            return True
        return False

    def exposes_transport(self, df, depth=0):
        if df.rel in self._exposes:
            return self._exposes[df.rel]
        self._exposes[df.rel] = False
        res = False
        if df.layer not in ('presentation', 'domain') and df.role not in ('dto', 'entity', 'state', 'event'):
            if self.maps_errors(df):
                res = False
            elif self.uses_io(df):
                res = True
            elif depth < 3:
                for tgt, _ in df.imports:
                    dep = self.by_rel.get(tgt)
                    if dep is not None and dep is not df and self.exposes_transport(dep, depth + 1):
                        res = True
                        break
        self._exposes[df.rel] = res
        return res

    def repo_deps_expose(self, df):
        if self.uses_io(df):
            return 'imports ' + ', '.join(self.network_imports(df))
        for tgt, _ in df.imports:
            dep = self.by_rel.get(tgt)
            if dep is None or dep is df:
                continue
            if dep.role in ('source', 'service', 'other', 'repository-impl') and self.exposes_transport(dep):
                return 'depends on %s, which does I/O without mapping its exceptions' % tgt
        return None

    # -- rules
    def run(self):
        for df in self.files:
            if df.role in SKIP_ROLES:
                continue
            self.check_catches(df)
            self.check_callbacks(df)
            self.check_throws(df)
            self.check_domain(df)
            self.check_repository(df)
            self.check_raw_message(df)
            self.check_loading(df)
            self.check_ui_io(df)
            self.check_zone(df)
        self.check_global()

    def check_catches(self, df):
        for t in df.tries:
            try_body = body_text(df, t['open'] + 1, t['close'])
            try_stmts = stmts(re.sub(r'\bif\s*\([^)]*\)\s*', '', try_body))
            cleanup = bool(try_stmts) and all(CLEANUP_STMT.match(s) for s in try_stmts)
            best_effort = bool(try_stmts) and not cleanup and all(CLEANUP_STMT.match(s) or BEST_EFFORT_STMT.match(s)
                                                                  for s in try_stmts)
            has_await = bool(re.search(r'\bawait\b', try_body))
            collection_only = not has_await and bool(COLLECTION_LOOKUP.search(try_body)) and \
                not re.search(r'[\w)\]]\s*[?!]?\.\s*(?!(?:firstWhere|lastWhere|singleWhere|elementAt|reduce|where|map|toList|'
                              r'contains|any|every|cast)\b)\w+\s*\(', try_body)
            io_try = has_await or (not collection_only and bool(re.search(r'[\w)\]]\s*[?!]?\.\s*\w+\s*\(', try_body)))
            owner = None
            for g in df.funcs:
                if not g['lambda'] and g['name'] and g['body_open'] <= t['open'] < g['body_close'] and \
                        (owner is None or g['body_open'] > owner['body_open']):
                    owner = g
            oname = owner['name'] if owner else ''
            oret = ' '.join(owner['ret'].split()) if owner else ''
            last_try = try_stmts[-1] if try_stmts else ''
            for c in t['clauses']:
                b = body_text(df, c['body_open'] + 1, c['body_close'])
                bs = stmts(b)
                evid = raw_snippet(df, c['start'], c['body_close'] + 1)
                eol = df.raw.find('\n', c['body_close'])
                documented = df.has_comment(c['body_open'], c['body_close']) or \
                    df.has_comment(c['start'], c['body_open'] + 1) or \
                    df.has_comment(c['body_close'], eol if eol >= 0 else len(df.raw))
                typ = c['type']
                var = c['var']
                # ERR-003
                if typ and is_error_type(typ):
                    self.add(df, 'ERR-003', c['line'], evid,
                             note='documented: confirm the API really signals expected failures with %s' % typ if documented else '')
                # ERR-011
                if var and re.search(r'\bthrow\s+' + re.escape(var) + r'\s*;', b):
                    self.add(df, 'ERR-011', df.line_of(c['body_open'] + 1 + re.search(r'\bthrow\s+' + re.escape(var), b).start()), evid)
                # ERR-007 (repository returns null on failure): only when the try does I/O (K1-E2)
                if df.is_repo_impl and io_try and re.search(r'\breturn\s+null\s*;', b):
                    self.add(df, 'ERR-007', c['line'], evid)
                    continue
                swallowed = None
                if not bs:
                    swallowed = 'empty'
                elif len(bs) == 1 and RETURN_DEFAULT.match(bs[0] + ';'):
                    swallowed = 'returns a default'
                elif all(PRINT_ONLY_STMT.match(s) for s in bs):
                    swallowed = 'print-only'
                if swallowed:
                    sev, note = 'high', ''
                    if cleanup and documented:
                        sev, note = 'info', 'documented best-effort cleanup'
                    elif cleanup:
                        sev, note = 'low', 'best-effort cleanup (try body only disposes/cancels/closes); add a comment or a log line'
                    elif documented:
                        sev, note = 'info', 'documented with a comment; confirm the fallback is right and consider logging it'
                    elif best_effort:
                        sev, note = 'low', 'best-effort UI call (scroll/animate/haptics); add a comment or a log line'
                    elif swallowed == 'returns a default' and bs[0].replace(' ', '') == 'returnnull' and \
                            ORNULL_NAME.search(oname) and oret.rstrip('>').rstrip().endswith('?'):
                        sev, note = 'info', ('`%s` is a null-on-failure API by name (xOrNull/tryX); fine if callers treat '
                                             'null as "unavailable"' % oname)
                    elif swallowed == 'returns a default' and bs[0].replace(' ', '') == 'returnfalse' and \
                            re.match(r'^(?:Future\s*<\s*)?bool\s*>?$', oret) and \
                            (PROBE_NAME.search(oname) or last_try.replace(' ', '') == 'returntrue'):
                        sev, note = 'low', 'capability probe (bool, catch -> false); consider logging the failure'
                    elif collection_only:
                        sev, note = 'low', 'collection lookup, no I/O: use firstWhereOrNull (package:collection) instead of catching'
                    elif swallowed == 'print-only':
                        sev, note = 'medium', 'print/debugPrint only: release builds lose it; report it or map it'
                    elif swallowed == 'returns a default' and typ.split('.')[-1] == 'FormatException' and \
                            (PARSE_HINT.search(try_body) or (f_ret_nullable(df, c['body_open']))):
                        sev, note = 'low', 'tryParse idiom (on FormatException -> default); fine for parsers, document it'
                    elif typ and not is_catch_all(typ) and typ != 'Exception':
                        sev, note = 'medium', 'narrow `on %s` catch; still say why the failure is ignored' % typ
                    elif swallowed == 'returns a default' and PARSE_HINT.search(try_body):
                        sev, note = 'medium', 'parse fallback: prefer `on FormatException` / tryParse and log corrupt input'
                    self.add(df, 'ERR-001', c['line'], evid, severity=sev, note=(swallowed + '; ' + note).strip('; '))
                    continue
                # ERR-002
                if df.layer in ('data', 'domain') and is_catch_all(typ):
                    bc = df.code[c['body_open'] + 1:c['body_close']]
                    uses_var = any(v and v != '_' and re.search(r'(?<![\w.])\$?\{?' + re.escape(v) + r'\b', bc)
                                   for v in (var, c['st']))
                    if not (uses_var or MAPPED_HINT.search(b) or LOG_CALL.search(b)):
                        if documented:
                            sev, note = 'info', 'documented fallback; prefer catching the specific exception types'
                        elif re.search(r'\bawait\b|[\w)]\s*\.\s*\w+\s*\(', b):
                            sev, note = 'low', ('fallback attempt (the catch tries another way); catch the specific exception, '
                                                'or a bug in the first attempt silently takes the fallback')
                        else:
                            sev, note = 'medium', 'the error value is dropped; catch specific types, map to a failure, or log it'
                        self.add(df, 'ERR-002', c['line'], evid, severity=sev, note=note)

    def check_callbacks(self, df):
        rx = re.compile(r'(\.catchError\s*\(|\bonError\s*:\s*)\(([^()]*)\)\s*(?:async\s*)?(\{\s*\}|=>\s*(' + DEFAULT_VALUE + r')\s*(?=[,)]))')
        for mm in rx.finditer(df.masked):
            ln = df.line_of(mm.start())
            evid = raw_snippet(df, mm.start(), mm.end())
            val = (mm.group(4) or '').strip()
            if df.is_repo_impl and val == 'null':
                self.add(df, 'ERR-007', ln, evid)
                continue
            ss = stmt_start(df, mm.start())
            above = df.line_starts[max(0, df.line_of(ss) - 3)]
            documented = df.has_comment(above, _expr_end(df, mm.end()) + 1)
            stmt = df.masked[ss:mm.start()]
            if documented:
                sev, note = 'info', 'documented with a comment; confirm nothing needs to react to this failure'
            elif re.search(r'\bunawaited\s*\(', stmt):
                sev, note = 'medium', 'fire-and-forget: say why the failure is irrelevant, or use .ignore() to state intent'
            elif 'onError' in mm.group(1):
                sev, note = 'high', 'stream/future errors are dropped silently'
            else:
                sev, note = 'high', ''
            self.add(df, 'ERR-001', ln, evid, severity=sev, note=note)

    def check_throws(self, df):
        rx = re.compile(r'\bthrow\s+(?:const\s+)?(?:r?[\'"]|\{|<\w|\[|\d)|\bFuture(?:\s*<[^>]*>)?\s*\.\s*error\s*\(\s*(?:r?[\'"]|\{)|'
                        r'\bcompleteError\s*\(\s*(?:r?[\'"]|\{)|\bthrow\s+\w+\s*\.\s*toString\s*\(\s*\)')
        for mm in rx.finditer(df.masked):
            ln = df.line_of(mm.start())
            self.add(df, 'ERR-005', ln, df.line_text(ln)[:120])

    def check_domain(self, df):
        if df.layer != 'domain':
            return
        names = '|'.join(DOMAIN_TRANSPORT_TYPES)
        for mm in re.finditer(r'\bthrow\s+(?:const\s+)?(?:\w+\.)?(' + names + r')\b', df.masked):
            ln = df.line_of(mm.start())
            self.add(df, 'ERR-006', ln, df.line_text(ln)[:120])
        for mm in re.finditer(r'(?:\bon\s+(?:\w+\.)?|\bis\s+(?:\w+\.)?)(' + names + r')\b', df.masked):
            ln = df.line_of(mm.start())
            self.add(df, 'ERR-006', ln, df.line_text(ln)[:120], severity='medium',
                     note='the domain knows a transport type; let the repository map it to a domain failure')

    def check_repository(self, df):
        if not df.is_repo_any:
            return
        hint = self.fix_hint()
        # ERR-009
        members = [f for f in df.funcs if f['member'] and f['name'] and f['cls'] is not None
                   and 'Repository' in (f['cls']['name'] or '') and not f['lambda']]
        result_funcs = [f for f in members if self.is_result(f['ret'])]
        sigs = []
        aliases = '|'.join(re.escape(n) for n in sorted(self.typedefs) if self.is_result(n))
        sig_rx = re.compile(r'(?m)^\s*((?:Future|FutureOr)\s*<.*?>|(?:Result|Either|TaskEither)\s*<.*?>' +
                            (r'|(?:' + aliases + r')\b(?:\s*<.*?>)?' if aliases else '') +
                            r')\??\s+([a-z]\w*)\s*(?:<[^>]*>)?\s*\(')
        for c in df.repo_classes:
            for sm in sig_rx.finditer(df.masked[c['open']:c['close']]):
                sigs.append((sm.group(1), sm.group(2), df.line_of(c['open'] + sm.start(2))))
        res_sigs = [s for s in sigs if self.is_result(s[0])]
        if result_funcs or res_sigs:
            for f in result_funcs:
                b = df.masked[f['body_open']:f['body_close']]
                for tm in re.finditer(r'\bthrow\b(?!\s+(?:const\s+)?(?:UnimplementedError|UnsupportedError|StateError|ArgumentError|AssertionError)\b)|\brethrow\b', b):
                    tp = f['body_open'] + tm.start()
                    if tm.group(0) == 'throw' and inside_guard(df, tp, f['body_open'], f['body_close'] + 1):
                        continue
                    ln = df.line_of(tp)
                    self.add(df, 'ERR-009', ln, df.line_text(ln)[:120],
                             note='`%s` returns %s but throws here' % (f['name'], f['ret'][:60]))
            plain = [s for s in sigs if not self.is_result(s[0]) and not re.match(r'Future\s*<\s*void\s*>', s[0])
                     and not s[1].startswith('_')]
            has_contract = any(self.by_rel.get(t) is not None and self.by_rel[t].role == 'repository-contract'
                               for t, _ in df.imports) and df.role != 'repository-contract'
            if plain and res_sigs and not has_contract:
                s = plain[0]
                self.add(df, 'ERR-009', s[2], '%s %s(...) next to %s %s(...)' % (s[0][:50], s[1], res_sigs[0][0][:50], res_sigs[0][1]),
                         severity='low', note='%d Result-returning and %d throwing-style methods in one repository' % (len(res_sigs), len(plain)))
        if not df.is_repo_impl:
            return
        # ERR-004
        why = self.repo_deps_expose(df)
        leaky = []
        memo = {}
        for f in members:
            if f['name'].startswith('_') or (f['cls'] and f['cls']['abstract']):
                continue
            p = self.unguarded_risk(df, f, bool(why), memo, 0)
            if p is not None:
                leaky.append((f, p))
        sev4, tail4 = self.err004_grade(df)
        if leaky:
            f0, p0 = leaky[0]
            names = ', '.join(f['name'] for f, _ in leaky[:6]) + (' ...' if len(leaky) > 6 else '')
            ln = df.line_of(p0)
            parse_only = not why
            self.add(df, 'ERR-004', f0['line'],
                     '%d public method(s) unguarded: %s; first: %s' % (len(leaky), names, df.line_text(ln)[:80]),
                     severity=sev4,
                     note='%s; map DioException/SocketException/ClientException/FormatException to a domain failure or Result '
                          'at this boundary%s' % ('jsonDecode outside try' if parse_only else why, tail4))
        if not why:
            return
        if not leaky:
            # K2 (ResoCoder): the awaits sit inside `on ServerException` only; the transport errors the source
            # throws (ClientException, SocketException, FormatException) are not covered.
            narrow = []
            for f in members:
                if f['name'].startswith('_') or (f['cls'] and f['cls']['abstract']):
                    continue
                ts = self.narrow_catches(df, f, memo)
                if ts:
                    narrow.append((f, ts))
            if narrow:
                types = sorted(set().union(*[ts for _, ts in narrow]))
                names = ', '.join(f['name'] for f, _ in narrow[:6]) + (' ...' if len(narrow) > 6 else '')
                self.add(df, 'ERR-004', narrow[0][0]['line'],
                         '%d public method(s) catch only %s: %s' % (len(narrow), '/'.join(types), names),
                         severity=sev4,
                         note='%s; the typed catch does not cover what the source throws (ClientException, SocketException, '
                              'FormatException ...): map those too, or have the source convert them%s' % (why, tail4))
        # ERR-004 variant: catch that rethrows transport unmapped
        for t in df.tries:
            for c in t['clauses']:
                b = body_text(df, c['body_open'] + 1, c['body_close'])
                if re.search(r'\brethrow\b', b) and not re.search(r'\bthrow\b', b) and \
                        (is_catch_all(c['type']) or c['type'].split('.')[-1] in TRANSPORT_TYPES or c['type'] == 'Exception'):
                    f = innermost_func(df, c['body_open'])
                    if f and f['name'] and f['name'].startswith('_'):
                        continue
                    self.add(df, 'ERR-004', c['line'], raw_snippet(df, c['start'], c['body_close'] + 1), severity=sev4,
                             note='%s; rethrows the transport exception instead of mapping it%s' % (why, tail4))

    def err004_grade(self, df):
        """K3-E6: under plain Riverpod a repository read by a FutureProvider/AsyncNotifier has its exceptions caught
        into AsyncValue.error, so the leak is a mapping issue for the view (ERR-008), not a crash: grade low."""
        if self.profile != 'riverpod':
            return None, ''
        names = [c['name'] for c in df.repo_classes if c['name']]
        names += re.findall(r'\b(\w+Provider)\s*=', df.masked)
        names += [m + 'Provider' for m in re.findall(r'@riverpod\s+[\w<>?,\s]*?\b(\w+)\s*\(\s*\w*Ref\b', df.masked)]
        if not names:
            return None, ''
        rx = re.compile(r'\b(?:' + '|'.join(re.escape(n) for n in set(names)) + r')\b')
        for other in self.files:
            if ASYNC_PROVIDER.search(other.masked) and rx.search(other.masked if other is not df else
                                                                 re.sub(r'\bclass\s+\w+', ' ', other.masked)):
                return 'low', ('; it feeds a FutureProvider/AsyncNotifier (%s), so callers get AsyncValue.error: '
                               'check the view maps it to user-safe text (ERR-008)' % other.rel)
        return None, ''

    CALLEE_RE = re.compile(r'[(\s]*(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*(\?\.|\.|!|\(|<)?')

    @staticmethod
    def narrow_try(df, p, lo, hi):
        """Types of the innermost try (within lo..hi) around p when every clause catches only narrow,
        non-transport types (`on ServerException`), and no broader try encloses it; else None."""
        around = [t for t in df.tries if t['open'] < p < t['close'] and t['clauses'] and t['open'] >= lo and t['close'] <= hi]
        if not around:
            return None
        types = set()
        for t in around:
            for c in t['clauses']:
                base = c['type'].split('.')[-1].rstrip('?')
                if is_catch_all(c['type']) or base in ('Exception', 'Object') or base in TRANSPORT_TYPES:
                    return None
                if not is_error_type(c['type']):
                    types.add(base)
        return types or None

    def narrow_catches(self, df, f, memo, depth=0):
        """Narrow catch types guarding awaits in f (or in local helpers it awaits)."""
        key = ('narrow', f['body_open'])
        if key in memo:
            return memo[key]
        memo[key] = set()
        out = set()
        body = df.masked[f['body_open']:f['body_close']]
        local = {g['name']: g for g in df.funcs if g['name'] and not g['lambda']}
        for a in re.finditer(r'\b(?:await|return)\b', body):
            p = f['body_open'] + a.start()
            ts = self.narrow_try(df, p, f['body_open'], f['body_close'] + 1)
            if ts and a.group(0) == 'await':
                out |= ts
            cm = self.CALLEE_RE.match(df.masked, f['body_open'] + a.end())
            if cm and cm.group(2) == '(' and depth < 3:
                g = local.get(cm.group(1))
                if g is not None and g is not f:
                    out |= self.narrow_catches(df, g, memo, depth + 1)
        memo[key] = out
        return out

    def unguarded_risk(self, df, f, network, memo, depth):
        """Position of the first operation in f that can throw a transport/parse exception unguarded, else None."""
        key = f['body_open']
        if key in memo:
            return memo[key]
        memo[key] = None
        body = df.masked[f['body_open']:f['body_close']]
        if RESULT_AWARE.search(body) or any(re.search(r'(?<![\w.])' + re.escape(g) + r'\s*(?:<[^>]*>)?\s*\(', body)
                                            for g in self.guard_names):
            return None
        local = {}
        for g in df.funcs:
            if g['name'] and not g['lambda'] and g['name'] not in local:
                local[g['name']] = g
        risky = [f['body_open'] + m.start() for m in re.finditer(r'\b(?:jsonDecode|json\s*\.\s*decode)\s*\(', body)]
        if network:
            starts = [f['body_open'] + a.end() for a in re.finditer(r'\bawait\b', body)]
            if re.match(r'(?:Future|FutureOr)\b', f['ret']) and (f['arrow'] or not f['is_async']):
                if f['arrow']:
                    starts.append(f['body_open'])
                starts += [f['body_open'] + r.end() for r in re.finditer(r'\breturn\b(?!\s+await\b)', body)]
            for s in starts:
                cm = self.CALLEE_RE.match(df.masked, s)
                if not cm:
                    continue
                name, nxt = cm.group(1), cm.group(2)
                if name in ('Future', 'Stream', 'Completer', 'unawaited'):
                    continue
                if nxt in ('(', '<'):
                    g = local.get(name)
                    if g is None or g is f or depth > 3:
                        continue
                    if self.unguarded_risk(df, g, network, memo, depth + 1) is not None:
                        risky.append(s)
                elif nxt in ('.', '?.', '!'):
                    if name in ('ref', 'context', 'widget') or not self.receiver_is_safe(df, s, name):
                        risky.append(s)
        for p in sorted(risky):
            if not inside_guard(df, p, f['body_open'], f['body_close'] + 1) and not inside_any_catch(df, p):
                memo[key] = p
                return p
        return None

    def callback_scope(self, df, start):
        """(open, end) of a `(params) => expr` / `(params) { ... }` callback whose `(` is at or after start."""
        o = df.masked.find('(', start)
        c = df.parens.get(o)
        if o < 0 or c is None:
            return None
        k = c + 1
        while k < len(df.masked) and df.masked[k] in ' \t\n':
            k += 1
        if df.masked.startswith('async', k):
            k += 5
            while k < len(df.masked) and df.masked[k] in ' \t\n':
                k += 1
        if df.masked.startswith('=>', k):
            return (o, _expr_end(df, k + 2))
        if k < len(df.masked) and df.masked[k] == '{' and k in df.braces:
            return (o, df.braces[k])
        return (o, c)

    def check_raw_message(self, df):
        if df.role in ('event',):
            return
        ui_classes = [c for c in df.classes if WIDGET_HDR.search(c['header'])]
        if df.layer != 'presentation' and df.role not in ('view', 'widget', 'logic', 'state') and not ui_classes:
            return
        glob = {'error', 'err', 'exception', 'failure', 'ex', 'exc'}
        scoped = []                                   # (name, lo, hi): K3-E3, a catch variable only means "error" in its block
        for t in df.tries:
            for c in t['clauses']:
                if c['var'] and c['var'] != '_':
                    scoped.append((c['var'], c['body_open'], c['body_close']))
        for mm in re.finditer(r'\b(error|onError|failure|errorBuilder)\s*:\s*\(\s*(?:\w+\s+)?(\w+)\s*(?:,\s*(?:\w+\s+)?(\w+))?', df.masked):
            kind, first, second = mm.group(1), mm.group(2), mm.group(3)
            sc = self.callback_scope(df, mm.end(1))
            if sc is None:
                continue
            if kind == 'errorBuilder':          # (context, error, stack)
                if second:
                    scoped.append((second, sc[0], sc[1]))
            elif first in ('context', 'ctx', '_', 'message', 'msg', 'text', 'reason', 'description', 'title'):
                continue
            elif kind == 'onError' or second or first in glob:
                # AsyncValue.when(error: (e, st)), onError: (e[, st]); a one-param `error:` callback of a
                # custom sealed/freezed state usually receives an already-mapped message, so skip it.
                scoped.append((first, sc[0], sc[1]))
        for mm in re.finditer(r'\.\s*catchError\s*\(\s*\(\s*(?:\w+\s+)?(\w+)', df.masked):     # K2-FN-3
            o = df.masked.find('(', mm.start())
            if df.parens.get(o) is not None:
                scoped.append((mm.group(1), o, df.parens[o]))
        for mm in re.finditer(r'\bAsyncError\s*(?:<[^>]*>)?\s*\(\s*(?:error\s*)?:\s*(?:final\s+)?(?:\w+\s+)?(\w+)', df.masked):
            glob.add(mm.group(1))
        glob.discard('_')

        def is_err(name, pos):
            if name is None or name in glob:
                return True
            return any(n == name and lo < pos < hi for n, lo, hi in scoped)

        p_tostring = re.compile(r'(?<![\w.$])([A-Za-z_]\w*)\s*[?!]?\s*\.\s*toString\s*\(\s*\)|'
                                r'\.\s*(?:error|exception)\s*[?!]?\s*\.\s*toString\s*\(\s*\)')
        p_interp = re.compile(r'\$([A-Za-z_]\w*)\b|\$\{\s*([A-Za-z_]\w*)\s*[?!]?\s*(?:\.\s*toString\s*\(\s*\))?\s*\}|'
                              r'\$\{\s*[\w.?!]*\.\s*(?:error|exception)\s*[?!]?\s*(?:\.\s*toString\s*\(\s*\))?\s*\}')
        compare_after = re.compile(r'\s*(?:\.\s*(?:toLowerCase|toUpperCase|trim)\s*\(\s*\)\s*)*'
                                   r'(?:\.\s*(?:contains|startsWith|endsWith|indexOf|compareTo|matchAsPrefix)\s*\(|[=!]=)')
        hits = []
        for mm in p_tostring.finditer(df.masked):
            if not is_err(mm.group(1), mm.start()):
                continue
            if compare_after.match(df.masked, mm.end()) or re.search(r'[=!]=\s*$', df.masked[max(0, mm.start() - 12):mm.start()]):
                continue                        # K1/K3-E3: a comparison, not display
            hits.append(mm.start())
        for s, e in df.strings:
            seg = df.code[s:e]
            for mm in p_interp.finditer(seg):
                if is_err(mm.group(1) or mm.group(2), s + mm.start()):
                    hits.append(s + mm.start())
            for mm in p_tostring.finditer(seg):
                if is_err(mm.group(1), s + mm.start()):
                    hits.append(s + mm.start())
        seen = set()
        for pos in sorted(hits):
            ln = df.line_of(pos)
            blk = None
            for t in df.tries:
                for c in t['clauses']:
                    if c['body_open'] < pos < c['body_close'] and (blk is None or c['body_open'] > blk):
                        blk = c['body_open']
            key = ('catch', blk) if blk is not None else ('line', ln)
            if key in seen or ('line', ln) in seen:
                continue
            stmt_s = max(df.masked.rfind(';', 0, pos), df.masked.rfind('{', 0, pos), df.masked.rfind('}', 0, pos)) + 1
            stmt = df.masked[stmt_s:pos]
            line = df.line_text(ln)
            if LOG_CALL.search(stmt) or LOG_ANY.search(stmt) or \
                    re.search(r'\b(?:throw|assert|Exception|Key|ValueKey|ObjectKey)\b\s*\(?', stmt[-60:]) or \
                    LOG_CALL.search(line) or LOG_ANY.search(line) or re.search(r'\bk(?:Debug|Profile)Mode\b', stmt + line):
                continue
            seen.add(key)
            seen.add(('line', ln))
            cls = self.class_of(df, pos)
            if cls is not None and WIDGET_HDR.search(cls['header']):
                ui = True                       # K3-E4: grade by the enclosing class, not the file role
            elif cls is not None and LOGIC_CONTENT.search(cls['header']):
                ui = False
            else:
                ui = df.role in ('view', 'widget')
            sink = UI_SINK.search(stmt) or UI_SINK.search(line)
            if ui:
                self.add(df, 'ERR-008', ln, line[:120])
            elif sink:                          # K3-E7: Get.snackbar/Get.dialog/*Toast* show text directly
                self.add(df, 'ERR-008', ln, line[:120],
                         note='logic shows the raw error directly (snackbar/dialog/toast); map it to user-safe text first')
            else:
                note = 'logic/state builds a message from the raw error; map typed failures to user-safe text'
                if self.profile == 'mvn':
                    note = ("the MVN spec's example does `XError(e.toString())`; fine only if every failure reaching the "
                            "notifier is already a user-safe domain failure")
                self.add(df, 'ERR-008', ln, line[:120], severity='low', note=note)

    LOADING_RE = re.compile(
        r'\bstate\s*=\s*(?:const\s+)?(?:\w+\.)?\w*(?:Loading|InProgress)\w*\s*(?:<[^>]*>)?\s*[(.]|'
        r'\bstate\s*=\s*(?:const\s+)?AsyncValue\s*(?:<[^>]*>)?\s*\.\s*loading\s*\(|'
        r'\bemit\s*\(\s*(?:const\s+)?(?:\w+\.)?\w*(?:Loading|InProgress)\w*\s*(?:<[^>]*>)?\s*[(.]|'
        r'\bemit\s*\(\s*(?:const\s+)?(?:state\s*\.\s*copyWith|[A-Z]\w*)\s*\([^;]*?\b(?:status|state)\s*:\s*(?:\(\s*\)\s*=>\s*)?\w+\s*\.\s*(?:loading|inProgress)\b|'
        r'\b(?P<flag>_?(?:is)?(?:[Ll]oading|[Bb]usy|[Rr]unning|[Ss]ubmitting))\s*(?:\.\s*value\s*)?=\s*true\b')
    HANDLER_SETS_STATE = re.compile(r'\bemit\s*\(|\bstate\s*=(?!=)|\bsetState\s*\(|\bnotifyListeners\s*\(|'
                                    r'\b[\w.]+\s*(?:\.\s*value\s*)?=(?![=>])|\w*(?:Failure|Failed|Error)\w*\s*\(|'
                                    r'\bGet\s*\.\s*(?:snackbar|dialog|defaultDialog)\b|\.\s*addError\s*\(|\bcompleteError\s*\(')

    def logic_kind(self, df, cls):
        """'logic', 'ui-state' (a State class doing the work itself) or None, decided per class (K3-E4, K1-FN)."""
        if cls is None:
            return 'logic' if df.role == 'logic' else None
        hdr = cls['header']
        if re.match(r'_?Command\w*$', cls['name'] or '') or re.search(r'\bextends\s+Command\w*\b', hdr):
            return None                         # K1-E1: the class that implements Command is the error path itself
        if STATE_HDR.search(hdr):
            return 'ui-state'
        if LOGIC_CONTENT.search(hdr):
            return 'logic'
        if WIDGET_HDR.search(hdr):
            return None
        return 'logic' if df.role == 'logic' else None

    def chain_error_handler(self, df, q, e):
        """K2-E2: an awaited `.then(...).catchError(handler)` / `.then(..., onError: handler)` chain.
        Returns None (no handler in the chain), 'handled' (the handler sets error state) or 'unhandled'."""
        m = df.masked
        skip = -1
        for hm in re.finditer(r'\.\s*catchError\s*\(|\.\s*then\s*(?:<[^>]*>)?\s*\(', m[q:e]):
            o = q + hm.end() - 1
            c = df.parens.get(o)
            if c is None or c > e or o < skip:
                continue                        # inside an earlier link's arguments, not the chain itself
            skip = c
            args = m[o + 1:c]
            if 'catchError' in hm.group(0):
                handler = args
            else:
                om = re.search(r'\bonError\s*:', args)
                if not om:
                    continue
                handler = args[om.end():]
            return 'handled' if self.HANDLER_SETS_STATE.search(handler) else 'unhandled'
        return None

    def in_reset_finally(self, df, p, flag):
        """K1-E1/K3-E5: p sits in a try whose finally clears the loading state."""
        for t in df.tries:
            if t['open'] < p < t['close'] and t['finally']:
                fb = df.masked[t['finally'][0]:t['finally'][1]]
                if flag and re.search(r'\b' + re.escape(flag) + r'\s*(?:\.\s*value\s*)?=\s*false\b', fb):
                    return True
                if not flag and re.search(r'\bemit\s*\(|\bstate\s*=(?!=)|\bnotifyListeners\s*\(|\bsetState\s*\(', fb):
                    return True
        return False

    def owned_by(self, df, f, pos):
        """pos belongs to f itself, or to a `setState(() ...)` closure directly inside f."""
        g = innermost_func(df, pos)
        if g is f:
            return True
        if g is not None and g['lambda'] and re.search(r'\bsetState\s*\(\s*$', df.masked[max(0, g['header_start'] - 40):g['header_start']]):
            return innermost_func(df, g['header_start'] - 1) is f
        return False

    def first_unhandled_await(self, df, f, start, flag):
        """(position, soft) of the first await after start that can leave the loading state stuck."""
        soft = None
        for am in re.finditer(r'\bawait\s+(?!Future\s*(?:<[^>]*>)?\s*\.\s*delayed\b)', df.masked[start:f['body_close']]):
            p = start + am.start()
            if innermost_func(df, p) is not f:
                continue
            if inside_guard(df, p) or inside_any_catch(df, p) or self.in_reset_finally(df, p, flag):
                continue
            q = start + am.end()
            e = _expr_end(df, q)
            expr = df.masked[q:e]
            if re.match(r'\s*emit\s*\.\s*(?:forEach|onEach)\b', expr) and re.search(r'\bonError\s*:', expr):
                continue                        # K2-E1: bloc's emit.forEach(onError:) is the error path
            ce = self.chain_error_handler(df, q, e)
            if ce == 'handled':
                continue
            if ce == 'unhandled':
                soft = soft or p
                continue
            if self.callee_kind(df, f, q) in ('result', 'infallible'):
                continue
            return p, False
        return (soft, True) if soft is not None else (None, False)

    def check_loading(self, df):
        for f in df.funcs:
            if not f['is_async'] or f['arrow']:
                continue
            kind = self.logic_kind(df, self.class_of(df, f['body_open']))
            if kind is None:
                continue
            body = df.masked[f['body_open']:f['body_close']]
            lm = None
            for cand in self.LOADING_RE.finditer(body):
                if self.owned_by(df, f, f['body_open'] + cand.start()):
                    lm = cand
                    break
            if not lm:
                continue
            if RESULT_AWARE.search(body) or any(re.search(r'(?<![\w.])' + re.escape(g) + r'\s*(?:<[^>]*>)?\s*\(', body)
                                                for g in self.guard_names):
                continue
            flag = lm.group('flag')
            bad, soft = self.first_unhandled_await(df, f, f['body_open'] + lm.end(), flag)
            if bad is None:
                continue
            # private helper called from a guarded site is fine
            if f['name'] and f['name'].startswith('_'):
                calls = [c.start() for c in re.finditer(r'(?<![\w.])' + re.escape(f['name']) + r'\b(?!\s*\()?', df.masked)
                         if not (f['header_start'] <= c.start() < f['body_open'])]
                if any(inside_guard(df, c) for c in calls) or re.search(r'Command\d?\s*(?:<[^>]*>)?\s*\(\s*' + re.escape(f['name']) + r'\b', df.masked):
                    continue
            ln = df.line_of(bad)
            self.loading_funcs.add((df.rel, f['body_open']))
            hint = FIX_BY_PROFILE['setstate'] if kind == 'ui-state' else self.fix_hint()
            if soft:
                self.add(df, 'ERR-010', ln, '%s: %s' % (f['name'] or '(handler)', df.line_text(ln)[:100]), severity='medium',
                         note='the catchError/onError handler does not set an error state, so loading never ends; ' + hint)
            else:
                self.add(df, 'ERR-010', ln, '%s: %s' % (f['name'] or '(handler)', df.line_text(ln)[:100]), note=hint)

    def check_ui_io(self, df):
        """ERR-014 (K1/K3 FN): a widget or State callback awaits a network call with no try/catch."""
        if not any(t in NETWORK_PACKAGES for t, _ in df.imports):
            return
        for f in df.funcs:
            if not f['is_async'] or (df.rel, f['body_open']) in self.loading_funcs:
                continue
            cls = self.class_of(df, f['body_open'])
            if cls is None or not WIDGET_HDR.search(cls['header']):
                continue
            body = df.masked[f['body_open']:f['body_close']]
            if RESULT_AWARE.search(body):
                continue
            for am in re.finditer(r'\bawait\b', body):
                p = f['body_open'] + am.start()
                if innermost_func(df, p) is not f or inside_guard(df, p) or inside_any_catch(df, p):
                    continue
                q = f['body_open'] + am.end()
                e = _expr_end(df, q)
                if not NET_CALL.match(df.masked[q:e]) or self.chain_error_handler(df, q, e) == 'handled':
                    continue
                ln = df.line_of(p)
                self.add(df, 'ERR-014', ln, '%s: %s' % (f['name'] or '(callback)', df.line_text(ln)[:100]),
                         note=FIX_BY_PROFILE.get(self.profile, FIX_BY_PROFILE['unknown']))
                break

    def check_zone(self, df):
        for zm in re.finditer(r'\brunZonedGuarded\s*(?:<[^>]*>)?\s*\(', df.masked):
            o = zm.end() - 1
            c = df.parens.get(o)
            if c is None:
                continue
            inner = df.masked[o:c]
            if not re.search(r'\brunApp\s*\(', inner):
                continue
            f = innermost_func(df, zm.start())
            lo = f['body_open'] if f else 0
            before = df.masked[lo:zm.start()]
            em = re.search(r'\bensureInitialized\s*\(', before)
            if em:
                ln = df.line_of(lo + em.start())
                self.add(df, 'ERR-013', ln, df.line_text(ln)[:120])

    def check_global(self):
        mains = [f for f in self.files if re.match(r'lib/main[\w]*\.dart$', f.rel) and re.search(r'\brunApp\s*\(', f.masked)]
        if not mains or not re.search(r'^\s*flutter\s*:\s*\n\s*sdk\s*:\s*flutter', self.pubspec, re.M):
            return
        allm = '\n'.join(f.masked for f in self.files)
        flutter_h = bool(re.search(r'FlutterError\s*\.\s*onError\s*=|SentryFlutter\s*\.\s*init\s*\(|\bBugsnag\w*\s*\.\s*start\s*\(', allm))
        async_h = bool(re.search(r'PlatformDispatcher\s*\.\s*instance\s*\.\s*onError\s*=|\brunZonedGuarded\s*[<(]|'
                                 r'SentryFlutter\s*\.\s*init\s*\(|\bBugsnag\w*\s*\.\s*start\s*\(', allm))
        if flutter_h and async_h:
            return
        missing = []
        if not flutter_h:
            missing.append('FlutterError.onError')
        if not async_h:
            missing.append('PlatformDispatcher.instance.onError (or runZonedGuarded)')
        deps = [r for r in REPORTERS if re.search(r'^\s+' + re.escape(r) + r'\s*:', self.pubspec, re.M)]
        main = sorted(mains, key=lambda f: (f.rel != 'lib/main.dart', f.rel))[0]
        ln = main.line_of(re.search(r'\brunApp\s*\(', main.masked).start())
        sev = 'medium' if deps else 'low'
        note = ('crash reporter dependency %s is present but not wired to both handlers' % ', '.join(deps)) if deps else \
            'no crash reporter dependency; at least log uncaught errors in release builds'
        self.add(main, 'ERR-012', ln, 'missing: ' + ', '.join(missing), severity=sev, note=note, key='global')


# --------------------------------------------------------------------------- project loading

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


def detect_profile_fallback(pubspec, files):
    deps = set(re.findall(r'^\s{2}(\w+)\s*:', pubspec, re.M))
    rels = [f.rel for f in files]
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
    sys.stderr.write('check_errors.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_errors.py <project-root> [--json] [--files <list>] '
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
    out_of_scope = 0
    for rel in rels:
        if arch_files and rel not in arch_files:
            out_of_scope += 1               # files[] is the source of truth for scope (generated files, l10n output ...)
            continue
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if re.search(r'GENERATED CODE - DO NOT MODIFY', df.raw[:400]):
            continue
        parse_file(df, package)
        a = arch_files.get(rel)
        if a:
            df.layer, df.role, df.feature = a.get('layer') or 'other', a.get('role') or 'other', a.get('feature')
        else:
            df.layer, df.role, df.feature = classify_fallback(rel, df)
        if df.layer in ('ui', 'view'):
            df.layer = 'presentation'
        refine_role(df)
        files.append(df)

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(pubspec, files), 'fallback detection from pubspec and folders'

    ck = Checker(root, files, package, pubspec, profile)
    if files:
        ck.run()
    findings = ck.findings
    suppressed = ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (SEV_ORDER.get(f['severity'], 9), f['id'], f['file'], f['line']))

    n_catch = sum(len(t['clauses']) for f in files for t in f.tries)
    n_throw = sum(len(re.findall(r'\bthrow\b', f.masked)) for f in files)
    n_result = sum(1 for f in files for fn in f.funcs if fn['member'] and ck.is_result(fn['ret']))
    allm = '\n'.join(f.masked for f in files)
    handlers = [h for h, rx in (('FlutterError.onError', r'FlutterError\s*\.\s*onError\s*='),
                                ('PlatformDispatcher.onError', r'PlatformDispatcher\s*\.\s*instance\s*\.\s*onError\s*='),
                                ('runZonedGuarded', r'\brunZonedGuarded\s*[<(]'),
                                ('ErrorWidget.builder', r'ErrorWidget\s*\.\s*builder\s*='),
                                ('SentryFlutter.init', r'SentryFlutter\s*\.\s*init\s*\('),
                                ('Crashlytics', r'FirebaseCrashlytics\s*\.\s*instance'),
                                ('BlocObserver', r'Bloc\s*\.\s*observer\s*='),
                                ('ProviderObserver', r'\bProviderObserver\b')) if re.search(rx, allm)]
    repo_sigs = [fn['ret'] for f in files if f.is_repo_any for fn in f.funcs
                 if fn['member'] and fn['name'] and not fn['name'].startswith('_') and not fn['lambda']
                 and (re.match(r'(?:Future|FutureOr|Result|Either|TaskEither)\b', fn['ret']) or ck.is_result(fn['ret']))
                 and not re.match(r'Future\s*<\s*void\s*>', fn['ret'])]
    n_res_repo = sum(1 for r in repo_sigs if ck.is_result(r))
    style = 'exceptions' if not (n_result or n_res_repo) else (
        'result' if n_res_repo == len(repo_sigs) else 'mixed')

    report = {
        'schema': SCHEMA, 'root': root, 'package': package,
        'profile': {'presentation': profile, 'source': psource,
                    'clean_architecture': bool(arch and arch.get('profile', {}).get('clean_architecture')),
                    'repository_pattern': bool(arch and arch.get('profile', {}).get('repository_pattern')) or
                    any(f.is_repo_any for f in files)},
        'classification': classification,
        'stats': {'files': len(files), 'catch_clauses': n_catch, 'throw_statements': n_throw,
                  'result_returning_methods': n_result, 'error_style': style, 'global_handlers': handlers,
                  'reported_scope': 'files list (%d)' % len(only) if only is not None else 'all',
                  'skipped_out_of_scope': out_of_scope,
                  'skipped_roles': sum(1 for f in files if f.role in SKIP_ROLES)},
        'findings': findings,
        'suppressed': suppressed,
    }
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2) + '\n')
        return 0
    out = ['== ERROR HANDLING',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  scanned: %d files, %d catch clauses, %d throw statements, %d Result-returning methods (style: %s)' %
           (len(files), n_catch, n_throw, n_result, style),
           '  global handlers: %s' % (', '.join(handlers) if handlers else 'none found')]
    groups = []
    index = {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    if not groups:
        out.append('  no error-handling findings')
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
