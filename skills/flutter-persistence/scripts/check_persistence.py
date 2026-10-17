#!/usr/bin/env python3
"""check_persistence.py: find unsafe or fragile local-storage code in a Flutter project (read-only).

Usage:
  python3 -I check_persistence.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (Hive type ids, database classes and
             call sites are resolved across files); only findings in the listed files
             are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  PERSIST-001 sql-built-from-strings          PERSIST-006 database-opened-per-use
  PERSIST-002 drift-schema-without-migration  PERSIST-007 writes-in-loop-without-transaction
  PERSIST-003 sqflite-version-without-upgrade PERSIST-008 drift-migrations-untested
  PERSIST-004 hive-type-id-collision          PERSIST-009 sensitive-store-unencrypted
  PERSIST-005 hive-field-index-collision

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so.

Suppression (in the analysed code):
  // persist-ignore: PERSIST-001 <reason>        on the reported line or the line above
  // persist-ignore-file: PERSIST-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/persistence@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

RULES = {
    'PERSIST-001': ('sql-built-from-strings', 'high',
                    'SQL text is built by interpolating or concatenating a value that is not a constant. A quote in '
                    'that value changes the statement (SQL injection, or a crash on an apostrophe). Bind values with '
                    '? arguments / Variable, and allow-list identifiers.'),
    'PERSIST-002': ('drift-schema-without-migration', 'high',
                    'A drift database has schemaVersion > 1 but no MigrationStrategy with onUpgrade. Drift\'s default '
                    'onUpgrade throws, so every existing install fails to open the database after the update.'),
    'PERSIST-003': ('sqflite-version-without-upgrade', 'high',
                    'A sqflite database is opened with version > 1 but no onUpgrade callback. Existing installs '
                    'keep the old schema (onCreate only runs on a fresh install) and queries on new columns fail.'),
    'PERSIST-004': ('hive-type-id-collision', 'high',
                    'Two Hive adapters use the same typeId. Registration throws, or records written by one type '
                    'are read back with the other adapter. Give every adapter a unique, never-reused typeId.'),
    'PERSIST-005': ('hive-field-index-collision', 'high',
                    'Two fields of one Hive type share a @HiveField index, so one overwrites the other on disk. '
                    'Field indexes must be unique and never reused, even after a field is removed.'),
    'PERSIST-006': ('database-opened-per-use', 'medium',
                    'A database instance is created per call, per screen or by a provider that is disposed when '
                    'unwatched. Each instance opens its own connection: watch() streams miss writes made through '
                    'the other one, writes can hit "database is locked", and the file is opened over and over. '
                    'Create one instance in the composition root and inject it.'),
    'PERSIST-007': ('writes-in-loop-without-transaction', 'medium',
                    'Database writes are awaited one by one in a loop without a transaction or batch. Each write is '
                    'its own commit (slow), and a crash halfway leaves half the data written.'),
    'PERSIST-008': ('drift-migrations-untested', 'low',
                    'A drift database has schemaVersion > 1, but the project has no exported schemas '
                    '(drift_schemas/) and no SchemaVerifier migration test, so a broken migration ships unnoticed.'),
    'PERSIST-009': ('sensitive-store-unencrypted', 'medium',
                    'A box, table or database named for health, payment, identity or similar personal data is stored '
                    'without encryption at rest. It sits in plain text in the app sandbox and in device backups.'),
}

# where the storage code goes, per architecture (appended to notes)
PLACE = {
    'mvn': 'MVN: keep the store in data/sources (a local source) used by the repository impl; use cases and notifiers stay unchanged.',
    'mvvm': 'MVVM: keep the store in a service under data/services used by the repository, which owns caching; view models stay unchanged.',
    'bloc': 'Bloc: keep the store in a data provider / API class used by the repository; blocs and cubits stay unchanged.',
    'riverpod': 'Riverpod: expose the database through one keepAlive provider and use it only from repository/source providers.',
    'provider': 'Provider: create the database once at the root (Provider(create:, dispose:)) and pass it to the repository; ChangeNotifiers stay unchanged.',
    'getx': 'GetX: register the database once (a permanent GetxService or Get.put(permanent: true)) and use it only from repositories; controllers stay unchanged.',
    'mvc': 'MVC: keep the store in the model/service layer behind a repository; controllers stay unchanged.',
    'setstate': 'Keep the store in one data-layer class created at startup; widgets call a repository, never the database.',
    'unknown': 'Keep the store in a data-layer source behind a repository, created once and injected.',
}
PLACE_CLEAN = 'Clean: data/datasources/local, mapped to domain entities in the repository impl; the domain layer stays unchanged.'

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.gen|\.steps|\.drift|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit')
SUPPRESS_RE = re.compile(r'persist-ignore(-file)?\s*:\s*((?:PERSIST-\d{3})(?:\s*,\s*PERSIST-\d{3})*)\s*(.*)')

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
                      r'([A-Za-z_]\w*)?[^{;]*?\{')
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

SQL_START = re.compile(r'(?is)^\W*(select|insert|update|delete|replace|create|drop|alter|pragma|with|vacuum|attach|'
                       r'detach|begin|savepoint|analyze|reindex|upsert)\b')
SQL_CALLS = ('rawQuery', 'rawInsert', 'rawUpdate', 'rawDelete', 'customSelect', 'customStatement', 'customUpdate',
             'customInsert', 'customWriteReturning', 'CustomExpression', 'execute', 'select', 'prepare',
             'rawQueryCursor')
SQL_ALWAYS = {'rawQuery', 'rawInsert', 'rawUpdate', 'rawDelete', 'customSelect', 'customStatement', 'customUpdate',
              'customInsert', 'customWriteReturning', 'rawQueryCursor'}
SQL_CALL_RE = re.compile(r'(?<![\w$])(' + '|'.join(SQL_CALLS) + r')\s*(?:<[^()]*?>)?\s*\(')
SAFE_NAME = re.compile(r'^(?:k[A-Z]\w*|_?[A-Z][A-Z0-9_]+|_?k[A-Z]\w*|schemaVersion|\w*[Pp]laceholders?\w*)$')
SAFE_SUFFIX = re.compile(r'\.\s*(?:length|index|hashCode|inMilliseconds|inSeconds|inMinutes|inHours|inDays|'
                         r'inMicroseconds|millisecondsSinceEpoch|microsecondsSinceEpoch|year|month|day|hour|minute|'
                         r'second|isEmpty|isNotEmpty|toInt\(\s*\)|round\(\s*\)|floor\(\s*\)|ceil\(\s*\)|'
                         r'toIso8601String\(\s*\)|actualTableName|tableName|\$name|entityName|escapedName)\s*$')
NUMERIC_TYPE = re.compile(r'^(?:int|double|num|bool|DateTime|Duration|BigInt)\??$')
TAINT_TYPE = re.compile(r'(?:\bString\b|\bdynamic\b|\bObject\b|\bMap\b)')
STORE_PKGS = ('drift', 'sqflite', 'sqflite_common', 'sqflite_common_ffi', 'sqflite_sqlcipher', 'sqlite3', 'hive',
              'hive_flutter', 'hive_ce', 'hive_ce_flutter', 'isar', 'isar_community', 'objectbox',
              'shared_preferences', 'flutter_secure_storage', 'get_storage', 'realm', 'sembast')
CIPHER_PKGS = ('sqlcipher_flutter_libs', 'sqflite_sqlcipher', 'sqlite3mc', 'sqlite3_multiple_ciphers',
               'drift_sqlcipher')

SENSITIVE_HIGH = {'health', 'medical', 'patient', 'patients', 'diagnosis', 'diagnoses', 'prescription',
                  'prescriptions', 'medication', 'medications', 'ssn', 'passport', 'passports', 'biometric',
                  'biometrics', 'creditcard', 'creditcards', 'iban'}
SENSITIVE_PAIRS = (('credit', 'card'), ('credit', 'cards'), ('card', 'number'), ('card', 'numbers'),
                   ('bank', 'account'), ('bank', 'accounts'), ('social', 'security'), ('national', 'id'))
SENSITIVE_LOW = {'payment', 'payments', 'salary', 'salaries', 'insurance', 'banking'}


VALUE_BEFORE = re.compile(r'''(?is)(?:['"%]|[=<>]|!=|\b(?:like|glob|is|not|in|values|between|and|limit|offset)\s*\(?|[(,])\s*$''')


def is_value_position(sql_before):
    """True when the SQL text right before an interpolation expects a value (not a table/column name)."""
    t = sql_before.rstrip()
    if re.search(r'(?is)\b(?:from|join|into|update|table|exists|index|on|order\s+by|group\s+by|select|as)\s*$', t):
        return False
    if t.endswith(',') and re.search(r'(?is)\bselect\b(?:(?!\bfrom\b).)*$', t):
        return False                    # SELECT a, $col
    return bool(VALUE_BEFORE.search(sql_before))


def sensitive_level(name):
    t = toks_of(name)
    if set(t) & SENSITIVE_HIGH:
        return 'medium', sorted(set(t) & SENSITIVE_HIGH)[0]
    for a, b in SENSITIVE_PAIRS:
        for i in range(len(t) - 1):
            if t[i] == a and t[i + 1] == b:
                return 'medium', '%s %s' % (a, b)
    if set(t) & SENSITIVE_LOW:
        return 'low', sorted(set(t) & SENSITIVE_LOW)[0]
    return None, None


# ---------------------------------------------------------------------------------------- checker

class Checker(object):
    def __init__(self, root, files, profile, clean, pubspec_deps):
        self.root = root
        self.files = files
        self.by_rel = dict((f.rel, f) for f in files)
        self.profile = profile
        self.clean = clean
        self.deps = pubspec_deps
        self.findings = []
        self.suppressed = []
        self.stats = {'stores': sorted(d for d in pubspec_deps if d in STORE_PKGS), 'sql_calls': 0,
                      'drift_databases': 0, 'sqflite_opens': 0, 'hive_types': 0, 'loops_with_writes': 0}
        self.global_safe = set()
        self.global_int = {}
        self.drift_dbs = {}        # class name -> (df, class tuple, version)
        self._call_cache = {}

    # -- reporting
    def place(self):
        p = PLACE.get(self.profile, PLACE['unknown'])
        if self.clean and self.profile != 'mvn':
            p += ' ' + PLACE_CLEAN
        return p

    def add(self, df, rid, pos, evidence, note='', severity=None, place=True):
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
        if place:
            note = (note + ' ' if note else '') + self.place()
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    # -- project index: constants and ints declared top-level or static
    def index(self):
        decl = re.compile(r'(?<![\w$.])(static\s+)?(const|final)\s+(?:[A-Za-z_$][\w$<>?,\s]*?\s+)?([A-Za-z_$][\w$]*)\s*='
                          r'\s*([^;]*);')
        for df in self.files:
            m = df.masked
            for mm in decl.finditer(m):
                pos = mm.start()
                cls = df.enclosing_class(pos)
                in_fn = df.enclosing_callables(pos)
                if in_fn:
                    continue
                if cls and not mm.group(1):
                    continue
                name = mm.group(3)
                self.global_safe.add(name)
                v = df.code[mm.start(4):mm.end(4)].strip()
                if re.match(r'^\d+$', v):
                    self.global_int[name] = int(v)

    def resolve_int(self, df, txt):
        txt = txt.strip()
        if re.match(r'^\d+$', txt):
            return int(txt)
        mm = re.match(r'^(?:[A-Z]\w*\s*\.\s*)?([A-Za-z_$][\w$]*)$', txt)
        if mm and mm.group(1) in self.global_int:
            return self.global_int[mm.group(1)]
        return None

    # -- taint analysis for PERSIST-001
    def taint_expr(self, df, s, e, depth=0):
        """Classify the expression df.raw[s:e]: ('safe'|'input'|'param'|'unknown', detail)."""
        raw = df.raw[s:e]
        if depth > 5:
            return 'unknown', raw.strip()
        if re.search(r'''['"]\s*\?\s*(?:,\s*)?['"]''', raw) or re.search(r'''['"]\?['"]''', raw):
            return 'safe', ''
        st = raw.strip()
        if not st or re.match(r'^-?\d+(\.\d+)?$', st):
            return 'safe', ''
        if SAFE_SUFFIX.search(df.iview[s:e]):
            return 'safe', ''
        if re.search(r'\.\s*text\b(?!\s*\()', df.iview[s:e]):
            return 'input', st
        view = df.iview[s:e]
        view = re.sub(r'\bthis\s*\.\s*', '', view)
        lam = set()
        for lm in re.finditer(r'\(([^()]*)\)\s*(?:async\s*)?(?:=>|\{)', view):
            for p in parse_params(lm.group(1), 0, len(lm.group(1))):
                lam.add(p[0])
        for lm in re.finditer(r'(?<![\w$])([A-Za-z_$][\w$]*)\s*=>', view):
            lam.add(lm.group(1))
        worst = ('safe', '')
        rank = {'safe': 0, 'fed': 1, 'unknown': 2, 'param': 3, 'input': 4}
        for im in re.finditer(r'(?<![\w$.])([A-Za-z_$][\w$]*)\b', view):
            name = im.group(1)
            after = view[im.end():im.end() + 3]
            if name in KEYWORDS or name in lam or name[0].isupper() and not re.match(r'^_?[A-Z][A-Z0-9_]+$', name):
                continue
            if re.match(r'\s*\(', after) or re.match(r'\s*:(?!:)', after):
                continue        # a function name or a named-argument label
            if re.match(r'\s*<', after) and re.match(r'\s*<[\w\s,?<>]*>\s*\(', view[im.end():im.end() + 60]):
                continue
            r = self.resolve(df, name, s + im.start(), depth)
            if rank[r[0]] > rank[worst[0]]:
                worst = r
        return worst

    def resolve(self, df, name, pos, depth):
        if SAFE_NAME.match(name):
            return 'safe', ''
        m = df.masked
        for f in df.enclosing_callables(pos):
            for i, (pn, pt, named) in enumerate(f.params):
                if pn != name:
                    continue
                if pt and (NUMERIC_TYPE.match(pt) or not TAINT_TYPE.search(pt)):
                    return 'safe', ''
                if f.name is None:
                    return 'unknown', name
                return self.param_taint(df, f, i, name, depth)
            r = self.local_decl(df, f.bo, f.bc, name, pos, depth)
            if r:
                return r
        cls = df.enclosing_class(pos)
        if cls:
            r = self.member_decl(df, cls, name, depth)
            if r:
                return r
        r = self.local_decl(df, 0, len(m), name, pos, depth, top_only=True)
        if r:
            return r
        if name in self.global_safe:
            return 'safe', ''
        return 'unknown', name

    def local_decl(self, df, lo, hi, name, pos, depth, top_only=False):
        m = df.masked
        rx = re.compile(r'(?<![\w$.])(const|final|var|late\s+final|late|[A-Za-z_$][\w$]*(?:<[^;=()]*?>)?\??)\s+%s\s*'
                        r'(=|;|,)' % re.escape(name))
        best = None
        for dm in rx.finditer(m, lo, min(hi, len(m))):
            if top_only and (df.enclosing_callables(dm.start()) or df.enclosing_class(dm.start())):
                continue
            if not top_only and dm.start() > pos:
                break
            if dm.group(1) in KEYWORDS and dm.group(1) not in ('const', 'final', 'var'):
                continue
            best = dm
        if best is None:
            # for-in loop variable (including patterns): for (final x in xs) / for (final (a, b) in ...)
            for fm in re.finditer(r'\bfor\s*\(', m[lo:pos] if not top_only else ''):
                po = lo + fm.end() - 1
                pc = df.parens.get(po)
                if pc is None:
                    continue
                k = pc + 1 + len(m[pc + 1:pc + 40]) - len(m[pc + 1:pc + 40].lstrip())
                end = df.braces.get(k, k) if k < len(m) and m[k] == '{' else expr_end(m, k)
                if not (po < pos <= end):
                    continue
                head = m[po + 1:pc]
                im = re.search(r'\sin\s', head)
                if not im or not re.search(r'(?<![\w$])%s(?![\w$])' % re.escape(name), head[:im.start()]):
                    continue
                return self.taint_expr(df, po + 1 + im.end(), pc, depth + 1)
            return None
        kind = best.group(1)
        if kind == 'const':
            return 'safe', ''
        if kind not in ('final', 'var', 'late final', 'late') and NUMERIC_TYPE.match(kind):
            return 'safe', ''
        if top_only and kind in ('final',):
            return 'safe', ''
        if best.group(2) != '=':
            return 'unknown', name
        vs = best.end()
        ve = expr_end(m, vs)
        return self.taint_expr(df, vs, ve, depth + 1)

    def member_decl(self, df, cls, name, depth):
        m = df.masked
        body = m[cls[1]:cls[2]]
        g = re.search(r'([A-Za-z_$][\w$<>?]*)\s+get\s+%s\b' % re.escape(name), body)
        if g:
            if NUMERIC_TYPE.match(g.group(1)):
                return 'safe', ''
            gs = cls[1] + g.end()
            tm = re.match(r'\s*=>\s*', m[gs:gs + 10])
            if tm:
                return self.taint_expr(df, gs + tm.end(), expr_end(m, gs + tm.end()), depth + 1)
            return 'unknown', name
        d = re.search(r'(?<![\w$.])(static\s+)?(const|final|late\s+final|late|var)?\s*([A-Za-z_$][\w$<>?,\s]*?)?\s+%s\s*'
                      r'(=|;)' % re.escape(name), body)
        if d:
            if d.group(2) == 'const' or (d.group(1) and d.group(2) in ('final', 'const')):
                return 'safe', ''
            t = (d.group(3) or '').strip()
            if t and NUMERIC_TYPE.match(t):
                return 'safe', ''
            if d.group(4) == '=' and d.group(2) == 'final':
                vs = cls[1] + d.end()
                return self.taint_expr(df, vs, expr_end(m, vs), depth + 1)
            return 'unknown', name
        return None

    def param_taint(self, df, f, idx, name, depth):
        """A string-like parameter: safe only if every call site in lib/ passes a safe value."""
        pn, pt, named = f.params[idx]
        positional_idx = len([p for p in f.params[:idx] if not p[2]])
        files = [df] if f.name.startswith('_') else self.files
        sites = 0
        call = re.compile(r'(?<![\w$])%s\s*(?:<[^()]*?>)?\s*\(' % re.escape(f.name))
        for cf in files:
            for cm in call.finditer(cf.masked):
                po = cm.end() - 1
                if cf is df and po == f.ps:
                    continue
                pc = cf.parens.get(po)
                if pc is None:
                    continue
                if re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>)', cf.masked[pc + 1:pc + 30]):
                    continue        # another declaration (override)
                args = split_top(cf.masked, po + 1, pc)
                target = None
                k = 0
                for a, b in args:
                    nm = re.match(r'\s*([A-Za-z_]\w*)\s*:(?!:)', cf.masked[a:b])
                    if nm:
                        if named and nm.group(1) == pn:
                            target = (a + nm.end(), b)
                    else:
                        if not named and k == positional_idx:
                            target = (a, b)
                        k += 1
                if target is None:
                    continue
                sites += 1
                r = self.taint_expr(cf, target[0], target[1], depth + 1)
                if r[0] not in ('safe', 'fed'):
                    return 'param', '%s (parameter of %s)' % (name, f.name)
        if sites == 0:
            return 'param', '%s (parameter of %s)' % (name, f.name)
        return 'fed', '%s (parameter of %s that gets a constant at %s today)' % (
            name, f.name, 'its only call site' if sites == 1 else 'all %d call sites' % sites)

    # -- rules
    def run(self):
        self.index()
        for df in self.files:
            self.find_drift_dbs(df)
        for df in self.files:
            if df.role == 'di':
                self.check_db_instances(df, lifetime_only=True)
                continue
            self.check_sql(df)
            self.check_where_args(df)
            self.check_sqflite_open(df)
            self.check_db_instances(df)
            self.check_loops(df)
            self.check_sensitive(df)
        self.check_drift_migrations()
        self.check_hive()

    # PERSIST-001 ---------------------------------------------------------
    def sql_pieces(self, df, s, e, depth=0):
        """Split an SQL argument into literal and non-literal pieces.

        Returns (literal_text, interps, concat_ranges) or None when the argument is not literal SQL."""
        m = df.masked
        s, e = strip_range(m, s, e)
        if s >= e:
            return None
        pieces = split_top(m, s, e, seps='+')
        text, interps, concat = '', [], []
        lit_seen = False
        for a, b in pieces:
            a, b = strip_range(m, a, b)
            core = m[a:b]
            if re.match(r'''^(?:\s*r?(?:'{3}|"{3}|'|")[\s\S]*?)+$''', core) and \
                    re.match(r'^[\s\'"rR]*$', re.sub(r"'''|\"\"\"", '', core).replace(' ', '')) is not None:
                for r in df.top_strings(a, b):
                    lit_seen = True
                    k = r['cs']
                    for i0, i1, braced in r['interps']:
                        dollar = i0 - (2 if braced else 1)
                        text += df.raw[k:dollar] + 'X'
                        value_pos = is_value_position(text[:-1] if text.endswith('X') else text)
                        interps.append((i0, i1, value_pos))
                        k = i1 + (1 if braced else 0)
                    text += df.raw[k:r['ce']]
            elif len(pieces) == 1 and re.match(r'^[A-Za-z_$][\w$]*$', core) and depth == 0:
                init = self.string_local(df, a, core)
                if init is None:
                    return None
                return self.sql_pieces(df, init[0], init[1], depth + 1)
            else:
                concat.append((a, b, is_value_position(text)))
                text += 'X'
        if not lit_seen:
            return None
        return text, interps, concat

    def string_local(self, df, pos, name):
        fs = df.enclosing_callables(pos)
        if not fs:
            return None
        f = fs[0] if not fs[0].expr_body else (fs[1] if len(fs) > 1 else fs[0])
        m = df.masked
        best = None
        for dm in re.compile(r'(?<![\w$.])(final|var|String)\s+%s\s*=' % re.escape(name)).finditer(m, f.bo, pos):
            best = dm
        if best is None:
            return None
        vs = best.end()
        return vs, expr_end(m, vs)

    def check_sql(self, df):
        m = df.masked
        for cm in SQL_CALL_RE.finditer(m):
            meth = cm.group(1)
            po = cm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            if re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>)', m[pc + 1:pc + 30]):
                continue        # a declaration
            args = split_top(m, po + 1, pc)
            first = None
            for a, b in args:
                if not re.match(r'\s*[A-Za-z_]\w*\s*:(?!:)', m[a:b]):
                    first = (a, b)
                    break
            if first is None:
                continue
            res = self.sql_pieces(df, first[0], first[1])
            if res is None:
                continue
            text, interps, concat = res
            if meth not in SQL_ALWAYS and not SQL_START.match(text):
                continue
            if not text.strip('X \n\t'):
                continue
            self.stats['sql_calls'] += 1
            self.judge_sql(df, cm.start(), meth, interps, concat, text)

    def judge_sql(self, df, pos, meth, interps, concat, sql_text=''):
        hits = []
        for i0, i1, value_pos in interps:
            r = self.taint_expr(df, i0, i1)
            hits.append((r, value_pos, df.raw[i0:i1].strip()))
        for a, b, value_pos in concat:
            r = self.taint_expr(df, a, b)
            hits.append((r, value_pos, df.raw[a:b].strip()))
        rank = {'input': 0, 'param': 1, 'unknown': 2, 'fed': 3}
        pragma = bool(re.match(r'(?is)^\W*pragma\b', sql_text))
        bad = [h for h in hits if h[0][0] in rank and not (h[0][0] == 'fed' and not h[1])
               and not (pragma and h[0][0] in ('unknown', 'fed'))]
        if not bad:
            return
        bad.sort(key=lambda h: (rank[h[0][0]], not h[1]))
        (kind, detail), value_pos, expr = bad[0]
        sev = 'high' if kind in ('input', 'param') else 'low'
        if kind == 'input':
            why = '`%s` is text the user typed' % expr
        elif kind == 'param':
            why = '`%s` is a %s, so callers control the SQL' % (expr, (detail.split(' (', 1)[-1].rstrip(')')
                                                                      if '(' in detail else 'parameter'))
        elif kind == 'fed':
            why = '`%s` is a %s, but it sits in a quoted value position' % (expr, detail.split(' (', 1)[-1].rstrip(')'))
        else:
            why = '`%s` is not a constant the checker can trace; confirm it never comes from input' % expr
        fix = ('bind it: replace the value (and its quotes) with ? and pass [%s] as arguments (sqflite) or '
               'variables: [Variable(%s)] (drift)' % (expr, expr)) if value_pos else \
            'identifiers cannot be bound: check it against an allow-list of known table/column names before use'
        more = len(bad) - 1
        note = '%s; %s%s.' % (why, fix, ' (+%d more in this statement)' % more if more else '')
        self.add(df, 'PERSIST-001', pos, df.line_text(pos), note=note, severity=sev)

    def check_where_args(self, df):
        if not (df.imports & {'sqflite', 'sqflite_common', 'sqflite_common_ffi', 'sqflite_sqlcipher'}):
            return
        m = df.masked
        for wm in re.finditer(r'(?<![\w$])(where|having)\s*:\s*', m):
            calls = df.enclosing_calls(wm.start())
            if not calls or calls[0][0] not in ('query', 'update', 'delete', 'queryCursor'):
                continue
            vs = wm.end()
            ve = expr_end(m, vs)
            res = self.sql_pieces(df, vs, ve)
            if res is None:
                continue
            text, interps, concat = res
            if not interps and not concat:
                continue
            self.stats['sql_calls'] += 1
            self.judge_sql(df, wm.start(), calls[0][0], interps, concat, text)

    # PERSIST-002 / 008 ---------------------------------------------------
    def find_drift_dbs(self, df):
        m = df.masked
        for name, o, c, header, hs in df.classes:
            if not re.search(r'\bextends\s+(?:_?\$\w+|GeneratedDatabase)(?![\w$])', header):
                continue
            prev_end = max([cc[2] for cc in df.classes if cc[2] < hs] or [0])
            before = m[max(prev_end, hs - 4000):hs]
            if '@DriftDatabase' not in before and '@UseMoor' not in before and \
                    not re.search(r'\bschemaVersion\b', m[o:c]):
                continue
            if '@DriftAccessor' in before:
                continue
            body = m[o:c]
            vm = re.search(r'\bint\s+get\s+schemaVersion\s*(?:=>\s*([^;]+);|\{\s*return\s+([^;]+);)', body)
            version = None
            vpos = o
            if vm:
                version = self.resolve_int(df, vm.group(1) or vm.group(2))
                vpos = o + vm.start()
            self.drift_dbs[name] = (df, (name, o, c, header, hs), version, vpos)
            self.stats['drift_databases'] += 1

    def check_drift_migrations(self):
        exported = self.has_drift_schemas()
        for name, (df, cls, version, vpos) in sorted(self.drift_dbs.items()):
            if df.role == 'di' or version is None or version <= 1:
                continue
            m = df.masked
            body = m[cls[1]:cls[2]]
            mg = re.search(r'\bget\s+migration\b', body)
            if not mg:
                self.add(df, 'PERSIST-002', vpos, df.line_text(vpos),
                         note='%s is at schemaVersion %d and has no migration getter. Add `@override MigrationStrategy '
                              'get migration => MigrationStrategy(onUpgrade: stepByStep(from1To2: ...))` generated with '
                              '`dart run drift_dev make-migrations`.' % (name, version), place=False)
                continue
            gs = cls[1] + mg.end()
            tm = re.match(r'\s*(=>|\{)', m[gs:gs + 10])
            if not tm:
                continue
            if tm.group(1) == '{':
                go = gs + tm.start(1)
                ge = df.braces.get(go, go)
            else:
                ge = expr_end(m, gs + tm.end())
            gbody = m[gs:ge]
            if 'MigrationStrategy' in gbody and not re.search(r'\bonUpgrade\s*:', gbody):
                self.add(df, 'PERSIST-002', vpos, df.line_text(vpos),
                         note='%s is at schemaVersion %d, but its MigrationStrategy has no onUpgrade, so drift\'s '
                              'default (which throws) runs on every upgraded install. Add onUpgrade: stepByStep(...).'
                         % (name, version), place=False)
                continue
            if not exported:
                self.add(df, 'PERSIST-008', vpos, df.line_text(vpos),
                         note='%s is at schemaVersion %d. Run `dart run drift_dev make-migrations` to export each '
                              'version to drift_schemas/ and generate a SchemaVerifier test, then test every '
                              'fromNToM step.' % (name, version), place=False)

    def has_drift_schemas(self):
        for dp, dns, fns in os.walk(self.root):
            rel = os.path.relpath(dp, self.root)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            dns[:] = [d for d in dns if not d.startswith('.') and d not in ('build', 'node_modules', 'ios', 'android',
                                                                            'macos', 'windows', 'linux', 'web')]
            if depth >= 4:
                dns[:] = []
            if os.path.basename(dp) == 'drift_schemas' or any(re.match(r'drift_schema_v\d+\.json$', f) for f in fns):
                return True
            if (os.sep + 'test') in (os.sep + rel) or rel.startswith('test'):
                for fn in fns:
                    if re.match(r'schema_v\d+\.dart$', fn) or fn == 'schema.dart':
                        return True
                    if fn.endswith('_test.dart'):
                        try:
                            with open(os.path.join(dp, fn), encoding='utf-8', errors='replace') as fh:
                                if 'SchemaVerifier' in fh.read():
                                    return True
                        except OSError:
                            pass
        return False

    # PERSIST-003 ---------------------------------------------------------
    def check_sqflite_open(self, df):
        m = df.masked
        for om in re.finditer(r'(?<![\w$])(openDatabase|OpenDatabaseOptions)\s*\(', m):
            po = om.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            if re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>)', m[pc + 1:pc + 30]):
                continue
            named = {}
            for a, b in split_top(m, po + 1, pc):
                nm = re.match(r'\s*([A-Za-z_]\w*)\s*:(?!:)', m[a:b])
                if nm:
                    named[nm.group(1)] = (a + nm.end(), b)
            if om.group(1) == 'openDatabase' and 'options' in named:
                continue
            self.stats['sqflite_opens'] += 1
            if 'version' not in named or 'onUpgrade' in named:
                continue
            if 'readOnly' in named and re.match(r'\s*true\b', m[named['readOnly'][0]:named['readOnly'][1]]):
                continue
            v = self.resolve_int(df, df.code[named['version'][0]:named['version'][1]])
            if v is None or v <= 1:
                continue
            extra = '' if 'onCreate' in named else ' (and no onCreate either)'
            self.add(df, 'PERSIST-003', om.start(), df.snippet(om.start(), min(pc + 1, om.start() + 110)),
                     note='version: %d with no onUpgrade%s. Add onUpgrade: (db, oldVersion, newVersion) async { if '
                          '(oldVersion < 2) { ... } } with one step per version, run in a batch, and keep onCreate '
                          'creating the latest schema.' % (v, extra), place=False)

    # PERSIST-004 / 005 ---------------------------------------------------
    def check_hive(self):
        ids = {}
        for df in self.files:
            if df.role == 'di':
                continue
            m = df.masked
            for hm in re.finditer(r'@HiveType\s*\(\s*typeId\s*:\s*([^,)]+)', m):
                v = self.resolve_int(df, df.code[hm.start(1):hm.end(1)])
                cls = None
                for c in df.classes:
                    if c[4] > hm.start():
                        cls = c
                        break
                self.stats['hive_types'] += 1
                if v is not None:
                    ids.setdefault(v, []).append((df, hm.start(), cls[0] if cls else '?'))
                if cls:
                    self.check_hive_fields(df, cls)
            for name, o, c, header, hs in df.classes:
                if not re.search(r'\bextends\s+TypeAdapter\s*<', header):
                    continue
                tm = re.search(r'\btypeId\s*(?:=>|=)\s*([\w$.]+)', m[o:c])
                if not tm:
                    continue
                v = self.resolve_int(df, tm.group(1))
                if v is not None:
                    ids.setdefault(v, []).append((df, o + tm.start(), name))
        for v, uses in sorted(ids.items()):
            if len(uses) < 2:
                continue
            uses.sort(key=lambda u: (u[0].rel, u[1]))
            first = uses[0]
            for df, pos, name in uses[1:]:
                self.add(df, 'PERSIST-004', pos, df.line_text(pos),
                         note='typeId %d is also used by %s (%s:%d). Pick an unused id and keep a registry of '
                              'used ids in one place (hive_ce: GenerateAdapters assigns them).' % (
                                  v, first[2], first[0].rel, first[0].line_of(first[1])), place=False)

    def check_hive_fields(self, df, cls):
        m = df.masked
        seen = {}
        for fm in re.finditer(r'@HiveField\s*\(\s*([\w$.]+)', m[cls[1]:cls[2]]):
            v = self.resolve_int(df, fm.group(1))
            if v is None:
                continue
            pos = cls[1] + fm.start()
            if v in seen:
                self.add(df, 'PERSIST-005', pos, df.line_text(pos),
                         note='index %d is already used in %s at line %d. Use the next unused index; never reuse '
                              'the index of a removed field.' % (v, cls[0], df.line_of(seen[v])), place=False)
            else:
                seen[v] = pos

    # PERSIST-006 ---------------------------------------------------------
    def check_db_instances(self, df, lifetime_only=False):
        names = sorted(self.drift_dbs)
        pats = []
        if names:
            pats.append(r'(?<![\w$.])(?:new\s+)?(' + '|'.join(re.escape(n) for n in names) +
                        r')(?:\s*\.\s*[a-z_$][\w$]*)?\s*\(')
        pats.append(r'(?<![\w$])(Isar\s*\.\s*open(?:Sync)?|openStore)\s*\(')
        m = df.masked
        for pat in pats:
            for cm in re.finditer(pat, m):
                name = cm.group(1)
                pos = cm.start(1)
                po = cm.end() - 1
                pc = df.parens.get(po)
                if pc is None or re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>|:)', m[pc + 1:pc + 30]):
                    continue        # a constructor declaration
                before = m[max(0, pos - 40):pos]
                if re.search(r'\b(class|extends|implements|with|new)\s*$', before) and 'new' not in before[-5:]:
                    continue
                cls = df.enclosing_class(pos)
                if cls and cls[0] == name:
                    continue
                verdict = self.instance_context(df, pos, pc)
                if verdict is None:
                    continue
                if lifetime_only and not verdict[0].startswith('lifetime'):
                    continue
                self.add(df, 'PERSIST-006', pos, df.line_text(pos), note=verdict[1])

    def instance_context(self, df, pos, pc):
        m = df.masked
        fs = df.enclosing_callables(pos)
        calls = df.enclosing_calls(pos)
        # provider lifetime first
        for cname, cpo in calls:
            pre = m[max(0, cpo - 60):cpo]
            if re.search(r'\.\s*autoDispose\b[^;]*$', pre) or cname == 'autoDispose':
                return ('lifetime', 'built inside an autoDispose provider: the database is closed and reopened '
                                    'whenever nothing watches it, and open streams break. Drop autoDispose for the '
                                    'database provider.')
            if cname in ('registerFactory', 'registerFactoryParam', 'registerFactoryAsync'):
                return ('lifetime', 'registered with %s, so every lookup builds a new database. Use '
                                    'registerLazySingleton (with dispose: (db) => db.close()).' % cname)
        for f in fs[::-1]:
            if f.name and not df.enclosing_callables(f.start):
                ann = m[max(0, f.start - 200):f.start]
                am = re.search(r'@(riverpod|Riverpod\s*\(([^()]*)\))\s*(?:[A-Za-z_$][\w$<>?,\s]*)?$', ann)
                if am and not (am.group(2) and re.search(r'keepAlive\s*:\s*true', am.group(2))):
                    return ('lifetime', 'built by an auto-disposed @riverpod provider (%s): it is closed and reopened '
                                        'whenever nothing watches it. Use @Riverpod(keepAlive: true) and close it in '
                                        'ref.onDispose.' % f.name)
        cls = df.enclosing_class(pos)
        if cls:
            ann = m[max(0, cls[4] - 200):cls[4]]
            am = re.search(r'@(riverpod|Riverpod\s*\(([^()]*)\))\s*$', ann)
            if am and not (am.group(2) and re.search(r'keepAlive\s*:\s*true', am.group(2))):
                return ('lifetime', 'built by an auto-disposed @riverpod notifier (%s). Use '
                                    '@Riverpod(keepAlive: true).' % cls[0])
        if df.layer == 'app' or df.role == 'di' or re.search(r'(^|/)main[^/]*\.dart$', df.rel):
            return None
        if not fs:
            return None                     # top-level or field initializer: one instance per holder
        if any(f.name and cls and f.name == cls[0] for f in fs):
            return None                     # constructor of the holder
        if any(f.name in ('main', 'callbackDispatcher') or
               re.search(r"@pragma\s*\(\s*['\"]vm:entry-point", m[max(0, f.start - 120):f.start])
               for f in fs if f.name):
            return None                     # a background isolate needs its own connection
        for f in fs:
            if f.name and re.search(r'(?i)isolate|background|worker', f.name):
                return None
            if f.name and re.match(r'^_?(?:init\w*|initialize\w*|open\w*|setup\w*|setUp\w*|bootstrap\w*|connect\w*|'
                                   r'create\w*|build\w*Database|restore\w*|reopen\w*)$', f.name) and f.name != 'initState':
                return None             # an explicit open/init step, called once by its owner
            if f.name and re.search(r'\bstatic\s+(?:Future\s*<[^;{]*>|[\w$<>?,\s]+?)?\s*$',
                                    m[max(0, f.start - 80):f.start]):
                return None             # a static factory
        before = m[max(0, pos - 80):pos]
        if re.search(r'\?\?=\s*(?:await\s+)?$', before):
            return None                     # memoised
        if re.search(r'(?:\b_[\w$]*|\bthis\s*\.\s*[\w$]+|\.\s*state|\b[A-Za-z_$][\w$]*\s*\.\s*[\w$]+)\s*=\s*(?:await\s+)?$',
                     before):
            return None                     # stored in a field / provider state (re-open)
        top = [f for f in fs if f.name and not df.enclosing_callables(f.start)]
        outer = fs[-1]
        if not cls and outer.name and outer is fs[0] and re.search(r'(?:\breturn\s+|=>\s*)(?:await\s+)?$', before):
            return None                     # a top-level factory function
        for cname, cpo in calls:
            if cname in ('Provider', 'FutureProvider', 'StateProvider', 'StreamProvider', 'NotifierProvider',
                         'AsyncNotifierProvider', 'RepositoryProvider', 'registerLazySingleton', 'registerSingleton',
                         'registerSingletonAsync', 'lazyPut', 'put', 'putAsync', 'MultiProvider',
                         'MultiRepositoryProvider', 'ProviderScope', 'overrideWithValue', 'overrideWith'):
                return None
        if not cls and top and not df.enclosing_class(outer.start):
            ann = m[max(0, outer.start - 200):outer.start]
            if re.search(r'@Riverpod\s*\([^()]*keepAlive\s*:\s*true', ann):
                return None
        where = fs[0].name or (fs[-1].name if fs[-1].name else 'a closure')
        return ('per-use', 'created inside %s()%s, so each call opens another connection to the same file. '
                           'Create the database once and inject it.' % (
                               where, ' of %s' % cls[0] if cls else ''))

    # PERSIST-007 ---------------------------------------------------------
    WRITE_RES = (
        re.compile(r'\binto\s*\([^;]*?\)\s*\.\s*(insert\w*)\s*\('),
        re.compile(r'\.\s*(insertOne|insertOnConflictUpdate|insertReturning\w*|deleteOne|replace)\s*\('),
        re.compile(r'\b(update)\s*\(\s*[\w$.]+\s*\)\s*(?:\.\.\s*where\s*\([^;]*?\))?\)?\s*\.\s*(?:write|replace)\s*\('),
        re.compile(r'\b(delete)\s*\(\s*[\w$.]+\s*\)\s*(?:\.\.\s*where\s*\([^;]*?\))?\)?\s*\.\s*go\s*\('),
        re.compile(r'\.\s*(rawInsert|rawUpdate|rawDelete)\s*\('),
    )
    SQFLITE_WRITE = re.compile(r'([\w$]+)\s*[!?]?\s*\.\s*(insert|update|delete)\s*\(\s*(?:[\'"]|[A-Za-z_$][\w$.]*\s*,)')
    TXN_CALLS = ('transaction', 'batch', 'writeTxn', 'writeTxnSync', 'runInTransaction', 'write', 'runInTransactionAsync',
                 'exclusively')
    MIGRATION_CTX = re.compile(r'^(?:onCreate|onUpgrade|onDowngrade|onConfigure|beforeOpen|from\d+To\d+|migration|'
                               r'stepByStep|migrationSteps)$')

    def check_loops(self, df):
        sqf = bool(df.imports & {'sqflite', 'sqflite_common', 'sqflite_common_ffi', 'sqflite_sqlcipher'})
        drift = 'drift' in df.imports or bool(set(self.drift_dbs) & set(re.findall(r'\b[A-Z]\w*', df.masked)))
        if not (sqf or drift):
            return
        m = df.masked
        loops = []
        for lm in re.finditer(r'(?<![\w$.])(?:await\s+)?for\s*\(', m):
            po = lm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            k = pc + 1 + len(m[pc + 1:pc + 40]) - len(m[pc + 1:pc + 40].lstrip())
            if k < len(m) and m[k] == '{':
                be = df.braces.get(k)
                if be is None:
                    continue
                loops.append((lm.start(), k, be))
            else:
                loops.append((lm.start(), k, expr_end(m, k)))
        for lm in re.finditer(r'\.\s*forEach\s*\(', m):
            po = lm.end() - 1
            pc = df.parens.get(po)
            if pc is not None:
                loops.append((lm.start(), po, pc))
        reported = []
        for ls, bs, be in loops:
            if any(r[0] <= ls < r[1] for r in reported):
                continue
            body = m[bs:be]
            hit = None
            for rx in self.WRITE_RES:
                wm = rx.search(body)
                if wm and (drift or rx is self.WRITE_RES[4]):
                    hit = bs + wm.start()
                    break
            if hit is None and sqf:
                for wm in self.SQFLITE_WRITE.finditer(body):
                    if re.search(r'(?i)batch|txn|transaction', wm.group(1)):
                        continue
                    if re.search(r'(?i)^(db|_db|database|_database|\w*[Dd]b|\w*[Dd]atabase|executor|_executor)$',
                                 wm.group(1)):
                        hit = bs + wm.start()
                        break
            if hit is None:
                continue
            if not re.search(r'\bawait\b', m[ls:hit + 200]) and '.forEach' not in m[ls:ls + 12]:
                continue
            if self.in_transaction(df, ls):
                continue
            self.stats['loops_with_writes'] += 1
            reported.append((ls, be))
            self.add(df, 'PERSIST-007', hit, df.line_text(hit),
                     note='the loop at line %d awaits one write per item. Wrap the loop in db.transaction(() async '
                          '{ ... }) (drift/sqflite), or collect the rows and use batch((b) => b.insertAll(...)) / '
                          'db.batch() ... commit(noResult: true).' % df.line_of(ls))

    def in_transaction(self, df, pos):
        for cname, cpo in df.enclosing_calls(pos):
            if cname in self.TXN_CALLS:
                return True
        m = df.masked
        for f in df.enclosing_callables(pos):
            if f.name and (self.MIGRATION_CTX.match(f.name) or re.search(r'(?i)migrat|upgrade', f.name)):
                return True
            lab = re.search(r'([A-Za-z_]\w*)\s*:\s*(?:\([^()]*\)\s*)?$', m[max(0, f.ps - 60):f.ps + 1])
            if lab and self.MIGRATION_CTX.match(lab.group(1)):
                return True
        return False

    # PERSIST-009 ---------------------------------------------------------
    def project_encrypts_db(self):
        if set(self.deps) & set(CIPHER_PKGS):
            return True
        for df in self.files:
            if re.search(r'(?i)pragma\s+(?:key|rekey|cipher)', df.raw) or 'SqlCipher' in df.code:
                return True
        return False

    def check_sensitive(self, df):
        m = df.masked
        if not hasattr(self, '_db_enc'):
            self._db_enc = self.project_encrypts_db()
            self._hive_cipher_any = any('encryptionCipher' in f.masked for f in self.files)
        for bm in re.finditer(r'(?<![\w$])(?:Hive|hive)\s*\.\s*(openBox|openLazyBox)\s*(?:<\s*([\w$]+)[^()]*>)?\s*\(', m):
            po = bm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            args = split_top(m, po + 1, pc)
            if not args or any(re.match(r'\s*encryptionCipher\s*:', m[a:b]) for a, b in args):
                continue
            name = df.code[args[0][0]:args[0][1]].strip()
            lvl, tok = sensitive_level(name + ' ' + (bm.group(2) or ''))
            if not lvl:
                continue
            self.add(df, 'PERSIST-009', bm.start(), df.line_text(bm.start()), severity=lvl,
                     note='box %s (%s data) is opened without encryptionCipher. Open it with encryptionCipher: '
                          'HiveAesCipher(key), where the 32-byte key is generated once and kept in '
                          'flutter_secure_storage.' % (name, tok))
        if self._db_enc:
            return
        for name, o, c, header, hs in df.classes:
            if not re.search(r'\bextends\s+Table\b', header):
                continue
            lvl, tok = sensitive_level(name)
            if lvl:
                self.add(df, 'PERSIST-009', hs, df.line_text(hs), severity=lvl,
                         note='drift table %s (%s data) lives in an unencrypted SQLite file. Encrypt the database '
                              '(sqlcipher_flutter_libs or sqlite3mc with PRAGMA key, key in flutter_secure_storage), '
                              'or keep this data on the server.' % (name, tok))
        for dm in re.finditer(r'(?<![\w$])(?:driftDatabase|openDatabase|NativeDatabase(?:\s*\.\s*createInBackground)?)'
                              r'\s*\(', m):
            po = dm.end() - 1
            pc = df.parens.get(po)
            if pc is None:
                continue
            for r in df.top_strings(po, pc):
                lit = df.raw[r['cs']:r['ce']]
                if not re.search(r'\.(db|sqlite3?)$', lit) and not re.search(r'name\s*:\s*$', m[max(0, r['s'] - 12):r['s']]):
                    continue
                lvl, tok = sensitive_level(lit)
                if lvl:
                    self.add(df, 'PERSIST-009', dm.start(), df.line_text(dm.start()), severity=lvl,
                             note='database %r (%s data) is opened without encryption at rest. Use SQLCipher '
                                  '(sqflite_sqlcipher / sqlcipher_flutter_libs) with the key in '
                                  'flutter_secure_storage.' % (lit, tok))
                    break
        if self._hive_cipher_any:
            return
        for hm in re.finditer(r'@HiveType\s*\(', m):
            cls = None
            for c in df.classes:
                if c[4] > hm.start():
                    cls = c
                    break
            if cls:
                lvl, tok = sensitive_level(cls[0])
                if lvl:
                    self.add(df, 'PERSIST-009', cls[4], df.line_text(cls[4]), severity=lvl,
                             note='Hive type %s (%s data), and no box in the project uses encryptionCipher. Open its '
                                  'box with encryptionCipher: HiveAesCipher(key), key in flutter_secure_storage.'
                                  % (cls[0], tok))


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
    sys.stderr.write('check_persistence.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_persistence.py <project-root> [--json] [--files <list>] '
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

    files = []
    skipped = 0
    for rel in rels:
        try:
            df = DartFile(root, rel)
        except OSError:
            continue
        if GENERATED_HEADER.search(df.raw[:400]):
            continue
        a = arch_files.get(rel)
        if a:
            df.layer, df.role = a.get('layer') or 'other', a.get('role') or 'other'
        else:
            df.layer, df.role = classify_fallback(rel)
        if df.role == 'barrel':
            skipped += 1
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
    stats['skipped_barrels'] = skipped
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
    out = ['== PERSISTENCE',
           '  profile: %s%s (%s)' % (profile, ' + clean' if clean else '', psource),
           '  classification: %s' % classification,
           '  scanned: %d files; stores: %s; %d SQL statements, %d drift database%s, %d sqflite open%s, '
           '%d Hive type%s' % (len(files), ', '.join(stats['stores']) or 'none declared', stats['sql_calls'],
                               stats['drift_databases'], '' if stats['drift_databases'] == 1 else 's',
                               stats['sqflite_opens'], '' if stats['sqflite_opens'] == 1 else 's',
                               stats['hive_types'], '' if stats['hive_types'] == 1 else 's')]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no persistence findings')
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
