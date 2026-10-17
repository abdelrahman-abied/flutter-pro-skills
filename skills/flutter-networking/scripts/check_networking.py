#!/usr/bin/env python3
"""check_networking.py: find fragile or unsafe API-layer code in a Flutter project (read-only).

Usage:
  python3 -I check_networking.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (base URLs are compared across files,
             a global Bloc transformer counts everywhere); only findings in the listed
             files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  NET-001 client-without-timeouts          NET-006 cancel-token-never-cancelled
  NET-002 client-created-per-call          NET-007 websocket-never-closed
  NET-003 http-client-never-closed         NET-008 base-url-duplicated
  NET-004 retry-resends-any-method         NET-009 top-level-http-call
  NET-005 page-fetch-without-guard         NET-010 query-value-not-encoded

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so.

Suppression (in the analysed code):
  // net-ignore: NET-001 <reason>        on the reported line or the line above
  // net-ignore-file: NET-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/networking@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
TOOL = 'check_networking.py'

RULES = {
    'NET-001': ('client-without-timeouts', 'medium',
                'A Dio client is built without connectTimeout and receiveTimeout (Dio waits forever by default), or a '
                'dart:io HttpClient without connectionTimeout. On a dead network the request never fails, so the '
                'spinner never stops and the error path never runs. Set both timeouts on the one shared client.'),
    'NET-002': ('client-created-per-call', 'medium',
                'A Dio client is constructed inside a method of a data-layer class. Each call gets a client without '
                'the shared interceptors (auth, retry, logging), timeouts and base URL, opens its own connection pool, '
                'and cannot be replaced in tests. Inject the one configured client instead.'),
    'NET-003': ('http-client-never-closed', 'low',
                'An http.Client / HttpClient / IOClient is created in a function and never closed, returned or handed '
                'to an owner. Its sockets stay open until they time out. Close it in a finally block, or better, '
                'inject one long-lived client and close it when its owner is disposed.'),
    'NET-004': ('retry-resends-any-method', 'medium',
                'An interceptor re-sends the failed request without checking its method. A POST or PATCH that timed '
                'out may already have been applied by the server, so the retry creates a second order, message or '
                'payment. Retry only idempotent methods (GET, HEAD, PUT, DELETE, OPTIONS), or send an idempotency key.'),
    'NET-005': ('page-fetch-without-guard', 'medium',
                'A "load the next page" handler awaits the network with no in-flight guard. Scroll listeners fire many '
                'times per second near the end of a list, so the same page is requested several times and appended '
                'twice (duplicates, skipped pages, wasted quota). Drop calls while one is running.'),
    'NET-006': ('cancel-token-never-cancelled', 'low',
                'A Dio CancelToken is created but nothing ever calls cancel() on it, so it cancels nothing. Tie it to '
                'the lifetime of whoever started the request (ref.onDispose, Bloc close(), dispose()) or remove it.'),
    'NET-007': ('websocket-never-closed', 'medium',
                'A WebSocket is opened and never closed in this file. The socket, its server session and its stream '
                'outlive the screen or provider that opened it, and every reopen adds another connection. Close the '
                'sink when the owner is disposed.'),
    'NET-008': ('base-url-duplicated', 'low',
                'The same API host is written as a literal in several source files. Switching environments '
                '(dev/staging/prod) or flavors then needs edits in many places, and one is always missed. Keep the '
                'base URL in one configuration value given to the one client.'),
    'NET-009': ('top-level-http-call', 'low',
                'A data-layer class calls the package:http top-level functions (http.get, http.post, ...). Each call '
                'creates and closes a throwaway client (no connection reuse, no shared headers or timeouts), and tests '
                'cannot swap in MockClient. Inject an http.Client and call it.'),
    'NET-010': ('query-value-not-encoded', 'low',
                'A text value is interpolated into a URL query string without encoding. A "&", "#", "+" or space in '
                'it changes or truncates the query, and a crafted value can add parameters. Build the URI with '
                'queryParameters (Uri.https / Uri.replace / Dio queryParameters), which encodes each value.'),
}

# where the client goes, per architecture (appended to notes)
PLACE = {
    'mvn': 'MVN: one client provider in core/network (@Riverpod(keepAlive: true)) injected into '
           'data/sources/<x>_remote_source.dart; the repository impl maps DTOs and errors; use cases and notifiers '
           'never see the client.',
    'mvvm': 'MVVM: one client built in the composition root and passed to the API service under data/services; the '
            'repository maps API models to domain models; view models only call repositories.',
    'bloc': 'Bloc: the API client is its own data-provider class or package, built once in main/bootstrap and given '
            'to the repository through RepositoryProvider; blocs receive the repository.',
    'riverpod': 'Riverpod: expose the client through one keepAlive provider and read it from source/repository '
                'providers; per-request state (CancelToken) belongs to the autoDispose provider that issues it.',
    'provider': 'Provider: build the client once at the root (Provider(create:, dispose:)) and pass it to the API '
                'service; ChangeNotifiers call the repository.',
    'getx': 'GetX: register one client (Dio or GetConnect) as a permanent service in the initial binding; '
            'controllers call repositories.',
    'mvc': 'MVC: keep the client in the model/service layer behind a repository; controllers call the repository.',
    'setstate': 'Build one client at startup in a data-layer API class; widgets call a repository, never the client.',
    'unknown': 'Keep one configured client in a data-layer API class behind a repository, built once and injected.',
}
PLACE_CLEAN = 'Clean: the remote source sits in data/datasources/remote with DTOs in data/models; the repository ' \
              'impl maps them to domain entities.'

PAGE_NOTE = {
    'bloc': 'Bloc: register the handler with transformer: droppable() (bloc_concurrency), or throttleDroppable as in '
            'bloclibrary\'s infinite list, and keep the hasReachedMax check.',
    'mvn': 'MVN: return early when state.isLoading or the last page was reached, and set loading before the await '
           '(or model each page as a provider family).',
    'riverpod': 'Riverpod: return early when state.isLoading (or an _inFlight flag) is set, or model each page as a '
                'family provider so Riverpod de-duplicates the request.',
    'mvvm': 'MVVM: expose it as a Command (Command0/Command1); execute() ignores calls while running.',
    'provider': 'Provider: keep a private _isLoading flag, return early while it is set, and reset it in finally.',
    'getx': 'GetX: return early while isLoading.value is true, and reset it in finally.',
    'cubit': 'Cubit: return early when state.status is loading or hasReachedMax, emit loading before the await.',
}
LIFE_NOTE = {
    'riverpod': 'Riverpod: create it in the provider that starts the request and register ref.onDispose(%s).',
    'mvn': 'MVN: create it in the notifier/source call chain and register ref.onDispose(%s) in build().',
    'bloc': 'Bloc: keep it in the bloc or the data provider and call %s from close().',
    'mvvm': 'MVVM: keep it in the view model or service and call %s from dispose().',
    'provider': 'Provider: keep it in the ChangeNotifier and call %s from dispose().',
    'getx': 'GetX: keep it in the controller and call %s from onClose().',
    'setstate': 'Keep it in the State and call %s from dispose().',
}

DATA_OWNER = {
    'mvn': 'MVN: the source\'s keepAlive provider registers ref.onDispose(source.close).',
    'riverpod': 'Riverpod: the provider that creates the source registers ref.onDispose(source.close).',
    'bloc': 'Bloc: the repository exposes dispose(), called where it was created (main/bootstrap); a bloc cancels '
            'its own subscriptions in close().',
    'mvvm': 'MVVM: the service is created in the root Provider(create:, dispose:), which calls close().',
    'provider': 'Provider: create the source in Provider(create:, dispose:) and close it there.',
    'getx': 'GetX: close it in the service\'s onClose().',
    'unknown': 'Close it when the object that owns it is disposed.',
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.gen|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|'
                              r'AUTO-GENERATED FILE, DO NOT MODIFY|Generated by: OpenAPI Generator|'
                              r'openapi-generator', re.I)
SUPPRESS_RE = re.compile(r'net-ignore(-file)?\s*:\s*((?:NET-\d{3})(?:\s*,\s*NET-\d{3})*)\s*(.*)')
NET_PKGS = ('dio', 'http', 'retrofit', 'chopper', 'graphql', 'graphql_flutter', 'ferry', 'web_socket_channel',
            'web_socket', 'socket_io_client', 'grpc', 'dio_smart_retry', 'http_mock_adapter', 'cupertino_http',
            'cronet_http', 'ok_http', 'openapi_generator_annotations', 'json_serializable', 'freezed')


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


def toks_of(text):
    out = []
    for w in re.findall(r'[A-Za-z0-9]+', text):
        out += [p.lower() for p in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+', w)]
    return out



# ---------------------------------------------------------------------------------------- vocab

UI_ROLES = {'view', 'widget'}
LOGIC_ROLES = {'logic', 'state', 'event'}
SKIP_ROLES = {'barrel'}
ROOT_ROLES = {'di'}
FACTORY_NAME = re.compile(r'^_?(?:build|create|make|provide|new|init|setup|setUp|configure|register|bootstrap|main|'
                          r'open|connect|instance)\w*$|(?:client|dio|http|api)(?:factory)?$', re.I)
STATE_CLASS = re.compile(r'\bextends\s+(?:State|ConsumerState|HookState)\s*<|'
                         r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|'
                         r'HookWidget|HookConsumerWidget)\b')
LOGIC_CLASS = re.compile(r'\b(?:extends|with)\s+(?:Cubit|Bloc|ChangeNotifier|Notifier|AsyncNotifier|StreamNotifier|'
                         r'StateNotifier|GetxController|ValueNotifier|FamilyNotifier|FamilyAsyncNotifier|'
                         r'AutoDisposeNotifier|AutoDisposeAsyncNotifier|_\$\w+)\b|\bclass\s+\w*ViewModel\b')
PAGE_EVENT = re.compile(r'(?:More|Next(?:Page)?|Page(?:Requested|Fetched|Loaded)|Scroll(?:ed)?|EndReached|Paginat)')
PAGE_BODY = re.compile(r'\bhasReachedMax\b|\bhasReachedEnd\b|\bnextPage\b|\bnextCursor\b|\bpage\s*\+\s*1\b|'
                       r'\bstartIndex\s*:|\boffset\s*:\s*state\.')
PAGE_METHOD = re.compile(r'^_?(?:(?:load|fetch|get|request)(?:More\w*|Next(?:Page\w*|Items|Results|Batch)?)|'
                         r'\w*NextPage\w*|paginate|onEndReached|onLoadMore|onScrollEnd\w*)$')
SCROLL_BODY = re.compile(r'maxScrollExtent|ScrollNotification|ScrollEndNotification|extentAfter|_?isBottom\b|'
                         r'\batEdge\b|index\s*>=?\s*[\w.]+\.length')
SCROLL_NAME = re.compile(r'^_?(?:on|handle)?Scroll\w*$|^_?\w*[Ss]croll(?:ed|ing)?(?:Listener|Changed)?$')
SCROLL_ARG = re.compile(r'(?:itemBuilder|onNotification|onEndReached|onLoadMore|builder)\s*:\s*$|addListener\s*\(\s*$')
BUTTON_ARG = re.compile(r'\bon(?:Pressed|Tap|LongPress|DoubleTap|Changed|Submitted|Selected|Refresh)\s*:\s*$')
SETS_FLAG = re.compile(r'(?i)(?:loading|fetching|busy|inflight|running|pending)\w*\s*(?::|=(?!=))\s*true\b|'
                       r'status\s*:\s*\w+\.(?:loading|inProgress|fetching|loadingMore)\b|'
                       r'\bemit\s*\(\s*(?:const\s+)?\w*Loading\w*\s*\(')
INFLIGHT = re.compile(r'(?i)loading|fetching|busy|inflight|in_flight|running|pending|refreshing|isrequesting')
GUARD_IF = re.compile(r'\bif\s*\(')
TEXT_NAMES = re.compile(r'(?i)^(?:_?(?:q|query|term|search\w*|keyword\w*|text|name|filter\w*|email|title|city|'
                        r'address|location|phrase|input|username|tag\w*|label|comment|message|body)|\w*(?:Query|Term|'
                        r'Text|Name|Search|Keyword|Filter))$')
NUMERIC_TYPE = re.compile(r'^(?:int|double|num|bool|DateTime|Duration|BigInt)\??$')
LOCAL_HOST = re.compile(r'^(?:localhost|127\.|0\.0\.0\.0|10\.0\.[23]\.2|\[::1\]|(?:[\w-]+\.)*example\.(?:com|org|net)|'
                        r'[^.]+$|.*\.(?:test|local|internal|localhost|invalid)$)', re.I)
CONTENT_HOST = re.compile(r'^(?:(?:[\w-]+\.)*github(?:usercontent)?\.com|gist\.github\.com|gitlab\.com|'
                          r'bitbucket\.org|cdn\.jsdelivr\.net|unpkg\.com|fonts\.(?:googleapis|gstatic)\.com|'
                          r'play\.google\.com|apps\.apple\.com|itunes\.apple\.com|(?:www\.)?youtube\.com|youtu\.be|'
                          r'(?:[\w-]+\.)?wikipedia\.org|pub\.dev|t\.me)$', re.I)
CONFIG_PATH = re.compile(r'(?i)(config|env|constant|endpoint|flavou?r|api_url|urls?\.dart|settings)')
URL_CONTEXT_CALL = re.compile(r'(?:BaseOptions|Dio|\.\s*(?:get|post|put|patch|delete|head|request|fetch|getUri|'
                              r'postUri|putUri|deleteUri|send|download|read|readBytes)|'
                              r'WebSocketChannel\s*\.\s*connect)\s*(?:<[^()]*?>)?\s*\(\s*$')
URL_IN_CLIENT_CALL = re.compile(r'(?:\.\s*(?:get|post|put|patch|delete|head|request|fetch|getUri|postUri|send|'
                                r'download|read|readBytes)|WebSocketChannel\s*\.\s*connect)\s*(?:<[^()]*?>)?\s*\(\s*'
                                r'Uri\s*\.\s*(?:parse|tryParse|https?)\s*\(\s*$')
URL_CONTEXT_NAME = re.compile(r'(?i)(?:(?<![A-Za-z0-9])_?base\w*|\w*(?:api|host|endpoint|server|backend)\w*)'
                              r'\s*(?::|=|\?\?=)\s*$')
URL_CONTEXT_NAMED_ARG = re.compile(r'\bbaseUrl\s*:\s*$')
NOT_API_CALL = re.compile(r'(?:launchUrl|launchUrlString|launch|canLaunchUrl|canLaunch|Image\s*\.\s*network|'
                          r'NetworkImage|CachedNetworkImage\w*|Share\w*|openUrl|Link)\s*\(')
HOST_ONLY = re.compile(r'^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?::\d+)?$')


def first_await(text):
    mm = re.search(r'\bawait\b|\.then\s*\(', text)
    return mm.start() if mm else -1


def has_inflight_guard(body):
    """An `if (... loading ...) return` (or `{ return`) before the first await of the body."""
    fa = first_await(body)
    pre = body if fa < 0 else body[:fa]
    for mm in GUARD_IF.finditer(pre):
        depth, i = 0, mm.end() - 1
        while i < len(pre):
            if pre[i] == '(':
                depth += 1
            elif pre[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        cond = pre[mm.end():i]
        after = pre[i + 1:i + 40]
        if INFLIGHT.search(cond) and re.match(r'\s*(?:\{\s*)?return\b', after):
            return True
    return False


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, root, files, profile, clean, pubspec_deps):
        self.root = root
        self.files = files
        self.profile = profile
        self.clean = clean
        self.deps = pubspec_deps
        self.findings = []
        self.suppressed = []
        self.stats = {'packages': sorted(d for d in pubspec_deps if d in NET_PKGS), 'dio_clients': 0,
                      'http_clients': 0, 'interceptors': 0, 'websockets': 0, 'cancel_tokens': 0,
                      'page_handlers': 0}
        self.global_bloc_transformer = False
        self.page_candidates = []
        self.constants = set()      # top-level and static const/final names, project-wide

    # -- reporting
    def place(self):
        p = PLACE.get(self.profile, PLACE['unknown'])
        if self.clean and self.profile != 'mvn':
            p += ' ' + PLACE_CLEAN
        return p

    def add(self, df, rid, pos, evidence, note='', severity=None, place=True, line=None):
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
        """Masked text of the current statement before pos (back to the last ; { or })."""
        k = max(m.rfind(';', 0, pos), m.rfind('{', 0, pos), m.rfind('}', 0, pos))
        return m[k + 1:pos]

    @staticmethod
    def assigned_name(prefix):
        """(name, is_local_declaration) when the statement assigns the expression to a name."""
        p = re.sub(r'\bawait\s*$', '', prefix.rstrip()).rstrip()
        mm = re.search(r'(?:\b(?:final|var|late|const)\s+(?:[\w$.<>?, ]+\s+)?|\b[A-Z][\w$.<>?, ]*\s+)'
                       r'([A-Za-z_$][\w$]*)\s*=\s*$', p)
        if mm:
            return mm.group(1), True
        mm = re.search(r'(?<![\w$.])(?:this\s*\.\s*)?([A-Za-z_$][\w$]*)\s*(?:\?\?)?=\s*$', p)
        if mm and not re.search(r'[=!<>]=\s*$', p):
            return mm.group(1), False
        return None, False

    @staticmethod
    def returned(prefix):
        return bool(re.search(r'(?:\breturn|=>)\s*(?:await\s+)?$', prefix))

    def named_owner(self, df, pos):
        """(innermost named callable, crossed_a_closure)."""
        crossed = False
        for f in df.enclosing_callables(pos):
            if f.name is None:
                crossed = True
                continue
            return f, crossed
        return None, crossed

    def is_provider_fn(self, df, f):
        if any(re.search(r'(?:^|\b)\w*Ref\b', pt or '') for _, pt, _ in f.params):
            return True
        return bool(re.search(r'@[Rr]iverpod\b[^;{}]*$', df.masked[max(0, f.start - 200):f.start]))

    def name_escapes(self, body, name):
        """The local `name` is closed, returned, passed on or stored somewhere in body."""
        n = re.escape(name)
        pats = (r'\b%s\s*[?!]?\s*\.\s*close\b' % n, r'\b%s\s*\.\.\s*close\b' % n,
                r'\breturn\s+%s\b' % n, r'=>\s*%s\b' % n, r'[(,]\s*%s\s*[,)]' % n, r':\s*%s\s*[,)]' % n,
                r'(?<![=!<>])=\s*%s\s*;' % n, r'onDispose\s*\([^;]*\b%s\b' % n, r'\.\s*add\s*\(\s*%s\b' % n)
        return any(re.search(p, body) for p in pats)

    # -- rules
    def run(self):
        decl = re.compile(r'(?<![\w$.])(static\s+)?(?:const|final)\s+(?:[A-Za-z_$][\w$<>?,\s]*?\s+)?'
                          r'([A-Za-z_$][\w$]*)\s*=')
        for df in self.files:
            if re.search(r'\bBloc\s*\.\s*transformer\s*=', df.masked):
                self.global_bloc_transformer = True
            for mm in decl.finditer(df.masked):
                if df.enclosing_callables(mm.start()):
                    continue
                if df.enclosing_class(mm.start()) and not mm.group(1):
                    continue
                self.constants.add(mm.group(2))
        hosts = {}
        for df in self.files:
            if df.role in SKIP_ROLES:
                continue
            self.net_dio(df)
            self.net_http_clients(df)
            self.net_retry(df)
            self.net_paging(df)
            self.net_cancel_tokens(df)
            self.net_websockets(df)
            self.net_top_level_http(df)
            self.net_query(df)
            self.collect_hosts(df, hosts)
        self.net_hosts(hosts)
        self.resolve_paging()

    # NET-001 / NET-002
    def net_dio(self, df):
        m = df.masked
        if df.layer == 'domain':
            return      # ARCH-003 owns transport in the domain
        for mm in re.finditer(r'(?<![\w$.])Dio\s*\(', m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            self.stats['dio_clients'] += 1
            pos = mm.start()
            if self.dio_per_call(df, pos, po, pc):
                continue
            self.dio_timeouts(df, pos, po, pc)

    def dio_per_call(self, df, pos, po, pc):
        if df.role in UI_ROLES or df.role in LOGIC_ROLES or df.role in ROOT_ROLES or df.layer == 'app':
            return False    # ARCH-101 / ARCH-007 / ARCH-012 own clients in UI and logic; the root may build it
        cls = df.enclosing_class(pos)
        if cls and STATE_CLASS.search(cls[3]):
            return False
        f, crossed = self.named_owner(df, pos)
        if f is None or crossed:
            return False    # field initializer, top level, or a DI / factory closure
        if f.name == (cls[0] if cls else None) or FACTORY_NAME.search(f.name) or self.is_provider_fn(df, f):
            return False
        prefix = self.stmt_prefix(df.masked, pos)
        if self.returned(prefix):
            return False
        if f.expr_body and not df.masked[f.bo + 2:pos].strip():
            return False    # `Dio make() => Dio(...)` is a factory
        name, local = self.assigned_name(prefix)
        body = df.masked[f.bo:f.bc]
        if name and not local:
            return False    # stored in a field: a lazily built single client
        if name and local and re.search(r'\breturn\s+%s\b|=\s*%s\s*;' % (re.escape(name), re.escape(name)), body):
            return False    # built, configured and returned or stored
        interceptor = bool(cls and re.search(r'\b(?:extends|implements)\s+(?:Queued)?Interceptor\b', cls[3]))
        sev = 'low' if interceptor else None
        note = '%s() builds its own client on every call%s.' % (
            f.name, '; a fresh client per refresh also skips timeouts: build the refresh client once' if interceptor
            else '')
        self.add(df, 'NET-002', pos, df.line_text(pos)[:120], note, severity=sev)
        return True

    def dio_timeouts(self, df, pos, po, pc):
        m, code = df.masked, df.code
        args = m[po + 1:pc]
        opts = None
        if not args.strip():
            opts = ''
        else:
            bo = re.search(r'(?<![\w$.])BaseOptions\s*\(', args)
            if bo:
                bpo = po + 1 + bo.end() - 1
                bpc = df.parens.get(bpo)
                opts = m[bpo + 1:bpc] if bpc else None
            else:
                im = re.match(r'^\s*([A-Za-z_$][\w$]*)\s*,?\s*$', args)
                if im:
                    dm = re.search(r'\b%s\s*=\s*(?:const\s+)?BaseOptions\s*\(' % re.escape(im.group(1)), m)
                    if dm:
                        bpo = dm.end() - 1
                        bpc = df.parens.get(bpo)
                        opts = m[bpo + 1:bpc] if bpc else None
        if opts is None:
            return      # options built elsewhere: can't tell
        has_c = 'connectTimeout' in opts or re.search(r'\.\s*options\s*\.\s*connectTimeout\s*=', m)
        has_r = 'receiveTimeout' in opts or re.search(r'\.\s*options\s*\.\s*receiveTimeout\s*=', m)
        if re.search(r'\.\s*options\s*=(?!=)', m):
            return      # options replaced later in the file
        if has_c and has_r:
            return
        missing = [n for n, ok in (('connectTimeout', has_c), ('receiveTimeout', has_r)) if not ok]
        sev = 'medium' if len(missing) == 2 else 'low'
        note = 'missing %s.' % ' and '.join(missing)
        self.add(df, 'NET-001', pos, df.line_text(pos)[:120], note, severity=sev)

    # NET-001 (HttpClient) / NET-003
    def net_http_clients(self, df):
        m = df.masked
        http_alias = set(re.findall(r'''import\s+['"]package:http/http\.dart['"]\s+as\s+(\w+)''', df.code))
        http_plain = bool(re.search(r'''import\s+['"]package:http/http\.dart['"]\s*(?:show[^;]*\bClient\b[^;]*)?;''',
                                    df.code))
        for mm in re.finditer(r'(?<![\w$.])(?:(\w+)\s*\.\s*)?(Client|HttpClient|IOClient|RetryClient)\s*\(', m):
            prefix_alias, kind = mm.group(1), mm.group(2)
            if kind == 'Client':
                if not ((prefix_alias and prefix_alias in http_alias) or (not prefix_alias and http_plain)):
                    continue
            elif prefix_alias and kind == 'HttpClient' and prefix_alias not in ('io',):
                continue
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            pos = mm.start()
            self.stats['http_clients'] += 1
            in_adapter = any(n in ('createHttpClient', 'onHttpClientCreate') for n, _ in df.enclosing_calls(pos)) or \
                re.search(r'\b(?:createHttpClient|onHttpClientCreate)\s*:\s*\([^()]*\)\s*(?:=>|\{)[^;]*$',
                          m[max(0, pos - 300):pos])
            if kind == 'HttpClient' and not prefix_alias and df.layer != 'domain' and not in_adapter:
                if 'connectionTimeout' not in m and not re.search(r'\.\s*timeout\s*\(', m) and \
                        re.search(r'''import\s+['"]dart:io['"]''', df.code):
                    self.add(df, 'NET-001', pos, df.line_text(pos)[:120],
                             'dart:io HttpClient without connectionTimeout, and no .timeout() in this file.',
                             severity='low')
            fs = df.enclosing_callables(pos)
            if not fs:
                continue
            f = fs[0]
            prefix = self.stmt_prefix(m, pos)
            if self.returned(prefix):
                continue
            if f.expr_body and not m[f.bo + 2:pos].strip():
                continue
            name, local = self.assigned_name(prefix)
            body = m[f.bo:f.bc + 1]
            if name:
                if not local or self.name_escapes(body, name):
                    continue
                self.add(df, 'NET-003', pos, df.line_text(pos)[:120],
                         '`%s` is never closed in %s.' % (name, (f.name or 'this closure') + ('()' if f.name else '')))
                continue
            tail = m[pc + 1:pc + 40]
            if re.match(r'\s*\.\s*(?:get|post|put|patch|delete|head|read|readBytes|send)\b', tail):
                self.add(df, 'NET-003', pos, df.line_text(pos)[:120],
                         'a client is created inline for one call and never closed.')

    # NET-004
    def net_retry(self, df):
        m = df.masked
        regions = []
        for c in df.classes:
            if re.search(r'\b(?:extends|implements|with)\s+(?:Queued)?Interceptor\b', c[3]):
                self.stats['interceptors'] += 1
                eo = [f for f in df.callables if f.name == 'onError' and c[1] < f.bo < c[2]]
                if eo:
                    regions.append((c[1], c[2], eo[0].bo, eo[0].bc))
        for mm in re.finditer(r'(?<![\w$.])InterceptorsWrapper\s*\(', m):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            self.stats['interceptors'] += 1
            om = re.search(r'\bonError\s*:', m[po:pc])
            if not om:
                continue
            fs = [f for f in df.callables if f.name is None and po + om.end() <= f.ps < po + om.end() + 20]
            if fs:
                regions.append((po, pc, fs[0].bo, fs[0].bc))
        resend_rx = re.compile(r'\.\s*(?:fetch|request|requestUri)\s*(?:<[^()]*?>)?\s*\(')
        for cs, ce, eb, ee in regions:
            scope = m[cs:ce]
            onerr = m[eb:ee]
            rpos = None
            r1 = resend_rx.search(onerr)
            if r1:
                rpos = eb + r1.start()
            else:
                # onError may delegate to a helper of the same class that re-sends
                calls = set(re.findall(r'(?<![\w$.])(_?\w+)\s*\(', onerr))
                for f in df.callables:
                    if f.name in calls and cs < f.bo < ce and f.bo != eb:
                        r2 = resend_rx.search(m[f.bo:f.bc])
                        if r2 and re.search(r'requestOptions|options', m[f.bo:f.bc]):
                            rpos = f.bo + r2.start()
                            break
            if rpos is None:
                continue
            if re.search(r'\.\s*method\b|idempot|retryableMethods|isIdempotent', scope, re.I):
                continue
            if re.search(r'\b401\b|unauthori[sz]ed|\b403\b', onerr, re.I):
                continue    # token refresh replays a rejected request (flutter-secure-defaults)
            self.add(df, 'NET-004', rpos, df.line_text(rpos)[:120],
                     'onError re-sends err.requestOptions for every method; check requestOptions.method (or an '
                     'Idempotency-Key header) first. Offline replay of queued writes belongs to the repository '
                     '(flutter-persistence, PERSIST-non-idempotent-retry).')

    # NET-005
    def page_note(self, cubit=False):
        if cubit:
            return PAGE_NOTE['cubit']
        return PAGE_NOTE.get(self.profile, PAGE_NOTE['riverpod'] if self.profile == 'mvn' else
                             'Return early while a fetch is in flight, and reset the flag in finally.')

    def net_paging(self, df):
        m = df.masked
        for c in df.classes:
            header = c[3]
            if re.search(r'\bextends\s+Bloc\s*<', header):
                if self.global_bloc_transformer:
                    continue
                body_s, body_e = c[1], c[2]
                for om in re.finditer(r'(?<![\w$.])on\s*<\s*(\w+)\s*>\s*\(', m[body_s:body_e]):
                    po = body_s + om.end() - 1
                    pc = df.parens.get(po)
                    if pc is None:
                        continue
                    args = m[po + 1:pc]
                    if re.search(r'\btransformer\s*:', args):
                        continue
                    ev = om.group(1)
                    hm = re.match(r'\s*([A-Za-z_$][\w$]*)\s*[,)]?', args)
                    hbody = None
                    if hm and not re.match(r'\s*\(', args):
                        for f in df.callables:
                            if f.name == hm.group(1) and body_s < f.bo < body_e:
                                hbody = m[f.bo:f.bc]
                                break
                    else:
                        fs = [f for f in df.callables if f.name is None and po < f.ps < pc]
                        if fs:
                            hbody = m[fs[0].bo:fs[0].bc]
                    if hbody is None or first_await(hbody) < 0:
                        continue
                    if not (PAGE_EVENT.search(ev) or PAGE_BODY.search(hbody)):
                        continue
                    self.stats['page_handlers'] += 1
                    if has_inflight_guard(hbody):
                        continue
                    self.page_candidates.append(('bloc', df, body_s + om.start(), ev, hbody, False, c[0]))
                continue
            if not (LOGIC_CLASS.search(header) or df.role == 'logic'):
                continue
            cubit = bool(re.search(r'\bextends\s+Cubit\s*<', header))
            for f in df.callables:
                if not (f.name and c[1] < f.bo < c[2] and PAGE_METHOD.match(f.name)):
                    continue
                if df.enclosing_class(f.bo) is not c:
                    continue
                body = m[f.bo:f.bc]
                fa = first_await(body)
                if fa < 0:
                    continue
                self.stats['page_handlers'] += 1
                if has_inflight_guard(body):
                    continue
                if re.search(r'\bCommand\d?\s*(?:<[^()]*?>)?\s*\(\s*(?:this\s*\.\s*)?%s\b' % re.escape(f.name), m):
                    continue    # MVVM Command: execute() ignores calls while running
                flag = bool(SETS_FLAG.search(body[:fa]))
                self.page_candidates.append(('cubit' if cubit else 'logic', df, f.start, f.name, body, flag, c[0]))

    @staticmethod
    def guarded_call(df, f, pos):
        """The call at pos sits inside an `if (<in-flight check>)` block or statement, or after an early return."""
        m = df.masked
        for mm in GUARD_IF.finditer(m, f.bo, pos):
            po = mm.end() - 1
            pc = df.parens.get(po)
            if pc is None or pc > pos:
                continue
            cond = m[po + 1:pc]
            if not INFLIGHT.search(cond):
                continue
            k = pc + 1
            while k < len(m) and m[k].isspace():
                k += 1
            if k < len(m) and m[k] == '{':
                bc = df.braces.get(k)
                if bc is not None and k < pos < bc:
                    return True
                if bc is not None and re.match(r'\s*return\b', m[k + 1:bc]):
                    return True     # if (loading) { return; }
                continue
            end = m.find(';', k)
            if end < 0:
                continue
            if k <= pos <= end or re.match(r'return\b', m[k:end]):
                return True
        return False

    def call_sites(self, kind, name):
        """[(df, pos, guard_text, trigger)] for calls of a page method or adds of a Bloc event.

        guard_text is the caller's code before the call; trigger is 'scroll', 'button' or ''."""
        if kind == 'bloc':
            rx = re.compile(r'\badd\s*\(\s*(?:const\s+)?%s\s*[(.]' % re.escape(name))
        else:
            rx = re.compile(r'\.\s*%s\s*\(|(?<![\w$.])%s\s*\(' % (re.escape(name), re.escape(name)))
        out = []
        for df in self.files:
            m = df.masked
            for mm in rx.finditer(m):
                if kind != 'bloc' and re.match(r'\s*(?:async\s*)?(?:\{|=>)',
                                               m[(df.parens.get(mm.end() - 1) or mm.end()) + 1:][:12]):
                    continue    # the declaration itself
                fs = df.enclosing_callables(mm.start())
                if not fs:
                    out.append((df, mm.start(), self.stmt_prefix(m, mm.start()), '', False))
                    continue
                trigger = ''
                for f in fs:            # innermost first
                    lead = m[max(0, f.start - 60):f.start]
                    if f.name is None and BUTTON_ARG.search(lead):
                        trigger = 'button'
                        break
                    if (f.name and SCROLL_NAME.match(f.name)) or (f.name is None and SCROLL_ARG.search(lead)) or \
                            SCROLL_BODY.search(m[f.bo:mm.start()]):
                        trigger = 'scroll'
                        break
                    if f.name:
                        break
                lead = self.stmt_prefix(m, mm.start())     # the receiver expression of this call
                guarded = any(self.guarded_call(df, x, mm.start()) for x in fs)
                out.append((df, mm.start(), lead, trigger, guarded))
        return out

    def resolve_paging(self):
        for kind, df, pos, name, body, flag, cls_name in self.page_candidates:
            sites = self.call_sites(kind, name)
            if kind != 'bloc' and len(sites) > 1:
                # several classes may share a method name: keep the calls whose receiver names this class
                stem = re.sub(r'(?:Controller|Notifier|ViewModel|Cubit|Store|Model)$', '', cls_name)
                stems = {s.lower() for s in (cls_name, stem) if len(s) >= 3}
                mine = [s for s in sites if any(st in s[2].lower() for st in stems)]
                if mine:
                    sites = mine
            scroll = [s for s in sites if s[3] == 'scroll']
            unguarded = [s for s in sites if not s[4]]
            if flag and (not sites or not unguarded):
                continue    # the flag is set before the await and every caller checks it
            if sites and not unguarded:
                continue
            sev = 'medium' if [s for s in scroll if s in unguarded] else 'low'
            trig = ''
            if scroll:
                s = scroll[0]
                trig = ' Triggered from a scroll callback at %s:%d.' % (s[0].rel, s[0].line_of(s[1]))
            elif not sites:
                trig = ' No caller found in lib/.'
            if kind == 'bloc':
                msg = ('on<%s> has no transformer, so Bloc runs these events concurrently; a hasReachedMax check '
                       'alone does not stop two fetches of the same page.%s %s' % (name, trig, PAGE_NOTE['bloc']))
            elif flag:
                msg = ('%s() sets a loading flag but never checks it, and a caller calls it without checking it '
                       'either (%s:%d).%s %s' % (name, unguarded[0][0].rel, unguarded[0][0].line_of(unguarded[0][1]),
                                                 trig, self.page_note(kind == 'cubit')))
            else:
                msg = '%s() awaits the next page with no in-flight check before the await.%s %s' % (
                    name, trig, self.page_note(kind == 'cubit'))
            self.add(df, 'NET-005', pos, df.line_text(pos)[:120], msg, severity=sev, place=False)

    # NET-006
    def life_note(self, call, df=None):
        if df is not None and (df.layer == 'data' or df.role in ('source', 'service', 'repository',
                                                                   'repository-impl')):
            owner = DATA_OWNER.get(self.profile, DATA_OWNER['unknown'])
            return 'Give this class a close()/dispose() that calls %s, and call it from its owner. %s' % (call, owner)
        return LIFE_NOTE.get(self.profile, 'Cancel or close it when its owner is disposed (%s).') % call

    def token_note(self, call, df):
        base = LIFE_NOTE.get(self.profile, 'Cancel it when its owner is disposed (%s).') % call
        if df.layer == 'data' or df.role in ('source', 'service', 'repository', 'repository-impl'):
            return 'Take the token as a parameter from the caller that owns the request\'s lifetime instead. ' + base
        return base

    def net_cancel_tokens(self, df):
        m = df.masked
        for mm in re.finditer(r'(?<![\w$.])CancelToken\s*\(\s*\)', m):
            pos = mm.start()
            self.stats['cancel_tokens'] += 1
            prefix = self.stmt_prefix(m, pos)
            if self.returned(prefix) or re.search(r'\?\?\s*$', prefix):
                continue    # a default for a caller-supplied token: the caller cancels
            name, local = self.assigned_name(prefix)
            if name:
                if re.search(r'\b%s\s*[?!]?\s*\.\s*cancel\b' % re.escape(name), m):
                    continue
                fs = df.enclosing_callables(pos)
                if fs and re.search(r'\breturn\s+%s\b|=>\s*%s\b' % (re.escape(name), re.escape(name)),
                                    m[fs[0].bo:fs[0].bc + 1]):
                    continue
                self.add(df, 'NET-006', pos, df.line_text(pos)[:120],
                         '`%s.cancel` is never called in this file. %s' % (name, self.token_note(name + '.cancel', df)),
                         place=False)
            else:
                self.add(df, 'NET-006', pos, df.line_text(pos)[:120],
                         'a CancelToken created inline can never be cancelled. %s' % self.token_note('token.cancel', df),
                         place=False)

    # NET-007
    def net_websockets(self, df):
        m = df.masked
        rx = re.compile(r'(?<![\w$.])(?:(?:IO|Html)?WebSocketChannel|WebSocket)\s*\.\s*connect\s*\(')
        for mm in rx.finditer(m):
            pos = mm.start()
            self.stats['websockets'] += 1
            prefix = self.stmt_prefix(m, pos)
            if self.returned(prefix):
                continue
            fs = df.enclosing_callables(pos)
            if fs and fs[0].expr_body and not m[fs[0].bo + 2:pos].strip():
                continue
            name, local = self.assigned_name(prefix)
            if name:
                n = re.escape(name)
                if re.search(r'\b%s\s*[?!]?\s*\.\s*(?:sink\s*[?!]?\s*\.\s*)?close\b' % n, m) or \
                        re.search(r'onDispose\s*\([^;]*\b%s\b' % n, m):
                    continue
                if fs and local and self.name_escapes(m[fs[0].bo:fs[0].bc + 1], name) and \
                        not re.search(r'\b%s\s*[?!]?\s*\.\s*(?:sink\s*[?!]?\s*\.\s*)?close\b' % n, m):
                    # handed on (returned, wrapped, stored): the receiver owns closing it
                    if re.search(r'\breturn\s+%s\b|=>\s*%s\b|[(,]\s*%s\s*[,)]|=\s*%s\s*;' % (n, n, n, n),
                                 m[fs[0].bo:fs[0].bc + 1]):
                        continue
                self.add(df, 'NET-007', pos, df.line_text(pos)[:120],
                         '`%s` is never closed. %s' % (name, self.life_note(name + '.sink.close', df)), place=False)
            else:
                pc = df.parens.get(mm.end() - 1)
                tail = m[pc + 1:pc + 60] if pc else ''
                if re.match(r'\s*(?:\.\s*timeout\s*\([^()]*\)\s*)?\.\s*(?:stream|sink|listen|ready)\b', tail):
                    self.add(df, 'NET-007', pos, df.line_text(pos)[:120],
                             'the channel is used inline and no reference is kept to close it. %s' %
                             self.life_note('channel.sink.close', df), place=False)

    # NET-009
    def net_top_level_http(self, df):
        if df.role in UI_ROLES or df.role in LOGIC_ROLES or df.role in ROOT_ROLES or df.layer in ('domain', 'app'):
            return      # ARCH-101 / ARCH-007 / ARCH-003 own these layers
        aliases = set(re.findall(r'''import\s+['"]package:http/http\.dart['"]\s+as\s+(\w+)''', df.code))
        if not aliases:
            return
        rx = re.compile(r'(?<![\w$.])(%s)\s*\.\s*(get|post|put|patch|delete|head|read|readBytes)\s*\(' %
                        '|'.join(re.escape(a) for a in aliases))
        for mm in rx.finditer(df.masked):
            cls = df.enclosing_class(mm.start())
            if cls and STATE_CLASS.search(cls[3]):
                continue
            injected = cls and re.search(r'\b(?:%s)\s*\.\s*(?:Base)?Client\??\s+_?\w+\s*[;=,)]' %
                                         '|'.join(re.escape(a) for a in aliases), df.masked[cls[1]:cls[2]])
            self.add(df, 'NET-009', mm.start(), df.line_text(mm.start())[:120],
                     '%s.%s() opens a throwaway client%s.' % (
                         mm.group(1), mm.group(2), ' although this class already holds an injected http.Client: '
                         'call that one' if injected else ''))

    # NET-010
    def net_query(self, df):
        code = df.code
        for rec in df.strings:
            if not rec['interps']:
                continue
            for s, e, braced in rec['interps']:
                lit_before = code[rec['cs']:s - (2 if braced else 1)]
                qm = re.search(r'[?&]([\w.\[\]-]+)=$', lit_before)
                if not qm:
                    continue
                lit = code[rec['cs']:rec['ce']]
                before = df.masked[max(0, rec['s'] - 80):rec['s']]
                if not (re.match(r'^(?:https?|wss?)://', lit) or
                        re.match(r'^\$\{?(?:\w+\.)*\w*(?:base|url|host|api|endpoint|server)\w*\}?', lit, re.I) or
                        URL_CONTEXT_CALL.search(before) or
                        re.search(r'Uri\s*\.\s*(?:parse|tryParse)\s*\(\s*$', before)):
                    continue    # app route locations and other strings: not an HTTP request URL
                expr = code[s:e].strip()
                if re.search(r'encode(?:Query)?Component|encodeFull|Uri\s*\.\s*encode', expr):
                    continue
                verdict = self.text_value(df, expr, s)
                if not verdict:
                    continue
                self.add(df, 'NET-010', s, df.line_text(s)[:120],
                         '`%s` goes into ?%s= unencoded (%s).' % (expr, qm.group(1), verdict))

    def text_value(self, df, expr, pos):
        if re.search(r'(?i)(?:^|[._])(?:id|uuid|guid|slug|\w*Id|\w*_id|page|limit|offset|count|size|index)$', expr):
            return None     # identifiers and numbers are URL-safe by construction
        if re.search(r'\.\s*text\s*$', expr) and not re.search(r'\(\s*\)\s*$', expr):
            return 'controller text'
        mm = re.match(r'^(?:(?:this|widget)\s*\.\s*)?([A-Za-z_$][\w$]*)$', expr)
        if not mm:
            return None
        name = mm.group(1)
        if name in self.constants or re.match(r'^_?(?:k[A-Z]\w*|[A-Z][A-Z0-9_]+)$', name):
            return None     # a compile-time or app-wide constant
        for f in df.enclosing_callables(pos):
            for pn, pt, _ in f.params:
                if pn == name:
                    if pt and NUMERIC_TYPE.match(pt):
                        return None
                    if pt and re.match(r'^String\??$', pt):
                        return 'a String parameter'
                    return 'text-like name' if TEXT_NAMES.match(name) else None
            dm = re.search(r'\b(int|double|num|bool|String\??)\s+%s\s*=' % re.escape(name), df.masked[f.bo:pos])
            if dm:
                return None if dm.group(1) != 'String' and dm.group(1) != 'String?' else 'a String local'
        return 'text-like name' if TEXT_NAMES.match(name) else None

    # NET-008
    def collect_hosts(self, df, hosts):
        if df.layer == 'domain':
            return
        code, m = df.code, df.masked
        for rec in df.strings:
            content = code[rec['cs']:rec['ce']]
            before = m[max(0, rec['s'] - 80):rec['s']]
            host = None
            um = re.match(r'^(?:https?|wss?)://([^/\s\'"$?#{}]+)', content)
            if um and not re.match(r'^(?:https?|wss?)://[^/\s]*\$', content):
                host = um.group(1).lower()
            elif HOST_ONLY.match(content) and re.search(r'Uri\s*\.\s*https?\s*\(\s*$', before):
                host = content.lower()
            if not host or LOCAL_HOST.match(host.split(':')[0]) or CONTENT_HOST.match(host.split(':')[0]):
                continue    # local and public code/content hosts are not the app's API base
            if not (URL_CONTEXT_CALL.search(before) or URL_IN_CLIENT_CALL.search(before) or
                    URL_CONTEXT_NAME.search(before) or URL_CONTEXT_NAMED_ARG.search(before)):
                continue
            if any(NOT_API_CALL.search(n + '(') for n, _ in df.enclosing_calls(rec['s'])[:3]):
                continue    # links opened in the browser, images: not the API base URL
            if re.search(r'(?i)(?:image|img|asset|icon|avatar|photo|thumb|logo|banner|picture)\w*\s*(?::|=)\s*$', before):
                continue
            hosts.setdefault(host, []).append((df, rec['s']))

    def net_hosts(self, hosts):
        for host in sorted(hosts):
            sites = hosts[host]
            by_file = {}
            for df, pos in sites:
                by_file.setdefault(df.rel, (df, pos))
            if len(by_file) < 2:
                continue
            cfg = [r for r in by_file if CONFIG_PATH.search(r.rsplit('/', 1)[-1]) or
                   re.search(r'(?i)/(config|env|constants?)/', r)]
            report = [r for r in sorted(by_file) if r not in cfg] if cfg else sorted(by_file)[1:]
            for rel in report:
                df, pos = by_file[rel]
                others = [r for r in sorted(by_file) if r != rel]
                note = '%s also appears in %s%s.' % (host, ', '.join(others[:4]),
                                                       ' (+%d more)' % (len(others) - 4) if len(others) > 4 else '')
                if cfg:
                    note += ' Use the value from %s.' % cfg[0]
                note += ' Cross-reference: AP-hardcoded-config-in-sources (flutter-architecture).'
                self.add(df, 'NET-008', pos, df.line_text(pos)[:120], note)


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
    sys.stderr.write('check_networking.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_networking.py <project-root> [--json] [--files <list>] '
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
    use_arch = bool(arch_files)

    files = []
    skipped = {'generated': 0, 'barrel': 0}
    for rel in rels:
        if use_arch and rel not in arch_files:
            skipped['generated'] += 1      # arch_check decides what is generated (CONTRACTS §18)
            continue
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if GENERATED_HEADER.search(df.raw[:600]):
            skipped['generated'] += 1
            continue
        a = arch_files.get(rel)
        if a:
            df.layer, df.role = a.get('layer') or 'other', a.get('role') or 'other'
        else:
            df.layer, df.role = classify_fallback(rel)
        if df.role == 'barrel':
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
    clean = bool(arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('clean_architecture'))
    if not arch:
        clean = any('/domain/' in r for r in rels) and any('/data/' in r for r in rels) and \
            any(('/usecases/' in r or '/use_cases/' in r or '/entities/' in r) for r in rels)

    ck = Checker(root, files, profile, clean, pubspec_deps(pubspec))
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

    out = ['== NETWORKING',
           '  profile: %s%s (%s)' % (profile, ' + clean' if clean else '', psource),
           '  classification: %s' % classification,
           '  scanned: %d files; packages: %s; %s, %s, %s, %s, %s, %s' % (
               len(files), ', '.join(stats['packages']) or 'none declared',
               plural(stats['dio_clients'], 'Dio client'), plural(stats['http_clients'], 'http client'),
               plural(stats['interceptors'], 'interceptor'), plural(stats['websockets'], 'WebSocket'),
               plural(stats['cancel_tokens'], 'CancelToken'), plural(stats['page_handlers'], 'page handler'))]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no networking findings')
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
