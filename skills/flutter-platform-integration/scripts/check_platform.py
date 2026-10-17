#!/usr/bin/env python3
"""check_platform.py: find unsafe or misplaced native-interop code in a Flutter project (read-only).

Usage:
  python3 -I check_platform.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (channel names are compared across files,
             callers of a platform call are found in every file); only findings in the
             listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  PLAT-001 channel-outside-data-layer       PLAT-007 library-loaded-from-writable-path
  PLAT-002 channel-name-duplicated          PLAT-008 call-handler-never-cleared
  PLAT-003 platform-call-unhandled          PLAT-009 platform-interface-not-enforced
  PLAT-004 platform-result-force-unwrapped  PLAT-010 isolate-channel-without-messenger
  PLAT-005 event-subscription-dropped       PLAT-011 permission-requested-at-startup
  PLAT-006 native-memory-not-freed          PLAT-012 permanent-denial-unhandled

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so. Generated Pigeon, ffigen and jnigen output is skipped (by banner
and by the output paths configured in pigeons/*.dart, ffigen.yaml and jnigen.yaml).

Suppression (in the analysed code):
  // plat-ignore: PLAT-001 <reason>        on the reported line or the line above
  // plat-ignore-file: PLAT-001 <reason>   anywhere in the file

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

SCHEMA = 'flutter-pro-skills/platform@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
TOOL = 'check_platform.py'

RULES = {
    'PLAT-001': ('channel-outside-data-layer', 'medium',
                 'A view, widget or logic class (notifier, view model, bloc, controller) talks to native code itself: '
                 'it builds a platform channel, calls invokeMethod, listens to an EventChannel, loads a native '
                 'library or allocates native memory. The screen or logic then cannot be tested without the engine, '
                 'PlatformException handling is repeated per caller, and the channel contract is spread over the UI. '
                 'Wrap the channel or binding in a data source behind a repository or service.'),
    'PLAT-002': ('channel-name-duplicated', 'low',
                 'The same channel name is written as a literal in several places. Both sides of a channel must agree '
                 'on the name, so a typo or a rename in one copy silently breaks that call site with a '
                 'MissingPluginException. Declare each channel once, as a constant in the class that wraps it.'),
    'PLAT-003': ('platform-call-unhandled', 'low',
                 'A platform call can fail with PlatformException (the native side reported an error) or '
                 'MissingPluginException (no handler on this platform, a test, or a background isolate), and nothing '
                 'on its path catches either: not the function, not its callers. The error reaches the zone as an '
                 'uncaught async error and the user sees nothing. Map it in the source or repository.'),
    'PLAT-004': ('platform-result-force-unwrapped', 'low',
                 'invokeMethod<T> returns Future<T?>: the native side may answer null, or a different type. Forcing '
                 'it with ! or a non-nullable "as" turns a protocol mismatch into a TypeError, which an '
                 '"on PlatformException" handler does not catch. Check for null and map it to a typed error.'),
    'PLAT-005': ('event-subscription-dropped', 'medium',
                 'receiveBroadcastStream().listen(...) is called without keeping the StreamSubscription, so it can '
                 'never be cancelled. The native side keeps streaming (sensor, location, battery) and the callback '
                 'keeps running after its owner is gone, and every rebuild or reopen adds another listener.'),
    'PLAT-006': ('native-memory-not-freed', 'high',
                 'Native memory is allocated with calloc/malloc or toNativeUtf8() and never freed in this function '
                 '(no free, no finally, no Arena, no NativeFinalizer, not returned or handed to an owner). The Dart '
                 'GC does not see native memory, so it leaks on every call. Use using((arena) {...}) or free it in a '
                 'finally block.'),
    'PLAT-007': ('library-loaded-from-writable-path', 'high',
                 'DynamicLibrary.open() loads a path built from a writable location (documents, temp, support or '
                 'downloads directory), an environment variable or user input. Anyone who can write that file gets '
                 'their code run inside the app with its permissions and data. Load only bundled libraries, by a '
                 'constant name.'),
    'PLAT-008': ('call-handler-never-cleared', 'low',
                 'A State or logic class registers a setMethodCallHandler/setMessageHandler and never clears it. '
                 'The channel keeps the handler (and through it the State or notifier) alive after dispose, and a '
                 'message after that calls setState or notifyListeners on a disposed object. Set the handler to null '
                 'in the owner\'s dispose hook.'),
    'PLAT-009': ('platform-interface-not-enforced', 'medium',
                 'A plugin platform interface loses its token check: an implementation uses "implements" instead of '
                 '"extends", or the instance setter does not call PlatformInterface.verify. Then new methods added '
                 'to the interface break every implementation at compile time instead of falling back to the '
                 'default, and any object can be installed as the platform instance.'),
    'PLAT-010': ('isolate-channel-without-messenger', 'high',
                 'Code run in a background isolate (Isolate.spawn, Isolate.run, compute) uses a platform channel or '
                 'a plugin that does, without calling BackgroundIsolateBinaryMessenger.ensureInitialized(token) '
                 'first. The call throws (the binding is not initialized in that isolate). Pass '
                 'RootIsolateToken.instance from the root isolate and initialize the messenger first.'),
    'PLAT-011': ('permission-requested-at-startup', 'low',
                 'A runtime permission is requested at app start (main/bootstrap). The user sees a system prompt '
                 'with no context, is more likely to deny it, and on iOS and Android 11+ a second denial is '
                 'permanent. Request it at the moment the feature needs it, after a short rationale.'),
    'PLAT-012': ('permanent-denial-unhandled', 'low',
                 'Permissions are requested but the app never handles a permanent denial (isPermanentlyDenied, '
                 'isRestricted, openAppSettings appear nowhere in lib/). Once the user denies twice, request() '
                 'returns permanentlyDenied without a prompt, so the feature silently stops working. Show a way to '
                 'the app settings.'),
}

PLACE = {
    'mvn': 'MVN: put the channel in data/sources/<x>_platform_source.dart behind the repository contract; the '
           'repository impl maps PlatformException to a Failure; use cases and notifiers never see the channel.',
    'mvvm': 'MVVM: wrap the channel in a service under data/services; the repository maps PlatformException to a '
            'Result error and view models call the repository.',
    'bloc': 'Bloc: wrap the channel in a data-provider class (or a plugin package) given to a repository through '
            'RepositoryProvider; blocs receive the repository.',
    'riverpod': 'Riverpod: expose a platform source through a provider and a repository provider that maps '
                'PlatformException; notifiers read the repository.',
    'provider': 'Provider: wrap the channel in a service created at the root (Provider(create:)); ChangeNotifiers '
                'call a repository built on it.',
    'getx': 'GetX: wrap the channel in a GetxService registered in the initial binding; controllers call a '
            'repository.',
    'mvc': 'MVC: keep the channel in the model/service layer behind a repository; controllers call the repository.',
    'setstate': 'Move the channel into a small wrapper class (one constant channel name, typed methods, errors '
                'mapped) that widgets call; it becomes the data source when the app grows.',
    'unknown': 'Wrap the channel in a data-layer class behind a repository or service, built once and injected.',
}
PLACE_CLEAN = 'Clean: data/datasources/<x>_platform_source.dart implements the source; the domain sees only the ' \
              'repository contract and its failures.'

MAP_NOTE = {
    'mvn': 'MVN: catch PlatformException/MissingPluginException in the repository impl and return the use case\'s '
           'Failure; the notifier turns it into an error state.',
    'mvvm': 'MVVM: catch it in the repository and return Result.error; the view model\'s Command exposes the error.',
    'bloc': 'Bloc: catch it in the repository and throw/return a domain failure; the bloc emits a failure state.',
    'riverpod': 'Riverpod: catch it in the repository provider, or let a FutureProvider/AsyncNotifier surface it '
                'as AsyncValue.error (AsyncValue.guard).',
    'provider': 'Provider: catch it in the repository/service and expose an error field the ChangeNotifier maps.',
    'getx': 'GetX: catch it in the repository/service; the controller sets an error Rx value.',
    'mvc': 'MVC: catch it in the model/service and give the controller a typed error.',
    'setstate': 'Catch it in the wrapper class (on PlatformException, on MissingPluginException) and return a '
                'typed result the widget can show.',
    'unknown': 'Catch it where the channel is wrapped and map it to a typed failure.',
}

LIFE_NOTE = {
    'state': 'State: call %s in dispose().',
    'riverpod': 'Riverpod: register ref.onDispose(() => %s) in build().',
    'mvn': 'MVN: register ref.onDispose(() => %s) in build() (better: move the channel into a data source).',
    'bloc': 'Bloc: call %s in close().',
    'mvvm': 'MVVM: call %s in the view model\'s dispose().',
    'provider': 'Provider: call %s in the ChangeNotifier\'s dispose().',
    'getx': 'GetX: call %s in onClose().',
    'unknown': 'Call %s when the owner is disposed.',
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.gen|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|'
                              r'AUTO[- ]?GENERATED FILE|Autogenerated from Pigeon|Autogenerated by jnigen|'
                              r'Generated by `?package:ffigen|Generated by: OpenAPI Generator', re.I)
SUPPRESS_RE = re.compile(r'plat-ignore(-file)?\s*:\s*((?:PLAT-\d{3})(?:\s*,\s*PLAT-\d{3})*)\s*(.*)')

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
LOGIC_ROLES = {'logic'}
STATE_CLASS = re.compile(r'\bextends\s+(?:State|ConsumerState|HookState)\s*<')
WIDGET_CLASS = re.compile(r'\bextends\s+(?:State|ConsumerState|HookState)\s*<|'
                          r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|'
                          r'HookWidget|HookConsumerWidget|StatefulHookWidget|StatefulHookConsumerWidget)\b')
LOGIC_CLASS = re.compile(r'\b(?:extends|with)\s+(?:Cubit|Bloc|ChangeNotifier|Notifier|AsyncNotifier|StreamNotifier|'
                         r'StateNotifier|GetxController|FullLifeCycleController|ValueNotifier|FamilyNotifier|'
                         r'FamilyAsyncNotifier|AutoDisposeNotifier|AutoDisposeAsyncNotifier|_\$\w+)\b|'
                         r'\bclass\s+\w*ViewModel\b')
CHANNEL_CTOR = re.compile(r'(?<![\w$.])(MethodChannel|OptionalMethodChannel|EventChannel|BasicMessageChannel)\s*'
                          r'(?:<[^()]*?>)?\s*\(')
CHANNEL_OP = re.compile(r'\.\s*(invokeMethod|invokeListMethod|invokeMapMethod|receiveBroadcastStream|'
                        r'setMethodCallHandler|setMessageHandler)\s*(?:<[^()]*?>)?\s*\(')
INVOKE_OP = re.compile(r'\.\s*(invokeMethod|invokeListMethod|invokeMapMethod)\s*(?:<([^()]*?)>)?\s*\(')
FFI_OP = re.compile(r'(?<![\w$.])DynamicLibrary\s*\.\s*(?:open|process|executable)\s*\(|'
                    r'\.\s*lookupFunction\s*<|(?<![\w$.])(?:calloc|malloc)\s*(?:<[^()]*?>)?\s*\(|'
                    r'(?<![\w$.])(?:calloc|malloc)\s*\.\s*allocate\s*(?:<[^()]*?>)?\s*\(|'
                    r'\.\s*toNative(?:Utf8|Utf16)\s*\(')
ALLOC = re.compile(r'(?<![\w$.])(calloc|malloc)\s*(?:<[^()]*?>)?\s*\(|'
                   r'(?<![\w$.])(calloc|malloc)\s*\.\s*allocate\s*(?:<[^()]*?>)?\s*\(|'
                   r'\.\s*(toNative(?:Utf8|Utf16))\s*\(')
HANDLES_ALL = re.compile(r'^(?:PlatformException|MissingPluginException|Exception|Object|dynamic|'
                         r'ServicesException)\??$')
CHAIN_HANDLER = re.compile(r'\s*(?:\.\s*(?:then\s*(?:<[^()]*?>)?\s*\([^;]*\bonError\s*:|catchError\s*\(|'
                           r'onError\s*(?:<[^()]*?>)?\s*\(|ignore\s*\(\s*\)))')
WRITABLE_SRC = re.compile(r'\b(?:getApplicationDocumentsDirectory|getTemporaryDirectory|'
                          r'getApplicationSupportDirectory|getApplicationCacheDirectory|getDownloadsDirectory|'
                          r'getExternalStorageDirectory|getExternalStorageDirectories|getExternalCacheDirectories|'
                          r'getLibraryDirectory)\s*\(|\bDirectory\s*\.\s*systemTemp\b|\bPlatform\s*\.\s*environment\b|'
                          r'\.\s*text\b|\bUri\s*\.\s*base\b|\bFilePicker\b|\bpickFiles?\s*\(|\bstdin\b')
PLATFORM_USE = re.compile(r'(?<![\w$.])(?:MethodChannel|OptionalMethodChannel|EventChannel|BasicMessageChannel)\s*'
                          r'(?:<[^()]*?>)?\s*\(|\.\s*(?:invokeMethod|invokeListMethod|invokeMapMethod|'
                          r'receiveBroadcastStream)\b|\bSharedPreferences\s*\.\s*getInstance\s*\(|'
                          r'\bSharedPreferencesAsync\s*\(|\b(?:getApplicationDocumentsDirectory|getTemporaryDirectory|'
                          r'getApplicationSupportDirectory|getApplicationCacheDirectory|getDownloadsDirectory)\s*\(')
PERM_HANDLED = re.compile(r'\bisPermanentlyDenied\b|\bpermanentlyDenied\b|\bopenAppSettings\s*\(|\bisRestricted\b|'
                          r'\bAppSettings\s*\.\s*open\w*\s*\(')
DECL_BEFORE = re.compile(r'(?:(?<![\w$])(?!(?:return|await|yield|throw|else|case|in|is|as|new|const|async|'
                         r'sync)\b)[A-Za-z_$][\w$]*[?]?|>[?]?|\]|\bget|\bset)\s+$')
COMMON_NAMES = {'dispose', 'init', 'initialize', 'start', 'stop', 'close', 'cancel', 'open', 'load', 'get', 'set',
                'update', 'call', 'run', 'play', 'pause', 'resume', 'reset', 'clear', 'remove', 'add', 'read',
                'write', 'create', 'delete', 'show', 'hide', 'send', 'fetch', 'refresh', 'save', 'connect',
                'disconnect', 'enable', 'disable', 'toggle', 'request', 'check', 'setup', 'register', 'listen',
                'execute', 'handle', 'process', 'select', 'seek', 'release', 'destroy', 'invoke'}
STARTUP_FN = {'main', 'bootstrap', '_bootstrap', 'mainCommon', '_mainCommon'}
EVENT_ARG = re.compile(r'\bon[A-Z]\w*\s*:\s*$|\baddListener\s*\(\s*$|\blisten\s*\(\s*$|\bonPressed\s*:\s*$')


def first_arg_literal(df, po):
    """The plain string literal that is the first argument of the call whose '(' is at po, or None."""
    pc = df.parens.get(po)
    if pc is None:
        return None
    s, e = strip_range(df.masked, po + 1, pc)
    end = expr_end(df.masked, s)
    rec = df.string_at(s)
    if rec is None or rec['s'] != s or rec['interps']:
        return None
    if df.masked[rec['e']:end].strip():
        return None           # 'a' + b, or a method call on the literal
    return df.code[rec['cs']:rec['ce']]


def owner_key(header, profile):
    """Which lifetime hook a logic class has, from its supertype (falls back to the profile)."""
    if re.search(r'\b(?:extends|with)\s+(?:Cubit|Bloc)\b', header):
        return 'bloc'
    if re.search(r'\b(?:extends|with)\s+(?:GetxController|FullLifeCycleController)\b', header):
        return 'getx'
    if re.search(r'\b(?:extends|with)\s+(?:ChangeNotifier|ValueNotifier)\b', header):
        return 'mvvm' if re.search(r'ViewModel\b', header) else 'provider'
    if re.search(r'\bextends\s+(?:_\$\w+|Notifier|AsyncNotifier|StreamNotifier|AutoDispose\w*Notifier|'
                 r'Family\w*Notifier)\b', header):
        return 'mvn' if profile == 'mvn' else 'riverpod'
    return profile


class Try(object):
    __slots__ = ('bo', 'bc', 'catches')

    def __init__(self, bo, bc, catches):
        self.bo, self.bc, self.catches = bo, bc, catches


def find_tries(df):
    m = df.masked
    out = []
    for mm in re.finditer(r'\btry\s*\{', m):
        bo = mm.end() - 1
        bc = df.braces.get(bo)
        if bc is None:
            continue
        catches = []
        i = bc + 1
        while True:
            cm = re.match(r'\s*(?:on\s+([\w$.<>?, ]+?)\s*(?=catch\b|\{)\s*)?(catch\s*\([^)]*\)\s*)?\{', m[i:i + 300])
            if not cm or (cm.group(1) is None and cm.group(2) is None):
                break
            catches.append(cm.group(1).strip() if cm.group(1) else None)
            o = i + cm.end() - 1
            c = df.braces.get(o)
            if c is None:
                break
            i = c + 1
        out.append(Try(bo, bc, catches))
    return out


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, root, files, profile, clean, layered, pigeon):
        self.root = root
        self.files = files
        self.profile = profile
        self.clean = clean
        self.layered = layered
        self.host_apis, self.flutter_apis = pigeon
        self.findings = []
        self.suppressed = []
        self.stats = {'method_channels': 0, 'event_channels': 0, 'message_channels': 0,
                      'pigeon_apis': len(self.host_apis) + len(self.flutter_apis), 'ffi_files': 0,
                      'native_allocations': 0, 'dynamic_libraries': 0, 'platform_interfaces': 0,
                      'isolate_entries': 0, 'permission_requests': 0}
        self.tries = {}
        self.refs = {}             # name -> [(df, pos, is_call)]
        self.memo = {}
        self.by_rel = dict((df.rel, df) for df in files)
        pig = []
        if self.host_apis:
            pig.append(r'(?<![\w$.])(?:%s)\s*\(' % '|'.join(re.escape(n) for n in sorted(self.host_apis)))
        if self.flutter_apis:
            pig.append(r'(?<![\w$.])(?:%s)\s*\.\s*set[Uu]p\s*\(' %
                       '|'.join(re.escape(n) for n in sorted(self.flutter_apis)))
        self.pigeon_rx = re.compile('|'.join(pig)) if pig else None

    # -- reporting
    def place(self):
        p = PLACE.get(self.profile, PLACE['unknown'])
        if self.clean and self.profile != 'mvn':
            p += ' ' + PLACE_CLEAN
        return p

    def add(self, df, rid, pos, evidence, note='', severity=None, place=False, line=None):
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
        if place:
            note = (note + ' ' if note else '') + self.place()
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    # -- helpers
    @staticmethod
    def stmt_prefix(m, pos):
        k = max(m.rfind(';', 0, pos), m.rfind('{', 0, pos), m.rfind('}', 0, pos))
        return m[k + 1:pos]

    @staticmethod
    def assigned_name(prefix):
        p = re.sub(r'\bawait\s*$', '', prefix.rstrip()).rstrip()
        mm = re.search(r'(?:\b(?:final|var|late|const)\s+(?:[\w$.<>?, ]+\s+)?|\b[A-Z][\w$.<>?, ]*\s+)'
                       r'([A-Za-z_$][\w$]*)\s*=\s*$', p)
        if mm:
            return mm.group(1), True
        mm = re.search(r'(?<![\w$.])(?:this\s*\.\s*)?([A-Za-z_$][\w$]*)\s*(?:\?\?)?=\s*$', p)
        if mm and not re.search(r'[=!<>]=\s*$', p):
            return mm.group(1), False
        return None, False

    def class_kind(self, df, pos):
        """'ui', 'logic', 'plain' or None (top level) for the class around pos."""
        cls = df.enclosing_class(pos)
        if cls is None:
            return None, None
        hdr = cls[3]
        if WIDGET_CLASS.search(hdr):
            return 'ui', cls
        if LOGIC_CLASS.search(hdr):
            return 'logic', cls
        return 'plain', cls

    def in_try(self, df, pos):
        for t in self.tries[df.rel]:
            if t.bo < pos < t.bc and any(c is None or HANDLES_ALL.match(c) for c in t.catches):
                return True
        return False

    def call_end(self, df, po):
        pc = df.parens.get(po)
        return pc + 1 if pc is not None else po + 1

    def expr_start(self, df, pos):
        """Start of the receiver chain ending at pos (walks back over identifiers, dots and (...))."""
        m = df.masked
        i = pos
        while i > 0:
            j = i - 1
            while j >= 0 and m[j] in ' \t\n':
                j -= 1
            if j < 0:
                break
            c = m[j]
            if c == ')' and df.parens.get(j) is not None:
                i = df.parens[j]
                continue
            if c == ']':
                if df.brackets is None:
                    df.brackets = match_pairs(m, '[', ']')
                if df.brackets.get(j) is not None and re.search(r'[\w$)\]]\s*$', m[max(0, df.brackets[j] - 3):
                                                                                    df.brackets[j]]):
                    i = df.brackets[j]
                    continue
            if c in '\'"':
                r = df.string_at(j)
                if r is not None:
                    i = r['s']
                    continue
            if c.isalnum() or c in '_$.?!':
                k = j
                while k >= 0 and (m[k].isalnum() or m[k] in '_$.?!'):
                    k -= 1
                word = m[k + 1:j + 1]
                if word in ('const', 'new'):
                    i = k + 1
                    break
                if word in KEYWORDS:
                    break
                i = k + 1
                continue
            if c == '>':
                k = m.rfind('<', 0, j)
                if k > 0 and re.search(r'[\w$]\s*$', m[max(0, k - 40):k]) and not re.search(r'[;{}()]', m[k:j]):
                    i = k
                    continue
            break
        return i

    def usage_kind(self, df, start):
        """How the value of the expression starting at start is used: awaited, returned, assigned, bare, other."""
        prefix = self.stmt_prefix(df.masked, start)
        p = prefix.rstrip()
        if re.search(r'\bawait\s*$', p):
            return 'awaited', prefix
        if re.search(r'(?:\breturn|=>)\s*$', p):
            return 'returned', prefix
        if re.search(r'(?<![=!<>])=\s*$', p):
            return 'assigned', prefix
        if not p.strip():
            return 'bare', prefix
        if re.search(r'\bunawaited\s*\(\s*$', p):
            return 'bare', prefix
        return 'other', prefix

    # -- reference index (for callers of functions that make platform calls)
    def index_refs(self):
        rx = re.compile(r'(?<![\w$])([A-Za-z_$][\w$]*)\b')
        for df in self.files:
            starts = set(f.start for f in df.callables if f.name)
            m = df.masked
            for mm in rx.finditer(m):
                name = mm.group(1)
                if name in KEYWORDS or mm.start() in starts:
                    continue
                after = m[mm.end():mm.end() + 60]
                is_call = bool(re.match(r'\s*(?:<[^()]*?>)?\s*\(', after))
                if is_call and DECL_BEFORE.search(m[max(0, mm.start() - 60):mm.start()]):
                    continue    # a declaration (abstract method, override in another class), not a call
                if mm.start() > 0 and m[mm.start() - 1] == '.' and m[max(0, mm.start() - 6):mm.start()] == 'super.':
                    continue
                self.refs.setdefault(name, []).append((df, mm.start(), is_call))

    def owner_verdict(self, df, pos, depth=0):
        """Is an error thrown by the expression at pos (awaited or returned) handled by someone?

        Returns ('handled'|'unhandled'|'unknown', site) where site is the (df, pos) left unhandled."""
        if self.in_try(df, pos):
            return 'handled', None
        fs = df.enclosing_callables(pos)
        if not fs:
            return 'unknown', None
        f = fs[0]
        if self.provider_context(df, f, pos):
            return 'handled', None      # AsyncValue captures the error (FutureProvider, AsyncNotifier, guard)
        if f.name is None:
            # a closure: framework callbacks (onPressed:, listen) leave the error unhandled
            if EVENT_ARG.search(df.masked[max(0, f.start - 80):f.start]):
                return 'unhandled', (df, pos)
            return 'unknown', None
        cls = df.enclosing_class(pos)
        if cls is not None and WIDGET_CLASS.search(cls[3]) and (
                f.name in ('build', 'initState', 'didChangeDependencies', 'didUpdateWidget', 'dispose') or
                re.match(r'^_?(?:on|handle)[A-Z]\w*$', f.name)):
            # lifecycle hooks and event handlers are called by the framework
            refs = [r for r in self.refs.get(f.name, []) if r[0] is not df or r[1] != f.start]
            if not refs:
                return 'unhandled', (df, pos)
        if re.search(r'@override\b[^;{}]*$', df.masked[max(0, f.start - 160):f.start]):
            return 'unknown', None      # called through an interface (a plugin implementation, a mixin)
        if depth >= 3:
            return 'unknown', None
        key = (df.rel, f.start)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = ('unknown', None)
        refs = [r for r in self.refs.get(f.name, []) if not (r[0] is df and f.start <= r[1] <= f.bc)]
        if f.name.lstrip('_') in COMMON_NAMES:
            refs = [r for r in refs if r[0] is df]      # too common to match across files by name
        if not refs:
            res = ('unknown', None)
        else:
            handled, unhandled = False, None
            for rdf, rpos, is_call in refs[:40]:
                if not is_call:
                    if EVENT_ARG.search(rdf.masked[max(0, rpos - 60):rpos]):
                        unhandled = unhandled or (rdf, rpos)
                    continue        # a tear-off passed somewhere we cannot follow: neutral
                v, site = self.site_verdict(rdf, rpos, depth + 1)
                if v == 'handled':
                    handled = True
                elif unhandled is None:
                    unhandled = site
            res = ('handled', None) if handled or unhandled is None else ('unhandled', unhandled)
        self.memo[key] = res
        return res

    def provider_context(self, df, f, pos):
        names = [n for n, _ in df.enclosing_calls(pos)[:6]]
        if any(n in ('guard', 'FutureProvider', 'StreamProvider', 'FutureBuilder', 'StreamBuilder', 'family',
                     'autoDispose') for n in names):
            return True
        for g in df.enclosing_callables(pos):
            if g.name is None:
                continue
            if re.search(r'@[Rr]iverpod\b[^;{}]*$', df.masked[max(0, g.start - 200):g.start]):
                return True
            if any(re.search(r'(?:^|\b)\w*Ref\b', pt or '') for _, pt, _ in g.params):
                return True
            if g.name == 'build':
                cls = df.enclosing_class(g.start)
                if cls and re.search(r'\bextends\s+(?:_\$\w+|AsyncNotifier|StreamNotifier|AutoDisposeAsyncNotifier|'
                                     r'FamilyAsyncNotifier)\b', cls[3]):
                    return True
            break
        return False

    def site_verdict(self, df, pos, depth):
        """Verdict for a call starting at pos (the name of the call or the start of its receiver chain)."""
        m = df.masked
        mm = re.match(r'[\w$.?!\s]*?(?:<[^()]*?>)?\s*\(', m[pos:pos + 200])
        po = pos + mm.end() - 1 if mm else pos
        ce = self.call_end(df, po)
        if CHAIN_HANDLER.match(m[ce:ce + 200]):
            return 'handled', None
        start = self.expr_start(df, pos)
        kind, prefix = self.usage_kind(df, start)
        if kind in ('awaited', 'returned'):
            return self.owner_verdict(df, start, depth)
        if kind == 'bare':
            if self.in_try(df, pos):
                return 'handled', None
            return 'unhandled', (df, pos)
        if kind == 'assigned':
            name, _ = self.assigned_name(prefix)
            if name and re.search(r'\b(?:future|stream)\s*:\s*(?:this\s*\.\s*|widget\s*\.\s*)?_?%s\b' %
                                  re.escape(name.lstrip('_')), m):
                return 'handled', None
            return 'unknown', None
        return 'unknown', None

    # -- rules
    def run(self):
        for df in self.files:
            self.tries[df.rel] = find_tries(df)
        self.index_refs()
        names = {}
        perm_sites = []
        perm_handled = False
        pis = set()
        for df in self.files:
            for mm in re.finditer(r'\bclass\s+(\w+)[^{;]*\bextends\s+PlatformInterface\b', df.masked):
                pis.add(mm.group(1))
        self.stats['platform_interfaces'] = len(pis)
        for df in self.files:
            if 'dart:ffi' in df.code and re.search(r'''^\s*import\s+['"]dart:ffi['"]''', df.code, re.M):
                self.stats['ffi_files'] += 1
            if PERM_HANDLED.search(df.masked):
                perm_handled = True
            self.placement(df)
            self.collect_names(df, names)
            self.unhandled_calls(df)
            self.force_unwrap(df)
            self.dropped_subscriptions(df)
            self.native_memory(df)
            self.dynamic_libraries(df)
            self.handlers(df)
            self.platform_interfaces(df, pis)
            self.isolates(df)
            perm_sites.extend(self.permissions(df))
        self.duplicate_names(names)
        if not perm_handled:
            for df, pos in perm_sites:
                self.add(df, 'PLAT-012', pos, df.line_text(pos)[:120],
                         'nothing in lib/ checks isPermanentlyDenied or offers openAppSettings(). Return a '
                         'permanentlyDenied/restricted value from the permission service and let the view offer '
                         'openAppSettings(). %s' % self.perm_note())

    def perm_note(self):
        return {'mvn': 'MVN: a PermissionSource in data/, a use case returning a domain PermissionStatus, the '
                       'notifier exposes it, the view asks at the moment of use.',
                'mvvm': 'MVVM: a PermissionService in data/services; the view model exposes the status; the view '
                        'triggers the request.',
                'bloc': 'Bloc: a PermissionRepository (or client package) given through RepositoryProvider; the '
                        'bloc emits granted/denied/permanentlyDenied states.',
                'riverpod': 'Riverpod: a permission service provider; a notifier exposes the status.',
                'provider': 'Provider: a PermissionService behind the ChangeNotifier.',
                'getx': 'GetX: a PermissionService (GetxService); the controller exposes the status.',
                }.get(self.profile, 'Wrap permission_handler in a service that returns granted, denied or '
                                    'permanentlyDenied; the view asks at the moment of use.')

    # PLAT-001
    def placement(self, df):
        role = df.role
        sites = []
        rxs = [CHANNEL_CTOR, CHANNEL_OP, FFI_OP]
        if self.pigeon_rx is not None:
            rxs.append(self.pigeon_rx)
        m = df.masked
        for rx in rxs:
            for mm in rx.finditer(m):
                pos = mm.start()
                if re.search(r'SystemChannels\s*\.\s*\w+\s*$', m[max(0, pos - 60):pos]):
                    continue
                kind, cls = self.class_kind(df, pos)
                if kind == 'plain':
                    continue        # a wrapper class: the channel already has its own home
                if kind is None:
                    if role not in UI_ROLES or df.layer == 'app':
                        continue    # top-level code of the composition root wires services up
                    kind = 'ui'
                if kind == 'logic' and (role in ('source', 'service', 'repository', 'repository-impl') or
                                        df.layer in ('core', 'data', 'domain')):
                    continue    # a notifier/ChangeNotifier in core/ or data/ is the app's data provider
                sites.append((pos, kind, cls))
        if not sites:
            return
        sites.sort()
        pos, kind, cls = sites[0]
        sev = 'medium' if self.layered else 'low'
        where = 'a %s' % ('widget/State class' if kind == 'ui' else 'logic class')
        more = ' (%d native-interop sites in this file)' % len(sites) if len(sites) > 1 else ''
        lead = '%s%s %s touches native code directly%s.' % (
            cls[0] if cls else 'This file', '' if cls else '', 'in ' + where if cls else '(top level of a view file)',
            more)
        if not self.layered:
            lead += ' The app has no data layer yet, so this is Low.'
        self.add(df, 'PLAT-001', pos, df.line_text(pos)[:120], lead, severity=sev, place=True)

    # PLAT-002
    def collect_names(self, df, names):
        for mm in CHANNEL_CTOR.finditer(df.masked):
            kind = mm.group(1)
            key = {'MethodChannel': 'method_channels', 'OptionalMethodChannel': 'method_channels',
                   'EventChannel': 'event_channels', 'BasicMessageChannel': 'message_channels'}[kind]
            self.stats[key] += 1
            name = first_arg_literal(df, mm.end() - 1)
            if name:
                names.setdefault(name, []).append((df, mm.start()))

    def duplicate_names(self, names):
        for name in sorted(names):
            sites = sorted(names[name], key=lambda s: (s[0].rel, s[1]))
            if len(sites) < 2:
                continue
            first = sites[0]
            for df, pos in sites[1:]:
                others = ['%s:%d' % (o.rel, o.line_of(p)) for o, p in sites if (o, p) != (df, pos)]
                self.add(df, 'PLAT-002', pos, df.line_text(pos)[:120],
                         "'%s' is also written at %s. Declare it once (static const on the wrapper class, or one "
                         "channel instance injected) and use that everywhere, tests included." % (
                             name, ', '.join(others[:4]) + (' (+%d more)' % (len(others) - 4) if len(others) > 4
                                                            else '')))

    # PLAT-003
    def unhandled_calls(self, df):
        m = df.masked
        for mm in INVOKE_OP.finditer(m):
            pos = mm.start()
            if re.search(r'SystemChannels\s*\.\s*\w+\s*$', m[max(0, pos - 60):pos]):
                continue
            v, site = self.site_verdict(df, pos, 0)
            if v != 'unhandled':
                continue
            sdf, spos = site
            if sdf is df and df.line_of(spos) == df.line_of(pos):
                where = 'nothing catches PlatformException or MissingPluginException here'
            else:
                where = 'it reaches %s:%d without a try/catch' % (sdf.rel, sdf.line_of(spos))
            self.add(df, 'PLAT-003', pos, df.line_text(pos)[:120],
                     '%s() can throw and %s. %s' % (mm.group(1), where,
                                                    MAP_NOTE.get(self.profile, MAP_NOTE['unknown'])))

    # PLAT-004
    def force_unwrap(self, df):
        m = df.masked
        for mm in INVOKE_OP.finditer(m):
            pos = mm.start()
            ce = self.call_end(df, mm.end() - 1)
            after = m[ce:ce + 80]
            start = self.expr_start(df, pos)
            before = m[max(0, start - 30):start]
            if re.match(r'\s*\)\s*!(?!=)', after) and re.search(r'\(\s*await\s*$', before):
                self.add(df, 'PLAT-004', pos, df.line_text(pos)[:120],
                         'the awaited %s() result is forced with !. Check for null and throw or return a typed '
                         'error instead.' % mm.group(1))
                continue
            am = re.match(r'\s*as\s+([\w$.]+(?:\s*<[^;()]*?>)?)(\??)', after)
            if am and not am.group(2) and am.group(1) not in ('dynamic', 'Object') and \
                    not re.match(r'^[A-Z]\d?$', am.group(1)):      # a type parameter may itself be nullable
                self.add(df, 'PLAT-004', pos, df.line_text(pos)[:120],
                         'the %s() result is cast with "as %s"; null or a different type from native throws a '
                         'TypeError. Use invokeMethod<%s>() and check for null, or "as %s?".' % (
                             mm.group(1), am.group(1), am.group(1), am.group(1)))
                continue
            kind, prefix = self.usage_kind(df, start)
            name = None
            if kind == 'awaited':
                pre = re.sub(r'\bawait\s*$', '', prefix.rstrip())
                name, local = self.assigned_name(pre)
                if not local:
                    name = None
            if not name:
                continue
            fs = df.enclosing_callables(pos)
            if not fs:
                continue
            body = m[ce:fs[0].bc]
            n = re.escape(name)
            if re.search(r'\b%s\s*(?:==|!=)\s*null|\bnull\s*(?:==|!=)\s*%s\b|\b%s\s*\?\?|\b%s\s*\?\.|'
                         r'\b%s\s+is\b|\bcase\b[^;]*\b%s\b|switch\s*\(\s*%s\s*\)' % (n, n, n, n, n, n, n), body):
                continue
            bm = re.search(r'\b%s\s*!(?!=)' % n, body)
            if bm:
                bpos = ce + bm.start()
                self.add(df, 'PLAT-004', bpos, df.line_text(bpos)[:120],
                         '`%s` comes from %s() at line %d and is forced with ! without a null check.' % (
                             name, mm.group(1), df.line_of(pos)))

    # PLAT-005
    def dropped_subscriptions(self, df):
        m = df.masked
        for mm in re.finditer(r'\.\s*receiveBroadcastStream\s*\(', m):
            pos = mm.start()
            i = self.call_end(df, mm.end() - 1)
            listen = None
            while True:
                cm = re.match(r'\s*(?:\?)?\.\s*([A-Za-z_$][\w$]*)\s*(?:<[^()]*?>)?\s*\(', m[i:i + 200])
                if not cm:
                    break
                if cm.group(1) == 'listen':
                    listen = i + cm.start(1)
                    i = self.call_end(df, i + cm.end() - 1)
                    break
                i = self.call_end(df, i + cm.end() - 1)
            if listen is None:
                continue
            if re.match(r'\s*(?:\.\.|\.|\?\.)', m[i:i + 5]):
                continue        # .listen(...).onDone / cascade: kept or handled elsewhere
            start = self.expr_start(df, pos)
            kind, prefix = self.usage_kind(df, start)
            if kind != 'bare' or re.search(r'\bunawaited\s*\(\s*$', prefix):
                continue
            ck, cls = self.class_kind(df, pos)
            sev = 'medium' if ck in ('ui', 'logic') or df.role in UI_ROLES | LOGIC_ROLES else 'low'
            owner = 'state' if ck == 'ui' else (owner_key(cls[3], self.profile) if cls else self.profile)
            note = LIFE_NOTE.get(owner, LIFE_NOTE['unknown']) % '_subscription?.cancel()'
            self.add(df, 'PLAT-005', listen, df.line_text(listen)[:120],
                     'the StreamSubscription from receiveBroadcastStream().listen() is discarded. Keep it in a '
                     'field. %s' % note, severity=sev)

    # PLAT-006
    def native_memory(self, df):
        m = df.masked
        for mm in ALLOC.finditer(m):
            pos = mm.start()
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            what = mm.group(1) or mm.group(2) or mm.group(3)
            if what.startswith('toNative'):
                args = m[po + 1:pc]
                am = re.search(r'\ballocator\s*:\s*([\w$.]+)', args)
                if am and am.group(1) not in ('calloc', 'malloc'):
                    continue    # an Arena or zone allocator frees it
                fname = am.group(1) if am else 'malloc'
            else:
                fname = what
            self.stats['native_allocations'] += 1
            fs = df.enclosing_callables(pos)
            if not fs:
                continue        # a top-level final: allocated once for the app's lifetime
            f = fs[0]
            body = m[fs[-1].bo:fs[-1].bc + 1]      # the outermost function: closures share its locals
            start = self.expr_start(df, pos)
            ce = pc + 1
            # follow .cast<...>() and similar
            while True:
                cm = re.match(r'\s*\.\s*(?:cast|elementAt)\s*(?:<[^()]*?>)?\s*\(', m[ce:ce + 80])
                if not cm:
                    break
                ce = self.call_end(df, ce + cm.end() - 1)
            kind, prefix = self.usage_kind(df, start)
            if kind == 'returned':
                continue
            if f.expr_body and not m[f.bo + 2:start].strip():
                continue
            if kind == 'assigned':
                if re.search(r'(?:\]|\.\s*[A-Za-z_$][\w$]*)\s*=\s*$', prefix.rstrip() + ' ') and \
                        not re.search(r'\bthis\s*\.\s*[A-Za-z_$][\w$]*\s*=\s*$', prefix):
                    continue    # stored into a native array or struct field: its owner frees it
                name, local = self.assigned_name(prefix)
                if not name:
                    continue
                if not local and re.search(r'\b(?:var|final|late|[A-Z][\w$<>?, ]*|int|double|bool)\s+%s\b' %
                                           re.escape(name), body):
                    local = True
                n = re.escape(name)
                scope = body
                if not local:
                    cls = df.enclosing_class(pos)
                    scope = m[cls[1]:cls[2]] if cls else m
                if re.search(r'\b(?:calloc|malloc|arena|allocator|\w*[Aa]llocator)\s*\.\s*free\s*\(\s*%s\b|'
                             r'(?<![\w$.])free\s*\(\s*%s\b|\b%s\s*\.\s*free\s*\(|\battach\s*\([^;]*\b%s\b|'
                             r'\breturn\s+%s\b|=>\s*%s\b' % (n, n, n, n, n, n), scope):
                    continue
                if re.search(r'(?<![=!<>])=\s*%s\s*[;.]|\b[A-Z]\w*(?:\.\w+)?\s*\([^;]*\b%s\b[^;]*\)|'
                                       r'\.\s*add\s*\(\s*%s\b|:\s*%s\s*[,)]|[Ff]inaliz\w*\s*\([^;]*\b%s\b' %
                                       (n, n, n, n, n), body):
                    continue    # stored in a field, wrapped in an owning object, or kept in a list
                self.add(df, 'PLAT-006', pos, df.line_text(pos)[:120],
                         '`%s` (%s) is never freed%s. Wrap the call in using((arena) {...}) and allocate with '
                         'arena, or free it in a finally block: %s.free(%s).' % (
                             name, what, ' in %s()' % f.name if f.name else '', fname, name))
                continue
            if kind == 'bare':
                continue        # value discarded: nothing to free (and nothing used)
            # inline: passed straight to a call, so no reference is left to free
            self.add(df, 'PLAT-006', pos, df.line_text(pos)[:120],
                     'the %s() result is passed inline, so nothing can free it%s. Allocate inside '
                     'using((arena) {...}) with allocator: arena, or keep it in a local and free it in finally.' % (
                         what, ' in %s()' % f.name if f.name else ''))

    # PLAT-007
    def dynamic_libraries(self, df):
        m = df.masked
        for mm in re.finditer(r'(?<![\w$.])DynamicLibrary\s*\.\s*(open|process|executable)\s*\(', m):
            self.stats['dynamic_libraries'] += 1
            if mm.group(1) != 'open':
                continue
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            if first_arg_literal(df, po) is not None:
                continue
            arg = df.iview[po + 1:pc]
            texts = [arg]
            fs = df.enclosing_callables(mm.start())
            scope = m[fs[-1].bo:fs[-1].bc] if fs else ''
            iscope = df.iview[fs[-1].bo:fs[-1].bc] if fs else ''
            seen = set()
            todo = re.findall(r'(?<![\w$.])([a-z_$][\w$]*)\b', arg)
            while todo:
                n = todo.pop()
                if n in seen or n in KEYWORDS or len(seen) > 20:
                    continue
                seen.add(n)
                for am in re.finditer(r'(?<![\w$.])%s\s*(?:\?\?)?=(?!=)\s*([^;]*);' % re.escape(n), iscope):
                    texts.append(am.group(1))
                    todo.extend(re.findall(r'(?<![\w$.])([a-z_$][\w$]*)\b', am.group(1)))
            hit = None
            for t in texts:
                wm = WRITABLE_SRC.search(t)
                if wm:
                    hit = wm.group(0).strip(' (')
                    break
            if not hit:
                continue
            self.add(df, 'PLAT-007', mm.start(), df.line_text(mm.start())[:120],
                     'the path comes from %s. Bundle the library with the app (native assets / build hooks, '
                     'jniLibs, an embedded framework) and open it by a constant name, e.g. '
                     "DynamicLibrary.open('libfoo.so') or DynamicLibrary.process()." % hit)

    # PLAT-008
    def handlers(self, df):
        m = df.masked
        for mm in re.finditer(r'\.\s*(setMethodCallHandler|setMessageHandler)\s*\(', m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None or re.match(r'\s*null\s*\)', m[po + 1:pc + 1]):
                continue
            kind, cls = self.class_kind(df, mm.start())
            if kind not in ('ui', 'logic') or cls is None:
                continue
            if kind == 'ui' and not STATE_CLASS.search(cls[3]):
                continue
            body = m[cls[1]:cls[2]]
            if re.search(r'\.\s*%s\s*\(\s*null\s*\)' % mm.group(1), body):
                continue
            owner = 'state' if kind == 'ui' else owner_key(cls[3], self.profile)
            note = LIFE_NOTE.get(owner, LIFE_NOTE['unknown']) % ('channel.%s(null)' % mm.group(1))
            fs = df.enclosing_callables(mm.start())
            if fs and fs[-1].name in ('didChangeDependencies', 'build', 'didUpdateWidget'):
                note = 'It is also registered again on every %s() call. ' % fs[-1].name + note
            self.add(df, 'PLAT-008', mm.start(), df.line_text(mm.start())[:120],
                     '%s registers a %s handler and never clears it. %s' % (cls[0], mm.group(1), note))

    # PLAT-009
    def platform_interfaces(self, df, pis):
        m = df.masked
        if pis:
            for c in df.classes:
                hdr = c[3]
                im = re.search(r'\bimplements\b([^{]*)', hdr)
                if not im:
                    continue
                hit = [p for p in pis if re.search(r'\b%s\b' % re.escape(p), im.group(1))]
                if not hit or 'MockPlatformInterfaceMixin' in hdr:
                    continue
                self.add(df, 'PLAT-009', c[4], df.line_text(c[4])[:120],
                         '%s implements %s; extend it instead (class %s extends %s), so methods added to the '
                         'interface later fall back to its default and the token check passes. Test fakes may '
                         'implement it only with MockPlatformInterfaceMixin.' % (c[0], hit[0], c[0], hit[0]))
        for c in df.classes:
            if not re.search(r'\bextends\s+PlatformInterface\b', c[3]):
                continue
            body = m[c[1]:c[2]]
            sm = re.search(r'\bstatic\s+set\s+instance\s*\(', body)
            if sm:
                so = c[1] + sm.end() - 1
                spc = df.parens.get(so)
                tail = m[spc + 1:spc + 400] if spc else ''
                bm = re.match(r'\s*(\{|=>)', tail)
                sb = ''
                if bm and bm.group(1) == '{':
                    o = spc + 1 + bm.start(1)
                    sb = m[o:(df.braces.get(o) or o) + 1]
                elif bm:
                    sb = m[spc + 1:spc + 1 + expr_end(m, spc + 1 + bm.end()) - spc]
                if not re.search(r'\bverify(?:Token)?\s*\(', sb):
                    pos = c[1] + sm.start()
                    self.add(df, 'PLAT-009', pos, df.line_text(pos)[:120],
                             'the %s.instance setter installs any object without PlatformInterface.verify(instance, '
                             '_token), so an "implements" fake or a stale implementation is accepted silently.' %
                             c[0], severity='low')

    # PLAT-010
    def isolates(self, df):
        m = df.masked
        rx = re.compile(r'(?<![\w$])(?:Isolate\s*\.\s*(spawn|run)|(compute))\s*(?:<[^()]*?>)?\s*\(')
        for mm in rx.finditer(m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            self.stats['isolate_entries'] += 1
            arg_s, _ = strip_range(m, po + 1, pc)
            arg_e = expr_end(m, arg_s)
            arg = m[arg_s:arg_e].strip()
            bodies = []
            if re.match(r'^[A-Za-z_$][\w$.]*$', arg):
                name = arg.split('.')[-1]
                for f in self.callables_named(df, name):
                    bodies.append((f[0], f[1]))
            else:
                for f in df.callables:
                    if arg_s <= f.ps and f.bc <= arg_e + 1:
                        bodies.append((df, f))
                        break
            if not bodies:
                continue
            texts = []
            for bdf, f in bodies:
                texts.append(bdf.masked[f.bo:f.bc + 1])
                # one hop into same-file helpers called from the entry point
                for cm in re.finditer(r'(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(', bdf.masked[f.bo:f.bc + 1]):
                    if cm.group(1) in KEYWORDS:
                        continue
                    for g in bdf.callables:
                        if g.name == cm.group(1) and g is not f:
                            texts.append(bdf.masked[g.bo:g.bc + 1])
            text = '\n'.join(texts)
            if re.search(r'BackgroundIsolateBinaryMessenger\s*\.\s*ensureInitialized', text):
                continue
            um = PLATFORM_USE.search(text)
            pm = self.pigeon_rx.search(text) if self.pigeon_rx is not None else None
            if not um and not pm:
                continue
            use = (um or pm).group(0).strip(' (.')
            self.add(df, 'PLAT-010', mm.start(), df.line_text(mm.start())[:120],
                     'the isolate entry point uses %s without BackgroundIsolateBinaryMessenger.ensureInitialized. '
                     'Pass RootIsolateToken.instance! as an argument and call '
                     'BackgroundIsolateBinaryMessenger.ensureInitialized(token) first in the isolate '
                     '(RootIsolateToken.instance is null inside it).' % use)

    def callables_named(self, df, name):
        own = [(df, f) for f in df.callables if f.name == name]
        if own:
            return own
        out = []
        for o in self.files:
            out.extend((o, f) for f in o.callables if f.name == name)
        return out if len(out) == 1 else []

    # PLAT-011 (returns PLAT-012 candidates)
    def permissions(self, df):
        m = df.masked
        out = []
        brackets = None
        for mm in re.finditer(r'\.\s*request\s*\(\s*\)', m):
            pos = mm.start()
            before = m[max(0, pos - 80):pos]
            if re.search(r'(?<![\w$])Permission\s*\.\s*\w+\s*$', before):
                pass
            elif before.rstrip().endswith(']'):
                if brackets is None:
                    brackets = match_pairs(m, '[', ']')
                cb = pos - (len(before) - len(before.rstrip()))  - 1
                ob = brackets.get(cb)
                if ob is None or not re.search(r'(?<![\w$])Permission\s*\.\s*\w+', m[ob:cb]):
                    continue
            else:
                continue
            self.stats['permission_requests'] += 1
            out.append((df, pos))
            fs = [f for f in df.enclosing_callables(pos) if f.name]
            fn = fs[-1].name if fs else None
            in_root = bool(re.search(r'(^|/)lib/main[^/]*\.dart$', df.rel)) and \
                self.class_kind(df, pos)[0] is None
            if fn in STARTUP_FN or (in_root and fn in (None, 'main')):
                self.add(df, 'PLAT-011', pos, df.line_text(pos)[:120],
                         'requested in %s(). Ask from the screen that needs it, when the user starts the feature '
                         '(show the rationale first if shouldShowRequestRationale is true). %s' % (
                             fn or 'app start', self.perm_note()))
        return out


# ---------------------------------------------------------------------------------------- classification

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
    sys.stderr.write('check_platform.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_platform.py <project-root> [--json] [--files <list>] '
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




def _norm_rel(root, p, base=None):
    p = p.strip().strip('\'"')
    if not p:
        return None
    if not os.path.isabs(p):
        p = os.path.join(base or root, p)
    p = os.path.relpath(os.path.normpath(p), root).replace(os.sep, '/')
    return None if p.startswith('..') else p


def configured_outputs(root):
    """Generated-output paths configured for Pigeon, ffigen and jnigen (files or folders, project-relative)."""
    outs = set()
    host, flutter = set(), set()
    for d in ('pigeons', 'pigeon'):
        for p in sorted(glob.glob(os.path.join(root, d, '*.dart'))):
            try:
                with open(p, encoding='utf-8', errors='replace') as fh:
                    t = fh.read()
            except OSError:
                continue
            for mm in re.finditer(r'''\bdartOut\s*:\s*['"]([^'"]+)['"]''', t):
                r = _norm_rel(root, mm.group(1))
                if r:
                    outs.add(r)
            t2 = re.sub(r'//[^\n]*', '', t)
            for mm in re.finditer(r'@(HostApi|FlutterApi)\s*\([^)]*\)\s*(?:@\w+(?:\([^)]*\))?\s*)*'
                                  r'(?:abstract\s+)?(?:interface\s+)?class\s+(\w+)', t2):
                (host if mm.group(1) == 'HostApi' else flutter).add(mm.group(2))
    for p in sorted(glob.glob(os.path.join(root, '*.sh'))) + sorted(glob.glob(os.path.join(root, 'tool', '*.sh'))):
        try:
            with open(p, encoding='utf-8', errors='replace') as fh:
                t = fh.read()
        except OSError:
            continue
        for mm in re.finditer(r'--dart_out[=\s]+(\S+)', t):
            r = _norm_rel(root, mm.group(1))
            if r:
                outs.add(r)
    for name in ('ffigen.yaml', 'jnigen.yaml', 'pubspec.yaml'):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        with open(p, encoding='utf-8', errors='replace') as fh:
            t = fh.read()
        if name == 'pubspec.yaml':
            fm = re.search(r'^ffigen:\s*\n((?:[ \t]+.*\n?)*)', t, re.M)
            if not fm:
                continue
            t = fm.group(1)
        for mm in re.finditer(r'''^\s*output\s*:\s*['"]?([^'"\s#]+\.dart)['"]?''', t, re.M):
            r = _norm_rel(root, mm.group(1))
            if r:
                outs.add(r)
        for mm in re.finditer(r'''^\s*(?:bindings|path)\s*:\s*['"]?([^'"\s#]+)['"]?''', t, re.M):
            v = mm.group(1)
            if v.endswith('.dart') or (name == 'jnigen.yaml' and v.startswith('lib')):
                r = _norm_rel(root, v)
                if r:
                    outs.add(r)
    return outs, host, flutter


def is_configured_output(rel, outs):
    for o in outs:
        if rel == o or (not o.endswith('.dart') and rel.startswith(o.rstrip('/') + '/')):
            return True
    return False


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
    outs, host_apis, flutter_apis = configured_outputs(root)

    rels = []
    lib = os.path.join(root, 'lib')
    if os.path.isdir(lib):
        for dp, dns, fns in os.walk(lib):
            dns[:] = sorted(d for d in dns if not d.startswith('.') and d != 'generated')
            for fn in sorted(fns):
                if fn.endswith('.dart'):
                    rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, '/')
                    rels.append(rel)

    skipped = {'generated': 0, 'barrel': 0}
    kept = []
    for rel in rels:
        if GENERATED_RE.search(rel) or is_configured_output(rel, outs):
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
    layered = clean or bool(aprof.get('repository_pattern')) or any(
        df.layer == 'data' or df.role in ('source', 'service', 'repository', 'repository-impl',
                                         'repository-contract') for df in files)

    ck = Checker(root, files, profile, clean, layered, (host_apis, flutter_apis))
    if files:
        ck.run()
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))

    stats = dict(ck.stats)
    stats['files'] = len(files)
    stats['skipped_generated'] = skipped['generated']
    stats['skipped_barrels'] = skipped['barrel']
    stats['layered'] = layered
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

    def plural(n, word):
        return '%d %s%s' % (n, word, '' if n == 1 else 's')

    out = ['== PLATFORM',
           '  profile: %s%s (%s)' % (profile, ' + clean' if clean else '', psource),
           '  classification: %s' % classification,
           '  scanned: %d files (%d generated skipped); channels: %d method, %d event, %d message; %s; %s, %s; '
           '%s; %s; %s' % (
               len(files), skipped['generated'], stats['method_channels'], stats['event_channels'],
               stats['message_channels'], plural(stats['pigeon_apis'], 'Pigeon API'),
               plural(stats['ffi_files'], 'FFI file'), plural(stats['native_allocations'], 'native allocation'),
               plural(stats['platform_interfaces'], 'platform interface'),
               '%d isolate entr%s' % (stats['isolate_entries'], 'y' if stats['isolate_entries'] == 1 else 'ies'),
               plural(stats['permission_requests'], 'permission request'))]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no platform findings')
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
