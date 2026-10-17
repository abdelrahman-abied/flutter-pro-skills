#!/usr/bin/env python3
"""arch_check.py: static architecture checker for Dart / Flutter projects.

Read-only, stdlib only (python3 >= 3.8). It builds an import graph over lib/,
classifies every file into a layer, role and feature, detects the
architecture profile, then applies the ARCH-0xx import-graph rules and the
ARCH-1xx code-pattern rules from docs/CONTRACTS.md (sections 5 to 7).

Usage:
  python3 -I arch_check.py <project-root> [--json] [--files <file-with-relative-paths>]
                           [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
                           [--max <n>]
                           [--baseline <file>] [--write-baseline <file>]
                           [--ci] [--fail-on high|medium|low]

Exit codes: 0 = report produced (findings never fail the run), 2 = usage or
environment error (for example, no pubspec.yaml). With --ci: 1 when a reported
(new, if --baseline is given) violation is at or above --fail-on (default high).

Baselines (CONTRACTS section 11): --write-baseline stores the current
violations as {"schema": "flutter-pro-skills/arch-baseline@1", "entries":
[{"id", "file", "key"}]}, where key is the evidence normalised without line
numbers, one entry per occurrence. --baseline then reports only the
occurrences beyond the stored count for each (id, file, key).

Suppressions in the analysed code:
  // arch-ignore: ARCH-005 <reason>        on the offending line or the line above it
  // arch-ignore-file: ARCH-005 <reason>   anywhere in the file
"""
import argparse
import bisect
import json
import os
import re
import sys
from collections import defaultdict

SCHEMA = 'flutter-pro-skills/arch-profile@1'
BASELINE_SCHEMA = 'flutter-pro-skills/arch-baseline@1'
PROFILES = ('mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')

# --------------------------------------------------------------------------
# Rule catalog (CONTRACTS section 6): id -> (name, default severity, message)
# --------------------------------------------------------------------------
RULES = {
    'ARCH-001': ('domain-depends-on-data', 'high',
                 'Domain imports the data layer; depend on a domain contract and bind the implementation in the composition root.'),
    'ARCH-002': ('domain-depends-on-presentation', 'high',
                 'Domain imports presentation; the domain must not know about the UI.'),
    'ARCH-003': ('domain-depends-on-framework', 'medium',
                 'Domain imports Flutter, an I/O package or a UI state-management package; keep the domain pure Dart.'),
    'ARCH-004': ('data-depends-on-presentation', 'high',
                 'Data imports presentation; data must not know about the UI.'),
    'ARCH-005': ('ui-depends-on-data-source', 'high',
                 'A view imports a transport/data-source; route it through the notifier/view model.'),
    'ARCH-006': ('ui-depends-on-dto', 'medium',
                 'Presentation imports a DTO; map DTOs to entities/models in the data layer.'),
    'ARCH-007': ('logic-depends-on-concrete-data', 'medium',
                 'Logic depends on a concrete source/service/repository implementation or an I/O package; depend on a repository contract.'),
    'ARCH-008': ('view-depends-on-repository', 'medium',
                 'A view imports a repository or a use case; go through the notifier/view model/bloc.'),
    'ARCH-009': ('logic-depends-on-flutter-ui', 'medium',
                 'Logic imports Flutter UI libraries; keep it testable without widgets (foundation.dart is fine).'),
    'ARCH-010': ('sibling-logic-dependency', 'medium',
                 'Logic depends on another logic class; share a repository/stream or compose in the UI instead.'),
    'ARCH-011': ('repository-depends-on-repository', 'medium',
                 'A repository depends on another repository; compose them in a use case or service.'),
    'ARCH-012': ('mvn-notifier-bypasses-usecase', 'medium',
                 'An MVN notifier reaches the repository/source directly; call a use case.'),
    'ARCH-013': ('core-depends-on-feature', 'medium',
                 'Core/shared code imports a feature; move the shared piece into core or invert the dependency.'),
    'ARCH-014': ('cross-feature-internal-import', 'low',
                 "A feature imports another feature's data/presentation internals; depend on its domain or a shared API."),
    'ARCH-015': ('feature-cycle', 'medium',
                 'Features import each other in a cycle; extract the shared part or invert one edge.'),
    'ARCH-101': ('io-in-widget', 'high',
                 'A widget does I/O; move it behind a repository/source and the notifier/view model.'),
    'ARCH-102': ('context-in-logic', 'medium',
                 'Logic uses BuildContext, navigation or dialogs; expose state/events and let the view react.'),
    'ARCH-103': ('god-file', 'medium',
                 'File is too large for its role; split it by responsibility.'),
    'ARCH-104': ('service-locator-in-ui', 'low',
                 'A widget reaches into a service locator; inject through the state-management layer or the constructor.'),
    'ARCH-105': ('global-mutable-state', 'medium',
                 'Mutable global/static state; move it into a provider/service with an owner and a lifecycle.'),
    'ARCH-106': ('mutable-state-class', 'medium',
                 'A state class has a mutable field; make state immutable and copy on change.'),
    'ARCH-107': ('repository-leaks-transport', 'medium',
                 'A repository exposes transport types; return domain types.'),
    'ARCH-108': ('concrete-repository-only', 'low',
                 'Concrete repository with no abstraction; add a contract so logic depends on it and tests can fake it.'),
    'ARCH-109': ('ephemeral-state-in-provider', 'low',
                 'An ephemeral UI controller is created in logic/a provider; own it in a State and dispose it there.'),
    'ARCH-110': ('provider-init-from-widget', 'low',
                 "initState() drives a provider; initialise in the provider's build() instead."),
    'ARCH-111': ('event-flag-in-state', 'low',
                 'A one-time event is modelled as a persistent bool in state; use ref.listen / a side-effect stream.'),
    'ARCH-112': ('mvn-forbidden-naming', 'low',
                 'MVN forbids ViewModel/VM/Controller naming; use a *Notifier under notifier/.'),
    'ARCH-113': ('getx-in-build', 'low',
                 'Get.put/Get.find inside build(); bind dependencies once (Bindings), not on every rebuild.'),
}
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

IO_PACKAGES = {
    'dio', 'http', 'retrofit', 'chopper', 'graphql', 'graphql_flutter', 'sqflite', 'drift',
    'hive', 'hive_flutter', 'isar', 'objectbox', 'shared_preferences', 'flutter_secure_storage',
    'cloud_firestore', 'firebase_database', 'firebase_storage', 'firebase_auth',
    'supabase_flutter', 'supabase', 'web_socket_channel', 'grpc', 'path_provider',
    'get_storage', 'hive_ce', 'hive_ce_flutter', 'sembast', 'realm', 'floor', 'isar_community',
}
# Symbols of an I/O package that are not transport/persistence by themselves (A4/A5).
IO_NEUTRAL_SYMBOLS = {'CancelToken'}
RIVERPOD_DEPS = ('flutter_riverpod', 'hooks_riverpod', 'riverpod', 'riverpod_annotation')
WIDGET_BASES = ('StatelessWidget', 'StatefulWidget', 'ConsumerWidget', 'ConsumerStatefulWidget',
                'HookWidget', 'HookConsumerWidget', 'StatefulHookWidget', 'StatefulHookConsumerWidget',
                'InheritedWidget', 'InheritedNotifier', 'InheritedModel', 'InheritedTheme')

GENERATED_SUFFIXES = ('.g.dart', '.freezed.dart', '.gr.dart', '.mocks.dart', '.config.dart',
                      '.pb.dart', '.pbenum.dart', '.pbjson.dart', '.pbserver.dart', '.chopper.dart',
                      '.gen.dart')
GENERATED_HEADER_RE = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|'
                                 r'^[ \t]*(?://+|/?\*+)[^\n]*(?:AUTO[- ]?GENERATED|DO NOT EDIT|\bGenerated by\b(?![^\n]*\bwhen running\b))',
                                 re.M | re.I)

# --------------------------------------------------------------------------
# Lexing: find comment and string spans, then blank them out
# --------------------------------------------------------------------------
_CODE_TOK = re.compile(r"//|/\*|'|\"|\{|\}")
_STR_RES = {}


def _str_re(q, triple, raw):
    key = (q, triple, raw)
    if key not in _STR_RES:
        delim = re.escape(q * 3 if triple else q)
        if raw:
            pat = delim if triple else delim + r'|\n'
        else:
            pat = r'\\.|\$\{|' + delim + ('' if triple else r'|\n')
        _STR_RES[key] = re.compile(pat, re.S)
    return _STR_RES[key]


def _is_ident(ch):
    return ch.isalnum() or ch in '_$'


def _scan_code(src, i, comments, strings, interp):
    """Scan code from i; in interpolation mode return just past the closing '}'."""
    n = len(src)
    depth = 0
    while i < n:
        m = _CODE_TOK.search(src, i)
        if not m:
            return n
        t, p = m.group(), m.start()
        if t == '//':
            j = src.find('\n', p)
            j = n if j < 0 else j
            comments.append((p, j))
            i = j
        elif t == '/*':
            lvl, k = 1, p + 2
            while lvl and k < n:
                a, b = src.find('/*', k), src.find('*/', k)
                if b < 0:
                    k = n
                    break
                if 0 <= a < b:
                    lvl, k = lvl + 1, a + 2
                else:
                    lvl, k = lvl - 1, b + 2
            comments.append((p, k))
            i = k
        elif t in ('"', "'"):
            raw = p > 0 and src[p - 1] in 'rR' and (p < 2 or not _is_ident(src[p - 2]))
            triple = src.startswith(t * 3, p)
            i = _scan_string(src, p, t, triple, raw, comments, strings)
        elif t == '{':
            depth += 1
            i = p + 1
        else:  # '}'
            if interp and depth == 0:
                return p + 1
            depth = max(0, depth - 1)
            i = p + 1
    return n


def _scan_string(src, p, q, triple, raw, comments, strings):
    start = p + (3 if triple else 1)
    rx = _str_re(q, triple, raw)
    i = start
    n = len(src)
    while i < n:
        m = rx.search(src, i)
        if not m:
            strings.append((start, n))
            return n
        t = m.group()
        if t == '\n':  # unterminated single-line string
            strings.append((start, m.start()))
            return m.start()
        if t.startswith('\\'):
            i = m.end()
        elif t == '${':
            i = _scan_code(src, m.end(), comments, strings, True)
        else:
            strings.append((start, m.start()))
            return m.end()
    strings.append((start, n))
    return n


_NONNL = re.compile(r'[^\n]')


def _blank(src, spans):
    if not spans:
        return src
    spans = sorted(spans)
    out, last = [], 0
    for a, b in spans:
        if b <= last:
            continue
        a = max(a, last)
        out.append(src[last:a])
        out.append(_NONNL.sub(' ', src[a:b]))
        last = b
    out.append(src[last:])
    return ''.join(out)


def lex(src):
    """Return (code, skel): code has comments blanked; skel also blanks string contents."""
    comments, strings = [], []
    _scan_code(src, 0, comments, strings, False)
    code = _blank(src, comments)
    skel = _blank(src, comments + strings)
    return code, skel


# --------------------------------------------------------------------------
# Lightweight declaration parsing on the skeleton
# --------------------------------------------------------------------------
_ANNOT_RE = re.compile(r'@[A-Za-z_][\w.]*')


def _skip_balanced(s, i, op, cl):
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == op:
            depth += 1
        elif c == cl:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def strip_annotations(h):
    out, i = [], 0
    while True:
        m = _ANNOT_RE.search(h, i)
        if not m:
            out.append(h[i:])
            break
        out.append(h[i:m.start()])
        j = m.end()
        if j < len(h) and h[j] == '(':
            j = _skip_balanced(h, j, '(', ')')
        i = j
    return ''.join(out)


_MOD_RE = re.compile(r'(static|late|final|const|var|external|covariant|abstract)\b\s*')
_IDENT_RE = re.compile(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*')
_NOT_DECL_RE = re.compile(r'(get|set|operator|factory|typedef|import|export|part|library|class|enum|'
                          r'mixin|extension|return|sealed|base|interface)\b')


def _take_type(h):
    """Parse a Dart type at the start of h; return (type, rest) or (None, h)."""
    i = 0
    n = len(h)
    if h.startswith('('):
        i = _skip_balanced(h, 0, '(', ')')
    else:
        m = _IDENT_RE.match(h)
        if not m:
            return None, h
        i = m.end()
        if i < n and h[i] == '<':
            i = _skip_balanced(h, i, '<', '>')
    if i < n and h[i] == '?':
        i += 1
    while True:  # function types: `void Function(int)?`
        m = re.match(r'\s*Function\b\s*', h[i:])
        if not m:
            break
        j = i + m.end()
        if j < n and h[j] == '<':
            j = _skip_balanced(h, j, '<', '>')
            while j < n and h[j].isspace():
                j += 1
        if j < n and h[j] == '(':
            j = _skip_balanced(h, j, '(', ')')
        else:
            break
        if j < n and h[j] == '?':
            j += 1
        i = j
    return h[:i], h[i:]


_NAME_ONLY_RE = re.compile(r'\s*([A-Za-z_$][\w$]*)\s*(?:,.*)?$', re.S)


def parse_var(header):
    """Parse a variable/field declaration header (text before '=' or ';').

    Returns (mods, type, name) or None when the header is not a variable.
    """
    h = strip_annotations(header).strip()
    if not h:
        return None
    mods = set()
    while True:
        m = _MOD_RE.match(h)
        if not m:
            break
        mods.add(m.group(1))
        h = h[m.end():]
    if not h or _NOT_DECL_RE.match(h):
        return None
    if 'var' not in mods:
        typ, rest = _take_type(h)
        if typ is not None and rest[:1].isspace():
            m = _NAME_ONLY_RE.match(rest)
            if m:
                return mods, typ, m.group(1)
    if mods & {'var', 'final', 'const', 'late'}:
        m = _NAME_ONLY_RE.match(h)
        if m:
            return mods, '', m.group(1)
    return None


def first_paren_outside_angles(h):
    depth = 0
    for i, c in enumerate(h):
        if c == '<':
            depth += 1
        elif c == '>':
            depth = max(0, depth - 1)
        elif c == '(' and depth == 0:
            return i
    return -1


def parse_method(header):
    """Return (return_type, name, is_getter) for a method/getter header, else None."""
    h = strip_annotations(header).strip()
    while True:
        m = re.match(r'(static|external|abstract|covariant)\b\s*', h)
        if not m:
            break
        h = h[m.end():]
    m = re.match(r'(.*?)\bget\s+([A-Za-z_$][\w$]*)\s*$', h, re.S)
    if m:
        return m.group(1).strip(), m.group(2), True
    p = first_paren_outside_angles(h)
    if p < 0:
        return None
    before = h[:p].rstrip()
    m = re.search(r'([A-Za-z_$][\w$]*)\s*(<[^()]*>)?$', before)
    if not m:
        return None
    ret = before[:m.start()].strip()
    name = m.group(1)
    if ret.endswith('.') or name in ('if', 'for', 'while', 'switch', 'catch'):
        return None
    if re.match(r'(factory|const|new|set|operator)\b', ret):
        return None
    return ret, name, False


_CLASS_HDR_RE = re.compile(
    r'(?:^|\s)((?:(?:abstract|sealed|base|final|interface|mixin)\s+)*)(class|mixin|enum|extension(?:\s+type)?)\b'
    r'(?:\s+(?:const\s+)?([A-Za-z_$][\w$]*))?')


def class_info(header):
    h = strip_annotations(header)
    m = _CLASS_HDR_RE.search(h)
    if not m:
        return None
    if '(' in h[:m.start()]:
        return None
    mods = set(m.group(1).split())
    kind = m.group(2).split()[0]
    name = m.group(3) or ''
    if kind == 'extension' and name == 'on':
        name = ''
    rest = h[m.end():]
    ext = re.search(r'\bextends\s+([\w$.]+)\s*(<)?', rest)
    impl = re.search(r'\b(?:implements|with|on)\s+(.*)$', rest, re.S)
    supers = []
    if ext:
        supers.append(ext.group(1))
    if impl:
        supers += re.findall(r'[A-Za-z_$][\w$]*', re.sub(r'<[^<>]*>', '', impl.group(1)))
    return {
        'name': name, 'kind': kind, 'mods': mods, 'header': h,
        'extends': ext.group(1) if ext else '',
        'extends_generic': bool(ext and ext.group(2)),
        'supers': supers,
    }


_STRUCT_TOK = re.compile(r'=>|==|!=|<=|>=|[{}()\[\];=]')


class Struct:
    __slots__ = ('classes', 'members', 'funcs')

    def __init__(self):
        self.classes, self.members, self.funcs = [], [], []


def scan_structure(s):
    """Very small structural pass over the skeleton.

    classes: dicts with name/kind/mods/extends/supers/start/body_start/body_end
    members: (cls, header, offset, terminator) for top-level and class-member statements
    funcs:   (cls, name, header, offset, body_start, body_end)
    """
    st = Struct()
    top = {'kind': 'top', 'cls': None, 'paren': 0, 'start': 0, 'hdone': False, 'arrow': None}
    frames = [top]
    for m in _STRUCT_TOK.finditer(s):
        t, pos = m.group(), m.start()
        f = frames[-1]
        if t in ('(', '['):
            f['paren'] += 1
            continue
        if t in (')', ']'):
            f['paren'] = max(0, f['paren'] - 1)
            continue
        if t in ('==', '!=', '<=', '>='):
            continue
        member_level = f['kind'] in ('top', 'class') and f['paren'] == 0
        if member_level and t != '}':
            if not f['hdone']:
                header = s[f['start']:pos]
                f['hdone'] = True
                st.members.append((f['cls'], header, f['start'], t))
                if t == '{':
                    ci = class_info(header)
                    if ci is not None:
                        ci['raw_header'] = header
                        ci['start'] = f['start']
                        ci['body_start'] = pos + 1
                        ci['body_end'] = len(s)
                        st.classes.append(ci)
                        frames.append({'kind': 'class', 'cls': ci, 'paren': 0, 'start': pos + 1,
                                       'hdone': False, 'arrow': None, 'body': True})
                    else:
                        frames.append({'kind': 'other', 'paren': 0, 'body': True,
                                       'func': (f['cls'], header, f['start'], pos + 1)})
                elif t == '=>':
                    f['arrow'] = (f['cls'], header, f['start'], pos + 2)
                elif t == ';':
                    f['start'], f['hdone'] = pos + 1, False
                continue
            if t == ';':
                if f['arrow']:
                    cls, header, off, bstart = f['arrow']
                    pm = parse_method(header)
                    if pm:
                        st.funcs.append((cls, pm[1], header, off, bstart, pos))
                f['start'], f['hdone'], f['arrow'] = pos + 1, False, None
            elif t == '{':
                frames.append({'kind': 'other', 'paren': 0, 'body': False, 'func': None})
            continue
        if t == '{':
            frames.append({'kind': 'other', 'paren': 0, 'body': False, 'func': None})
            continue
        if t == '}':
            if len(frames) == 1:
                continue
            fr = frames.pop()
            if fr['kind'] == 'class':
                fr['cls']['body_end'] = pos
            elif fr.get('func'):
                cls, header, off, bstart = fr['func']
                pm = parse_method(header)
                if pm:
                    st.funcs.append((cls, pm[1], header, off, bstart, pos))
            parent = frames[-1]
            if fr.get('body') and parent['kind'] in ('top', 'class'):
                parent['start'], parent['hdone'], parent['arrow'] = pos + 1, False, None
            continue
    return st


# --------------------------------------------------------------------------
# pubspec.yaml (no YAML library)
# --------------------------------------------------------------------------
def parse_pubspec(path):
    name, deps = None, set()
    section, dep_indent = None, None
    with open(path, encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            line = re.sub(r'(^|\s)#.*$', '', raw.rstrip('\n'))
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0:
                m = re.match(r'([A-Za-z_][\w-]*)\s*:\s*(.*)$', line)
                section, dep_indent = None, None
                if not m:
                    continue
                key, val = m.group(1), m.group(2).strip()
                if key == 'name' and val:
                    name = val.strip('\'"')
                elif key in ('dependencies', 'dev_dependencies'):
                    section = key
            elif section:
                if dep_indent is None:
                    dep_indent = indent
                if indent == dep_indent:
                    m = re.match(r'\s*["\']?([A-Za-z_]\w*)["\']?\s*:', line)
                    if m:
                        deps.add(m.group(1))
    return name, deps


def parse_path_deps(path):
    """Names of `path:` dependencies (local packages such as packages/*_repository)."""
    out, cur, section = [], None, False
    with open(path, encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            line = re.sub(r'(^|\s)#.*$', '', raw.rstrip('\n'))
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0:
                section = bool(re.match(r'(?:dependencies|dev_dependencies|dependency_overrides)\s*:', line))
                cur = None
                continue
            if not section:
                continue
            m = re.match(r'\s*["\']?([A-Za-z_]\w*)["\']?\s*:\s*$', line)
            if m and indent <= 4:
                cur = m.group(1)
                continue
            if cur and re.match(r'\s*path\s*:', line) and cur not in out:
                out.append(cur)
    return out


# --------------------------------------------------------------------------
# Files, imports and classification
# --------------------------------------------------------------------------
class DartFile:
    __slots__ = ('rel', 'segs', 'base', 'stem', 'raw', 'lines', 'code', 'skel', 'line_starts',
                 'imports', 'parts', 'part_of', 'layer', 'role', 'feature', 'struct', 'is_core_area',
                 'ignore_file', 'ignore_lines', 'widget_ranges', 'other_class_ranges', 'prim', 'toks',
                 'role_from_content', 'logic_ranges')

    def line_of(self, off):
        return bisect.bisect_right(self.line_starts, off)

    def src_line(self, n):
        if 1 <= n <= len(self.lines):
            return self.lines[n - 1].strip()
        return ''


_DIRECTIVE_RE = re.compile(r'(?m)^[ \t]*(import|export|part)\b(?:\s+of\b)?\s*(?=r?[\'"])([^;]*);')
_PARTOF_RE = re.compile(r'(?m)^[ \t]*part\s+of\b')


def _directive_uris(text):
    """String literals of an import/export directive that are not inside parentheses."""
    uris, depth, i, n = [], 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth = max(0, depth - 1)
        elif c in '\'"':
            j = text.find(c, i + 1)
            if j < 0:
                break
            if depth == 0:
                uris.append(text[i + 1:j])
            i = j
        i += 1
    return uris


def parse_imports(f, package):
    f.imports, f.parts, f.part_of = [], [], bool(_PARTOF_RE.search(f.skel))
    for m in _DIRECTIVE_RE.finditer(f.code):
        kind = m.group(1)
        if f.skel[m.start(1):m.end(1)] != kind:
            continue  # the keyword sits inside a string literal
        line = f.line_of(m.start(1))
        text = m.group(2)
        evidence = re.sub(r'\s+', ' ', m.group(0).strip())
        uris = _directive_uris(text)
        if kind == 'part':
            if not re.match(r'\s*part\s+of\b', m.group(0)) and uris:
                f.parts.append(_resolve(f.rel, uris[0], package)[0])
            continue
        for uri in uris:
            target, pkg, pkg_path = _resolve(f.rel, uri, package)
            f.imports.append({'uri': uri, 'line': line, 'kind': kind, 'target': target,
                              'pkg': pkg, 'pkg_path': pkg_path, 'evidence': evidence})


def _resolve(rel, uri, package):
    """Return (target_rel_or_None, external_pkg_or_None, pkg_path)."""
    if uri.startswith('dart:'):
        return None, 'dart:' + uri[5:].split('/')[0], uri
    if uri.startswith('package:'):
        body = uri[8:]
        pkg, _, path = body.partition('/')
        if package and pkg == package:
            return 'lib/' + path, None, body
        return None, pkg, body
    if re.match(r'^[a-z]+:', uri):
        return None, None, uri
    joined = os.path.normpath(os.path.join(os.path.dirname(rel), uri)).replace(os.sep, '/')
    return joined, None, uri


LAYER_SEGS = (
    ('domain', {'domain'}),
    ('data', {'data'}),
    ('presentation', {'presentation', 'ui', 'view', 'views', 'screens', 'screen', 'pages', 'page',
                      'widgets', 'widget'}),
    ('app', {'di', 'injection', 'router', 'routes', 'routing', 'bindings', 'binding'}),
    ('core', {'core', 'shared', 'common', 'utils', 'util'}),
)
LAYER_FIRST_DATA = {'models', 'model', 'services', 'repositories', 'api', 'datasources'}
COMPOSITION_SEGS = {'di', 'injection', 'router', 'routes', 'routing', 'bindings', 'binding'}
COMPOSITION_FILES = ('app', 'bootstrap')  # lib/app.dart, lib/bootstrap.dart (bloclibrary, VGV)
FEATURE_SEGS = ('features', 'feature', 'modules')
LOGIC_DIRS = {'notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels',
              'bloc', 'blocs', 'cubit', 'cubits', 'controller', 'controllers'}
LOGIC_SUFFIXES = ('_notifier', '_view_model', '_viewmodel', '_bloc', '_cubit', '_controller')
SOURCE_DIRS = {'sources', 'source', 'datasources', 'datasource', 'data_sources', 'data_source',
               'api', 'remote', 'local'}
SOURCE_SUFFIXES = ('_source', '_datasource', '_data_source', '_api', '_client')
REPO_DIRS = {'repositories', 'repository', 'repositories_impl', 'repository_impl', 'repos'}
REPO_IMPL_DIRS = {'repositories_impl', 'repository_impl'}
# bloclibrary feature folders: lib/<feature>/{bloc,cubit,view,widgets,models}
FLAT_FEATURE_MARKERS = {'bloc', 'blocs', 'cubit', 'cubits', 'view', 'views', 'widgets'}
NOT_FEATURE_TOP = {'presentation', 'ui', 'core', 'shared', 'common', 'utils', 'util', 'app', 'data', 'domain',
                   'features', 'feature', 'modules', 'di', 'injection', 'router', 'routes', 'routing', 'config',
                   'l10n', 'generated', 'models', 'model', 'services', 'service', 'repositories', 'api',
                   'datasources', 'screens', 'screen', 'pages', 'page', 'widgets', 'widget', 'view', 'views',
                   'components', 'theme', 'themes', 'helpers', 'constants', 'application', 'infrastructure',
                   'bloc', 'blocs', 'cubit', 'cubits', 'controllers', 'controller', 'providers', 'provider'}
# observability services are cross-cutting (core), not data (A15)
_OBSERVABILITY_RE = re.compile(r'(?:^|_)(?:log|logs|logger|logging|analytics|crash\w*|telemetry|tracking|tracker|'
                               r'sentry|metrics)(?:_|$)')

_ABSTRACT_REPO_RE = re.compile(
    r'\b(?:abstract\s+(?:interface\s+|base\s+)?|interface\s+|sealed\s+)class\s+(\w*Repo(?:sitory)?)\b')
_CONCRETE_REPO_RE = re.compile(r'(?m)^[ \t]*(?:final\s+|base\s+)?class\s+(\w*Repo(?:sitory)?\w*)\b')
_REPO_IMPL_CONTENT_RE = re.compile(r'\bclass\s+\w+Repo(?:sitory)?Impl\b|\bimplements\s+(?:[\w<>,\s]*?,\s*)?\w*Repository\b')
_WIDGET_DECL_RE = re.compile(r'\bextends\s+(?:' + '|'.join(WIDGET_BASES) + r'|State\s*<|ConsumerState\s*<)')
# state holders whose class is presentation logic in every profile (CONTRACTS section 18)
_LOGIC_CONTENT_BASE_RE = re.compile(
    r'^(?:(?:AutoDispose)?(?:Family)?(?:Async|Stream)?Notifier|StateNotifier|ChangeNotifier|ValueNotifier|'
    r'Cubit|Bloc|HydratedCubit|HydratedBloc|ReplayCubit|ReplayBloc|GetxController|FullLifeCycleController|'
    r'SuperController)$')
# Routing glue is composition root, not presentation logic (RouterDelegate with ChangeNotifier, go_router
# refreshListenable adapters such as GoRouterRefreshStream)
_ROUTER_GLUE_SUPERS = {'RouterDelegate', 'RouteInformationParser', 'RouteInformationProvider',
                       'PlatformRouteInformationProvider', 'PopNavigatorRouterDelegateMixin', 'NavigatorObserver',
                       'RouteObserver', 'BackButtonDispatcher'}
_ROUTER_GLUE_NAME_RE = re.compile(r'(?:Refresh(?:Stream|Listenable)|RouterDelegate|RouteInformationParser|'
                                  r'RouteInformationProvider)$')


def is_router_glue(c):
    return bool(set(c['supers']) & _ROUTER_GLUE_SUPERS) or bool(_ROUTER_GLUE_NAME_RE.search(c['name'] or ''))


_DI_CLASS_NAME_RE = re.compile(r'\w(?:Factory|Module|Locator|Injector)$')
_DIRECTIVE_ONLY_RE = re.compile(r'(?m)^[ \t]*(?:library|import|export|part)\b[^;]*;')
_PROVIDER_INIT_RE = re.compile(r'^\s*(?:[A-Za-z_]\w*\.)*(\w*Provider)\b')
_ASYNC_PROVIDER_RE = re.compile(r'^(?:Future|Stream|AsyncNotifier|StreamNotifier|AutoDisposeFuture|'
                                r'AutoDisposeStream|AutoDisposeAsyncNotifier)\w*Provider$')


def prepass(files):
    """Project-wide facts that classification needs (abstract repositories, bloclibrary features)."""
    g = {'flat_features': set(), 'abstract_repos': set(), 'bloc_dirs': set()}
    for f in files.values():
        if len(f.segs) >= 2 and f.segs[1] in FLAT_FEATURE_MARKERS and f.segs[0] not in NOT_FEATURE_TOP:
            g['flat_features'].add(f.segs[0])
        g['abstract_repos'].update(_ABSTRACT_REPO_RE.findall(f.skel))
        if f.stem.endswith(('_bloc', '_cubit')):
            g['bloc_dirs'].add(tuple(f.segs))
    return g


def _initializer(skel, off, header):
    """Text of a top-level `x = <initializer>;` (from after '=' to the closing ';' at depth 0)."""
    i = off + len(header) + 1
    depth, n, j = 0, len(skel), i
    while j < n:
        c = skel[j]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth < 0:
                break
        elif c == ';' and depth == 0:
            break
        j += 1
    return skel[i:j]


def top_level_providers(f):
    """[(name, kind, value_type, init_text)] for top-level providers, plus a flag: True when every top-level
    declaration is a provider (directives aside). kind: 'var' or 'fn'."""
    st = struct_of(f)
    out, only = [], True
    for cls, header, off, term in st.members:
        if cls is not None:
            continue
        h = strip_annotations(header).strip()
        if term == ';' and (not h or re.match(r'(?:library|import|export|part|typedef)\b', h)):
            continue
        if term == '=':
            pv = parse_var(header)
            init = _initializer(f.skel, off, header)
            m = _PROVIDER_INIT_RE.match(init)
            if pv and m:
                tm = re.match(r'\s*(?:[A-Za-z_]\w*\.)*\w*Provider\s*(?:\.\s*\w+\s*)*<\s*([\w.]+)', init)
                out.append((pv[2], m.group(1), tm.group(1) if tm else '', init))
                continue
            if pv and re.match(r'typedef\b', h):
                continue
        elif term in ('{', '=>') and _RIVERPOD_ANNOT_RE.search(header) and not class_info(header):
            pm = parse_method(header)
            if pm:
                out.append((pm[1] + 'Provider', 'fn', pm[0], ''))
                continue
        elif term == '{' and class_info(header) is not None:
            continue  # classes are judged separately
        only = False
    return out, only


def _di_like(f, st):
    """True for a provider-only wiring file, or a *Factory/*Module/*Locator class that only constructs objects."""
    named = [c for c in st.classes if c['name'] and c['kind'] in ('class', 'mixin', 'enum')]
    if any(re.search(r'Repo(?:sitory)?$', c['name']) for c in named):
        return False
    provs, only = top_level_providers(f)
    if not only:
        return False
    if named:
        if not all(c['kind'] == 'class' and _DI_CLASS_NAME_RE.search(c['name']) for c in named):
            return False
        for c in named:
            body = f.skel[c['body_start']:c['body_end']]
            if re.search(r'\b(?:await|if|for|while|switch|try|async)\b', body):
                return False
        return True
    if not provs:
        return False
    for name, kind, vtype, init in provs:
        if kind == 'var' and _ASYNC_PROVIDER_RE.match(_PROVIDER_INIT_RE.match(init).group(1)):
            return False
        if kind == 'fn' and re.match(r'(?:Future|Stream|FutureOr)\b', vtype or ''):
            return False
    return True


def _logic_content(f, st):
    """Classes that make the file presentation logic (ChangeNotifier, classic/codegen notifiers, Cubit/Bloc, GetX)."""
    names = []
    for c in st.classes:
        if c['kind'] == 'class' and c['name'] and re.search(r'(?:Repository|Repo|Source|DataSource|Api|Client)$', c['name']) \
                and not any(_LOGIC_CONTENT_BASE_RE.match(x) for x in c['supers']):
            return []  # a transport/data file that also hosts a small notifier stays a data file
    for c in st.classes:
        if c['kind'] != 'class' or not c['name']:
            continue
        if re.search(r'Repo(?:sitory)?$', c['name']) or c['name'].startswith('Command') or is_router_glue(c):
            continue
        if any(_LOGIC_CONTENT_BASE_RE.match(x) for x in c['supers']) or (
                c['extends'].startswith('_$') and _RIVERPOD_ANNOT_RE.search(c.get('raw_header', ''))):
            names.append(c['name'])
    return names


def classify(f, g=None):
    g = g or {'flat_features': set(), 'abstract_repos': set(), 'bloc_dirs': set()}
    segs = f.segs
    sset = set(segs)
    stem = f.stem
    st = struct_of(f)
    # feature
    f.feature = None
    for i, sg in enumerate(segs):
        if sg in FEATURE_SEGS and i + 1 < len(segs):
            f.feature = segs[i + 1]
            break
    flat_feature = f.feature is None and bool(segs) and segs[0] in g['flat_features']
    if flat_feature:
        f.feature = segs[0]
    # layer: priority order (domain > data > presentation > composition root > core)
    layer = None
    if (not segs and (f.base.startswith('main') or stem in COMPOSITION_FILES)) or segs == ['app'] or \
            segs[:1] == ['config']:
        layer = 'app'  # composition root: lib/main*.dart, lib/app.dart, lib/bootstrap.dart, lib/app/*, lib/config/**
    else:
        for name, names in LAYER_SEGS:
            if sset & names:
                layer = name
                break
    weak_data = layer is None and bool(sset & LAYER_FIRST_DATA)
    flat_models = flat_feature and len(segs) >= 2 and segs[1] in ('models', 'model')
    if flat_models:
        layer, weak_data = 'presentation', False  # P3: a bloclibrary feature's UI models are not data
    # core area (for ARCH-013): a core/shared/common tree outside features/, not a composition root
    f.is_core_area = (f.feature is None and bool(sset & {'core', 'shared', 'common'})
                      and not sset & COMPOSITION_SEGS)

    eff = layer or ('data' if weak_data else None)
    ui_ok = eff not in ('domain', 'data')          # name/folder-based UI roles
    ui_ok_content = layer not in ('domain', 'data')  # content beats the weak layer-first data folders
    data_ok = layer not in ('domain', 'presentation')
    has_abstract_repo = bool(_ABSTRACT_REPO_RE.search(f.skel))
    concrete_repo = _CONCRETE_REPO_RE.findall(f.skel)
    classes = [c for c in st.classes if c['name'] and c['kind'] in ('class', 'mixin')]
    widget_classes = [c for c in classes if is_widget_class(c) or is_state_class(c)]
    only_widgets = bool(classes) and len(widget_classes) == len(classes)
    logic_names = _logic_content(f, st) if not widget_classes else []
    in_repo_folder = bool(sset & REPO_DIRS)
    repo_named = (in_repo_folder or stem.endswith(('_repository', '_repo', '_repository_impl', '_repo_impl'))
                  or '_repository_' in stem)
    from_content = False

    glue = [c for c in classes if is_router_glue(c)]
    if f.imports and not _DIRECTIVE_ONLY_RE.sub('', f.skel).strip():
        role = 'barrel'
    elif glue and not logic_names and not widget_classes and len(glue) == len(classes):
        role = 'other'  # routing glue: composition root (FX-T note)
        if layer not in ('domain', 'data'):
            layer = 'app'
    elif _di_like(f, st):
        role = 'di'
    elif stem.endswith(('_usecase', '_use_case', '_usecases', '_use_cases')) or \
            sset & {'usecases', 'use_cases', 'usecase', 'use_case', 'interactors', 'application'}:
        role = 'usecase'
    elif repo_named or _REPO_IMPL_CONTENT_RE.search(f.skel):
        if layer == 'domain':
            role = 'repository-contract'
        elif has_abstract_repo and not concrete_repo:
            role = 'repository-contract'
        elif not concrete_repo and not _REPO_IMPL_CONTENT_RE.search(f.skel):
            role = 'other' if logic_names or only_widgets else 'repository-impl'
            if logic_names and ui_ok_content:
                role, from_content = 'logic', True
            elif only_widgets and ui_ok:
                role = 'widget'
        else:
            role = 'repository-impl' if _has_contract(f, st, g, concrete_repo) else 'repository'
    elif logic_names and ui_ok_content and not in_repo_folder:
        # content beats file names (C7) and layer-first data folders (K1 FN1); the layer still comes from a
        # UI-ish name or folder when there is one
        role = 'logic'
        from_content = not (ui_ok and (sset & (LOGIC_DIRS | {'state', 'states'}) or stem.endswith(
            LOGIC_SUFFIXES + ('_state', '_states', '_store'))))
    elif sset & {'entities', 'entity'} or stem.endswith('_entity') or (layer == 'domain' and sset & {'models', 'model'}):
        role = 'entity'
    elif data_ok and (stem.endswith(('_dto', '_request', '_response')) or sset & {'dto', 'dtos'}
                      or ('data' in sset and sset & {'models', 'model'})):
        role = 'dto'
    elif data_ok and (stem.endswith(SOURCE_SUFFIXES) or sset & SOURCE_DIRS):
        role = 'source'
    elif data_ok and (stem.endswith('_service') or sset & {'services', 'service'}):
        role = 'service'
        if _OBSERVABILITY_RE.search(stem):
            role = 'other'
            if layer is None:
                layer, weak_data = 'core', False
    elif only_widgets and ui_ok:
        role = 'view' if (stem.endswith(('_screen', '_page', '_view')) or
                          sset & {'view', 'views', 'screens', 'screen', 'pages', 'page'}) else 'widget'
    elif ui_ok and (stem.endswith(('_state', '_states')) or sset & {'state', 'states'}):
        role = 'state'
    elif ui_ok and stem.endswith(('_event', '_events')) and (
            sset & {'bloc', 'blocs', 'cubit', 'cubits'} or f.part_of or tuple(segs) in g['bloc_dirs']):
        role = 'event'
    elif ui_ok and (sset & LOGIC_DIRS or stem.endswith(LOGIC_SUFFIXES)
                    or (stem.endswith('_store') and layer == 'presentation')):
        role = 'logic'
    elif ui_ok and (stem.endswith(('_screen', '_page', '_view')) or sset & {'view', 'views', 'screens', 'screen', 'pages', 'page'}):
        role = 'view'
    elif flat_models and not widget_classes:
        role = 'other'  # P3: formz inputs, UI filter enums
    elif ui_ok and (sset & {'widget', 'widgets', 'components'} or layer == 'presentation'):
        role = 'widget'
    elif has_abstract_repo:
        role = 'repository-contract'
    elif ui_ok and _WIDGET_DECL_RE.search(f.skel):
        role = 'widget'
        if layer is None and not weak_data:
            layer = 'presentation'
    elif ui_ok_content and re.search(r'@[Rr]iverpod\b[^;{}]*?\bclass\s|\bclass\s+\w+Notifier\s+extends\s+_\$|'
                                     r'\bclass\s+\w+\s+extends\s+(?:Cubit\s*<|Bloc\s*<|GetxController\b)', f.skel):
        role, from_content = 'logic', True
    else:
        role = 'other'

    if layer is None:
        if weak_data:
            # models/services/... mean data, except for UI or logic that lives there (layer stays unknown)
            layer = 'presentation' if role in ('view', 'widget') else (
                None if role in ('logic', 'state', 'event') else 'data')
        elif from_content:
            pass  # A14: a content fallback sets the role, never the layer
        elif role in ('logic', 'state', 'event', 'view', 'widget'):
            layer = 'presentation'
        elif role in ('source', 'repository-impl', 'repository', 'dto'):
            layer = 'data'
    f.layer = layer or 'other'
    f.role = role
    f.role_from_content = from_content


def _has_contract(f, st, g, concrete_repo):
    """A concrete *Repository is an implementation only when a contract exists for it (C1)."""
    abstract = g['abstract_repos'] | set(_ABSTRACT_REPO_RE.findall(f.skel))
    for c in st.classes:
        if c['kind'] != 'class' or not c['name']:
            continue
        if 'abstract' in c['mods'] or 'interface' in c['mods'] or 'sealed' in c['mods']:
            continue
        if any(s in abstract for s in c['supers']):
            return True
        base = re.sub(r'Impl$', '', c['name'])
        if base != c['name'] and base in abstract:
            return True
    return False


def is_generated(rel, l10n_dirs):
    base = rel.rsplit('/', 1)[-1]
    if base.endswith(GENERATED_SUFFIXES):
        return True
    if '/generated/' in rel or rel.startswith('lib/generated/'):
        return True
    if base.startswith('app_localizations') or base.startswith('messages_'):
        return True
    for d, stem in l10n_dirs:
        if rel.startswith(d + '/') and (stem is None or base.startswith(stem)):
            return True
    return False


def l10n_output_dirs(root):
    """[(dir, file-stem-or-None)]: an explicit output-dir is skipped whole; without one, gen-l10n writes
    into arb-dir (default lib/l10n), so only <output-localization-file stem>*.dart there is skipped."""
    p = os.path.join(root, 'l10n.yaml')
    if not os.path.isfile(p):
        return []
    vals = {}
    with open(p, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = re.match(r'\s*(output-dir|arb-dir|output-localization-file)\s*:\s*["\']?([^"\'#\s]+)', line)
            if m:
                vals[m.group(1)] = m.group(2).strip()
    if 'output-dir' in vals:
        return [(vals['output-dir'].strip('/'), None)]
    stem = vals.get('output-localization-file', 'app_localizations.dart')
    stem = stem[:-5] if stem.endswith('.dart') else stem
    return [(vals.get('arb-dir', 'lib/l10n').strip('/'), stem)]


def load_files(root, package):
    lib = os.path.join(root, 'lib')
    files = {}
    l10n_dirs = l10n_output_dirs(root)
    if not os.path.isdir(lib):
        return files
    for dirpath, dirnames, filenames in os.walk(lib):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        for fn in sorted(filenames):
            if not fn.endswith('.dart'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            if is_generated(rel, l10n_dirs):
                continue
            try:
                with open(full, encoding='utf-8', errors='replace') as fh:
                    raw = fh.read()
            except OSError:
                continue
            if GENERATED_HEADER_RE.search(raw[:600]):
                continue
            f = DartFile()
            f.rel = rel
            parts = rel.split('/')
            f.segs = [p.lower() for p in parts[1:-1]]
            if f.segs[:1] == ['src']:
                f.segs = f.segs[1:]  # package layout: lib/src/** is classified like lib/**
            f.base = parts[-1].lower()
            f.stem = f.base[:-5].replace('.', '_')  # dotted names: x.repository.dart -> x_repository
            f.raw = raw
            f.lines = raw.split('\n')
            f.line_starts = [0]
            for mm in re.finditer('\n', raw):
                f.line_starts.append(mm.end())
            f.code, f.skel = lex(raw)
            parse_imports(f, package)
            f.struct = None
            f.prim = None
            f.toks = None
            f.role_from_content = False
            f.logic_ranges = None
            parse_suppressions(f)
            files[rel] = f
    return files


_IGNORE_RE = re.compile(r'//\s*arch-ignore(-file)?\s*:\s*((?:ARCH-\d{3}[\s,]*)+)(.*)$')


def parse_suppressions(f):
    f.ignore_file, f.ignore_lines = {}, defaultdict(dict)
    if 'arch-ignore' not in f.raw:
        return
    for i, line in enumerate(f.lines, 1):
        m = _IGNORE_RE.search(line)
        if not m:
            continue
        ids = re.findall(r'ARCH-\d{3}', m.group(2))
        reason = m.group(3).strip() or 'arch-ignore'
        for rid in ids:
            if m.group(1):
                f.ignore_file[rid] = reason
            else:
                f.ignore_lines[i][rid] = reason


def struct_of(f):
    if f.struct is None:
        f.struct = scan_structure(f.skel)
        f.widget_ranges, f.other_class_ranges = [], []
        for c in f.struct.classes:
            rng = (c['body_start'], c['body_end'])
            if is_widget_class(c) or is_state_class(c):
                f.widget_ranges.append(rng)
            else:
                f.other_class_ranges.append(rng)
    return f.struct


def is_state_class(c):
    return bool(re.match(r'(?:State|ConsumerState|\w+State)$', c['extends'] or '')) and c['extends_generic'] \
        and c['kind'] == 'class'


def is_widget_class(c):
    return c['extends'] in WIDGET_BASES


def in_ranges(off, ranges):
    return any(a <= off < b for a, b in ranges)


_ROLE_NAME_RE = re.compile(r'(?:Repository|RepositoryImpl|Source|DataSource|Datasource|Service|Api|Client|'
                           r'UseCase|Usecase|Interactor)$')
_LOGIC_BASES = {'Notifier', 'AsyncNotifier', 'StreamNotifier', 'StateNotifier', 'ChangeNotifier', 'Cubit',
                'Bloc', 'GetxController', 'ValueNotifier', 'FamilyNotifier', 'FamilyAsyncNotifier'}
_NEUTRAL_SUPERS = {'Exception', 'Error', 'Equatable', 'Object'}
_RIVERPOD_ANNOT_RE = re.compile(r'@[Rr]iverpod\b')
_OBSERVABILITY_NAME_RE = re.compile(r'(?:Log|Logger|Logging|Analytics|Crash\w*|Crashlytics|Telemetry|Tracker|Tracking|'
                                    r'Sentry|Metrics)(?:Service|Client|Api|Repository)?$')
_PROVIDER_ROLE_NAME_RE = re.compile(r'(?:Repository|Repo|Source|DataSource|Datasource|Service|Client|Api)Provider$')


def _static_only(st, c):
    """True when every member of class c is static (constructors aside)."""
    seen = False
    for cls, header, off, term in st.members:
        if cls is not c:
            continue
        h = strip_annotations(header).strip()
        if not h:
            continue
        if re.match(r'(?:const\s+|factory\s+)?%s\s*(?:\.\s*\w+\s*)?\(' % re.escape(c['name']), h):
            continue
        if not re.match(r'static\b', h):
            return False
        seen = True
    return seen


def _lower_first(n):
    return n[:1].lower() + n[1:]


def primary_symbols(f):
    """Names through which an importer depends on what makes this file a source/service/repository/use case.

    Primary: contracts (abstract/interface classes), classes with a role name (…Repository, …Source,
    …Service, …UseCase), classes with async methods or call(), classes implementing those, functional
    providers and *Provider variables. Neutral (not returned): enums, exceptions, value classes,
    static namespaces, notifiers/blocs that happen to live in the file, widgets and top-level functions.
    """
    if f.prim is not None:
        return f.prim
    st = struct_of(f)
    async_cls, call_cls = set(), set()
    for cls, header, off, term in st.members:
        if cls is None or term not in ('{', '=>', ';'):
            continue
        pm = parse_method(header)
        if not pm or pm[1] == 'Function':
            continue  # a `FutureOr<void> Function()?` field is not an async method (A15)
        if re.search(r'\b(?:Future|Stream|FutureOr)\b', pm[0]):
            async_cls.add(cls['name'])
        if pm[1] == 'call':
            call_cls.add(cls['name'])
    local = {c['name']: c for c in st.classes if c['name']}
    prim, neutral = set(), set()
    pending = []
    for c in st.classes:
        name = c['name']
        if not name or c['kind'] != 'class' or is_widget_class(c) or is_state_class(c):
            neutral.add(name)
            continue
        supers = set(c['supers'])
        if re.search(r'(?:Exception|Error|Failure)$', name) or supers & {'Exception', 'Error'}:
            neutral.add(name)
            continue
        if {'abstract', 'final'} <= c['mods'] and 'interface' not in c['mods']:
            neutral.add(name)  # static namespace (`abstract final class Keys`)
            continue
        if _static_only(st, c):
            neutral.add(name)  # static namespace written as `abstract class X { static ... }` (A3)
            continue
        if _OBSERVABILITY_NAME_RE.search(name):
            neutral.add(name)  # logger/analytics/crash reporting is cross-cutting, not data (A15)
            continue
        is_logic = bool(supers & _LOGIC_BASES) or (
            c['extends'].startswith('_$') and _RIVERPOD_ANNOT_RE.search(c.get('raw_header', '')))
        if c['mods'] & {'abstract', 'interface'} and not is_logic:
            prim.add(name)
        elif is_logic:
            neutral.add(name)
        elif _ROLE_NAME_RE.search(name) or name in async_cls or name in call_cls:
            prim.add(name)
        else:
            pending.append(c)
    changed = True
    while changed:  # classes implementing a primary type (local, or external and not neutral)
        changed = False
        for c in list(pending):
            ext = [s for s in c['supers'] if s not in _NEUTRAL_SUPERS]
            if any(s in prim or (s not in local and not s.startswith('_$')) for s in ext):
                prim.add(c['name'])
                pending.remove(c)
                changed = True
    for c in st.classes:
        if c['name'] in prim and _RIVERPOD_ANNOT_RE.search(c.get('raw_header', '')):
            prim.add(_lower_first(c['name']) + 'Provider')
            if c['name'].endswith('Notifier'):
                prim.add(_lower_first(c['name'][:-8]) + 'Provider')
    # A2: a provider is primary only when its value is a primary type (Provider<XRepository>,
    # @riverpod XRepository x(Ref), a constructed primary class) or its name says so; Future/Stream/
    # AsyncNotifier providers are neutral.
    def primary_type(t):
        t = (t or '').split('.')[-1]
        return bool(t) and (t in prim or bool(_ROLE_NAME_RE.search(t))) and not _OBSERVABILITY_NAME_RE.search(t)
    for name, kind, vtype, init in top_level_providers(f)[0]:
        named = bool(_PROVIDER_ROLE_NAME_RE.search(name))
        if kind == 'fn':
            if re.match(r'(?:Future|Stream|FutureOr)\b', vtype or ''):
                continue
            if named or primary_type(re.sub(r'[<?].*$', '', vtype or '')):
                prim.add(name)
            continue
        pkind = _PROVIDER_INIT_RE.match(init).group(1)
        if named:
            prim.add(name)
        elif _ASYNC_PROVIDER_RE.match(pkind):
            continue
        elif vtype:
            if primary_type(vtype):
                prim.add(name)
        else:
            m = re.search(r'(?:=>|\breturn)\s*(?:const\s+|new\s+)?([A-Z]\w*)\s*[(.<]', init)
            if m and primary_type(m.group(1)):
                prim.add(name)
    f.prim = prim
    return prim


def tokens(f):
    if f.toks is None:
        f.toks = set(re.findall(r'[A-Za-z_$][\w$]*', f.skel))
    return f.toks


def uses_primary(importer, target, imp, name_filter=None):
    """True when the importer references a primary symbol of the target (or re-exports it)."""
    prim = primary_symbols(target)
    if name_filter:
        prim = {p for p in prim if name_filter(p)}
    if not prim:
        return False
    if imp['kind'] == 'export':
        return True
    return bool(prim & tokens(importer))


# --------------------------------------------------------------------------
# Profile detection
# --------------------------------------------------------------------------
_GEN_NOTIFIER_RE = re.compile(r'\bclass\s+(\w+Notifier)\s+extends\s+_\$\w+')
_VM_CLASS_RE = re.compile(r'\bclass\s+\w+ViewModel\b')
_GETX_CTRL_RE = re.compile(r'\bextends\s+(?:GetxController|GetxService|FullLifeCycleController)\b')
_CTRL_CLASS_RE = re.compile(r'\bclass\s+(\w+Controller)\b(?:\s+extends\s+(\w+))?')
_FLUTTER_CTRLS = {'AnimationController', 'TextEditingController', 'ScrollController', 'PageController',
                  'TabController', 'ValueNotifier', 'GetxController', 'FullLifeCycleController'}
_CHANGE_NOTIFIER_RE = re.compile(r'\b(?:extends|with)\s+ChangeNotifier\b')
_STATEFUL_RE = re.compile(r'\bextends\s+StatefulWidget\b')
_SETSTATE_RE = re.compile(r'\bsetState\s*\(')


_BLOC_CLASS_RE = re.compile(r'\bclass\s+\w+\s+extends\s+(?:Hydrated|Replay)?(?:Cubit|Bloc)\s*<')


def detect_profile(files, deps, override, path_pkgs=()):
    sig = []
    counts = defaultdict(int)
    for f in files.values():
        s = set(f.segs)
        if s & {'notifier', 'notifiers'} and 'presentation' in s:
            counts['notifier_dir_files'] += 1
        if s & {'view_model', 'view_models', 'viewmodel', 'viewmodels'}:
            counts['vm_dir_files'] += 1
        counts['gen_notifiers'] += len(_GEN_NOTIFIER_RE.findall(f.skel))
        counts['vm_classes'] += len(_VM_CLASS_RE.findall(f.skel))
        if f.stem.endswith(('_bloc', '_cubit')):
            counts['bloc_files'] += 1
        counts['bloc_classes'] += len(_BLOC_CLASS_RE.findall(f.skel))
        if f.layer == 'domain':
            counts['domain_files'] += 1
        counts['getx_ctrls'] += len(_GETX_CTRL_RE.findall(f.skel))
        if s & {'controller', 'controllers'}:
            for name, base in _CTRL_CLASS_RE.findall(f.skel):
                if base not in _FLUTTER_CTRLS:
                    counts['mvc_ctrls'] += 1
        if s & {'model', 'models'}:
            counts['model_dirs'] += 1
        if s & {'view', 'views'}:
            counts['view_dirs'] += 1
        counts['change_notifiers'] += len(_CHANGE_NOTIFIER_RE.findall(f.skel))
        counts['stateful'] += len(_STATEFUL_RE.findall(f.skel))
        counts['setstate'] += len(_SETSTATE_RE.findall(f.skel))
        if f.role in ('repository-contract', 'repository-impl', 'repository') or \
                re.search(r'\bclass\s+\w*Repository\w*\b', f.skel):
            counts['repos'] += 1
        for imp in f.imports:
            if imp['pkg'] and imp['pkg'].endswith('_repository'):
                counts['repo_pkgs'] += 1
        if f.role == 'usecase' and 'application' not in s:
            counts['usecases'] += 1  # MVN use cases; codewithandrea application/ services don't count

    riverpod = sorted(d for d in RIVERPOD_DEPS if d in deps)
    bloc = sorted(d for d in ('bloc', 'flutter_bloc') if d in deps)
    if riverpod:
        sig.append('dependency: ' + ', '.join(riverpod))
    if bloc:
        sig.append('dependency: ' + ', '.join(bloc))
    for d in ('get', 'provider', 'mvc_pattern', 'fluttery_framework', 'get_it', 'injectable', 'mobx',
              'flutter_redux', 'stacked'):
        if d in deps:
            sig.append('dependency: ' + d)
    if counts['notifier_dir_files']:
        sig.append('%d files under */presentation/notifier/' % counts['notifier_dir_files'])
    if counts['gen_notifiers']:
        sig.append('suffix *Notifier extends _$X x%d' % counts['gen_notifiers'])
    if counts['vm_dir_files']:
        sig.append('%d files under view_model(s)/' % counts['vm_dir_files'])
    if counts['vm_classes']:
        sig.append('suffix *ViewModel x%d' % counts['vm_classes'])
    if counts['bloc_files']:
        sig.append('%d *_bloc/_cubit.dart files' % counts['bloc_files'])
    if counts['getx_ctrls']:
        sig.append('GetxController subclasses x%d' % counts['getx_ctrls'])
    if counts['mvc_ctrls']:
        sig.append('*Controller classes under controller(s)/ x%d' % counts['mvc_ctrls'])
    if counts['change_notifiers']:
        sig.append('ChangeNotifier classes x%d' % counts['change_notifiers'])

    pres, conf = 'unknown', 'low'
    # MVN (K3 rule): the MVN spec makes use cases mandatory, so they are required for high confidence
    a, b, c, d = counts['notifier_dir_files'], counts['usecases'], counts['gen_notifiers'], counts['domain_files']
    mvn = None
    if riverpod and not counts['vm_dir_files']:
        if a and b:
            mvn = 'high'
        elif b and c >= 3:
            mvn = 'medium'
        elif a and d:
            mvn = 'low'
            sig.append('presentation/notifier/ + domain/ but 0 use cases')
        elif c >= 3:
            sig.append('*Notifier suffix x%d but no domain/usecases/: plain Riverpod naming, not MVN' % c)
    # getx / mvvm / bloc: the majority pattern wins; a minority is a signal (P1)
    cands = []
    if 'get' in deps and counts['getx_ctrls']:
        cands.append(('getx', counts['getx_ctrls'], 'high', 'GetxController'))
    if counts['vm_dir_files'] or counts['vm_classes'] >= 3:
        cands.append(('mvvm', max(counts['vm_classes'], counts['vm_dir_files']),
                      'high' if counts['vm_dir_files'] and counts['vm_classes'] else 'medium', 'view model'))
    if bloc or counts['bloc_files'] or counts['bloc_classes']:
        nb = max(counts['bloc_files'], counts['bloc_classes'], 1)
        cands.append(('bloc', nb, 'high' if bloc and (counts['bloc_files'] or counts['bloc_classes']) else 'medium',
                      'bloc/cubit'))
    if mvn:
        pres, conf = 'mvn', mvn
    elif cands:
        order = {'getx': 0, 'mvvm': 1, 'bloc': 2}
        best = sorted(cands, key=lambda x: (-x[1], order[x[0]]))[0]
        pres, conf = best[0], best[2]
        others = [x for x in cands if x[0] != best[0]]
        if others:
            sig.append('mixed architecture: %s x%d (majority) + %s; report AP-mixed-architecture once' % (
                best[3], best[1], ', '.join('%s x%d' % (x[3], x[1]) for x in others)))
            if conf == 'high':
                conf = 'medium'
    elif ({'mvc_pattern', 'fluttery_framework'} & deps) or \
            (counts['mvc_ctrls'] and counts['model_dirs'] and counts['view_dirs']):
        pres, conf = 'mvc', 'high' if {'mvc_pattern', 'fluttery_framework'} & deps else 'medium'
    elif 'provider' in deps and counts['change_notifiers']:
        pres, conf = 'provider', 'medium'
    elif riverpod:
        pres, conf = 'riverpod', 'medium'
    elif 'get' in deps:
        pres, conf = 'getx', 'low'
    elif not (bloc or riverpod or {'provider', 'mobx', 'flutter_redux', 'stacked'} & deps) and \
            counts['stateful'] and counts['setstate']:
        pres, conf = 'setstate', 'medium'
        sig.append('StatefulWidget x%d, setState( x%d' % (counts['stateful'], counts['setstate']))
    sig.append('use cases: %d files' % b)
    if path_pkgs:
        sig.append('path packages: %s (not scanned)' % ', '.join(sorted(path_pkgs)))
    if override and override != 'auto':
        if override != pres:
            sig.insert(0, 'declared via --profile %s (detected: %s)' % (override, pres))
        else:
            sig.insert(0, 'declared via --profile %s' % override)
        pres, conf = override, 'high'

    sm = []
    if riverpod:
        sm.append('riverpod')
    if bloc:
        sm.append('bloc')
    for d, label in (('provider', 'provider'), ('get', 'getx'), ('mobx', 'mobx'),
                     ('flutter_redux', 'redux'), ('redux', 'redux'), ('signals', 'signals'),
                     ('stacked', 'stacked')):
        if d in deps and label not in sm:
            sm.append(label)
    if not sm and counts['setstate']:
        sm.append('setstate')
    di = []
    if riverpod:
        di.append('riverpod')
    for d, label in (('get_it', 'get_it'), ('injectable', 'injectable'), ('provider', 'provider'),
                     ('flutter_bloc', 'bloc'), ('get', 'getx'), ('kiwi', 'kiwi')):
        if d in deps:
            di.append(label)

    layers_present = {f.layer for f in files.values()}
    has_domain_dirs = any('domain' in f.segs for f in files.values())
    has_data_dirs = any('data' in f.segs for f in files.values())
    has_uc_or_ent = any(set(f.segs) & {'usecases', 'use_cases', 'entities'} for f in files.values())
    clean = has_domain_dirs and has_data_dirs and has_uc_or_ent

    feats = defaultdict(int)
    top = set()
    for f in files.values():
        if f.segs:
            top.add(f.segs[0])
        if f.feature:
            feats[f.feature] += 1
    layer_first = bool(top & {'data', 'domain', 'presentation', 'ui', 'screens', 'models', 'services'})
    # CONTRACTS says >=2 features; relaxed to >=1 so a one-feature app is feature-first
    feature_first = len(feats) >= 1
    if feature_first and layer_first:
        layout = 'hybrid'
    elif feature_first:
        layout = 'feature-first'
    else:
        layout = 'layer-first'
        if not layer_first:
            sig.append('flat lib/ (no feature or layer folders)')

    return {
        'presentation': pres,
        'clean_architecture': bool(clean),
        'repository_pattern': counts['repos'] > 0 or counts['repo_pkgs'] > 0 or
        any(p.endswith('_repository') for p in path_pkgs),
        'use_cases': any(f.role == 'usecase' for f in files.values()),
        'layout': layout,
        'state_management': sm,
        'di': di,
        'confidence': conf,
        'signals': sig,
    }, sorted({f.feature for f in files.values() if f.feature}), 'domain' in layers_present


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, files, profile, package, has_domain):
        self.files = files
        self.profile = profile
        self.pres = profile['presentation']
        self.layout = profile['layout']
        self.package = package
        self.has_domain = has_domain
        self.hits = []
        self.suppressed = []
        self.declared_classes = set()
        self.record_typedefs = set()
        aliases = set()
        for f in files.values():
            if 'typedef' in f.skel:
                self.record_typedefs |= set(re.findall(r'\btypedef\s+(\w+)\s*(?:<[^=]*>)?\s*=\s*\(', f.skel))
            self.declared_classes |= {c['name'] for c in struct_of(f).classes if c['name']}
            if 'GetIt' in f.skel:
                aliases |= set(_GETIT_ALIAS_RE.findall(f.skel))
        aliases -= {'sl', 'getIt', 'locator'}
        self.locator_alias_re = re.compile(r'\b(?:%s)\s*(?:<|\(|\.\s*get\s*<)' % '|'.join(sorted(aliases))) \
            if aliases else None  # FN-2: `final injector = GetIt.I;` then `injector<X>()`
        self._assign_cache = {}

    def is_reassigned(self, f, name, decl_end):
        """True when `name` is assigned anywhere in lib/ besides its declaration (A5)."""
        pat = re.compile(r'(?<![\w$])%s\s*(?:[-+*/%%&|^]|\?\?|<<|>>)?=(?!=)|(?:\+\+|--)\s*%s\b|\b%s\s*(?:\+\+|--)'
                         % ((re.escape(name),) * 3))
        pool = [f] if name.startswith('_') else [x for x in self.files.values() if name in tokens(x)]
        for x in pool:
            for m in pat.finditer(x.skel):
                if x is f and m.start() < decl_end <= m.end() + len(name) + 4:
                    continue
                if x is f and abs(m.start() - (decl_end - len(name))) < len(name) + 2:
                    continue
                return True
        return False

    def hit(self, rid, f, line, evidence, severity=None, note='', extra_files=None, mvn_seam=False):
        name, sev, msg = RULES[rid]
        v = {'id': rid, 'name': name, 'severity': severity or sev, 'file': f.rel, 'line': line,
             'evidence': evidence[:200], 'message': msg, 'note': note}
        if extra_files:
            v['_files'] = extra_files
        if mvn_seam:
            self.suppressed.append({'id': rid, 'file': f.rel, 'line': line,
                                    'reason': 'MVN DI seam (use-case provider)'})
            return
        reason = f.ignore_file.get(rid) or f.ignore_lines.get(line, {}).get(rid) \
            or f.ignore_lines.get(line - 1, {}).get(rid)
        if reason:
            self.suppressed.append({'id': rid, 'file': f.rel, 'line': line, 'reason': reason})
            return
        self.hits.append(v)


REPO_ROLES = ('repository-contract', 'repository-impl')
ALL_REPO_ROLES = ('repository-contract', 'repository-impl', 'repository')
CONCRETE_DATA_ROLES = ('source', 'service', 'repository-impl')
UI_ROLES = ('view', 'widget')
SKIP_ROLES = ('barrel', 'di')  # no rules apply to barrels and DI wiring (CONTRACTS section 18)

# Symbols of common I/O packages, used to judge *how* an importer uses the package (A4/A5).
IO_PKG_SYMBOLS = {
    'dio': {'Dio', 'DioException', 'DioError', 'DioExceptionType', 'DioErrorType', 'CancelToken', 'Options',
            'BaseOptions', 'Response', 'Interceptor', 'InterceptorsWrapper', 'QueuedInterceptor', 'FormData',
            'MultipartFile', 'RequestOptions', 'Headers', 'ResponseType', 'LogInterceptor', 'DioMixin',
            'ErrorInterceptorHandler', 'RequestInterceptorHandler', 'ResponseInterceptorHandler'},
    'http': {'Client', 'Response', 'ClientException', 'Request', 'MultipartRequest', 'MultipartFile',
             'StreamedResponse', 'BaseClient', 'BaseRequest'},
    'shared_preferences': {'SharedPreferences', 'SharedPreferencesAsync', 'SharedPreferencesWithCache'},
    'flutter_secure_storage': {'FlutterSecureStorage', 'AndroidOptions', 'IOSOptions'},
    'cloud_firestore': {'FirebaseFirestore', 'DocumentSnapshot', 'QuerySnapshot', 'CollectionReference',
                        'DocumentReference', 'FieldValue', 'Timestamp', 'GeoPoint', 'FirebaseException',
                        'SetOptions', 'WriteBatch', 'QueryDocumentSnapshot'},
    'firebase_auth': {'FirebaseAuth', 'User', 'UserCredential', 'FirebaseAuthException', 'AuthCredential',
                      'GoogleAuthProvider', 'PhoneAuthProvider', 'EmailAuthProvider', 'PhoneAuthCredential'},
    'path_provider': {'getApplicationDocumentsDirectory', 'getTemporaryDirectory', 'getApplicationSupportDirectory',
                      'getExternalStorageDirectory', 'getDownloadsDirectory', 'getLibraryDirectory'},
}
IO_VALUE_SYMBOLS = {'CancelToken', 'Timestamp', 'GeoPoint', 'Options', 'ResponseType', 'SetOptions'}
_EXC_NAME_RE = re.compile(r'(?:Exception|Error)(?:Type)?$')
_DI_SITE_RE = re.compile(r'\bcreate\s*:|\b\w+(?:ViewModel|Bloc|Cubit|Notifier|Controller|Store)\s*\(')


def _arg_end(s, i):
    """End of the argument that starts at i (next ',' or closing bracket at depth 0)."""
    depth, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return i
            depth -= 1
        elif c == ',' and depth == 0:
            return i
        i += 1
    return n


def di_site_ranges(f):
    """Spans where objects are only handed to logic: `create:` arguments (BlocProvider, RepositoryProvider,
    ChangeNotifierProvider, ...) and the argument lists of *ViewModel/*Bloc/*Cubit/*Notifier(...) constructors."""
    out = []
    for m in _DI_SITE_RE.finditer(f.skel):
        if m.group().startswith('create'):
            out.append((m.end(), _arg_end(f.skel, m.end())))
        else:
            p = m.end() - 1
            out.append((p, _skip_balanced(f.skel, p, '(', ')')))
    return out


def provider_ranges(f):
    """Spans of top-level provider declarations (a provider runs outside the widget tree)."""
    st = struct_of(f)
    tops = [(off, header, term) for cls, header, off, term in st.members if cls is None]
    out = []
    for i, (off, header, term) in enumerate(tops):
        end = tops[i + 1][0] if i + 1 < len(tops) else len(f.skel)
        if _RIVERPOD_ANNOT_RE.search(header) and not class_info(header):
            out.append((off, end))
        elif term == '=' and _PROVIDER_INIT_RE.match(_initializer(f.skel, off, header)):
            out.append((off, end))
    return out


def logic_class_ranges(f):
    """Bodies of the non-widget classes and mixins of a file (where logic lives)."""
    if f.logic_ranges is None:
        st = struct_of(f)
        f.logic_ranges = [(c['body_start'], c['body_end']) for c in st.classes
                          if c['kind'] in ('class', 'mixin') and not is_widget_class(c) and not is_state_class(c)]
    return f.logic_ranges


_DIR_LINE_RE = re.compile(r'(?m)^[ \t]*(?:import|export|part|library)\b[^;]*;')


def _code_offsets(f, names):
    """Offsets of identifier uses of `names` in the code (directives excluded)."""
    if not names:
        return []
    skip = [(m.start(), m.end()) for m in _DIR_LINE_RE.finditer(f.skel)]
    pat = re.compile(r'(?<![\w$])(?:%s)(?![\w$])' % '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True)))
    return [(m.start(), m.group()) for m in pat.finditer(f.skel) if not in_ranges(m.start(), skip)]


def io_package_uses(f, imp):
    """[(offset, symbol)] for the uses of an I/O package import, or None when they cannot be told apart."""
    ev = imp['evidence']
    m = re.search(r'\bas\s+(\w+)', ev)
    if m:
        pre = m.group(1)
        return [(x.start(), x.group(1)) for x in re.finditer(r'(?<![\w$.])%s\s*\.\s*(\w+)' % re.escape(pre), f.skel)
                if not _DIR_LINE_RE.match(f.skel, f.skel.rfind('\n', 0, x.start()) + 1)]
    m = re.search(r'\bshow\s+([\w\s,]+?)(?:\bhide\b|;|$)', ev)
    names = set(re.findall(r'\w+', m.group(1))) if m else IO_PKG_SYMBOLS.get(imp['pkg'])
    if not names:
        return None
    return _code_offsets(f, names)


def io_use_kind(uses):
    """'io' | 'exception' | 'none' for a list of (offset, symbol)."""
    syms = {u[1] for u in uses}
    if not syms:
        return 'none'
    if syms <= IO_VALUE_SYMBOLS:
        return 'none'
    if all(_EXC_NAME_RE.search(x) or x in IO_VALUE_SYMBOLS for x in syms):
        return 'exception'
    return 'io'


def _static_ref_only(f, offs):
    """True when every use is `Name.member` static access (not .instance/.I/.of/.get) or a supertype clause."""
    for off, name in offs:
        tail = f.skel[off + len(name):off + len(name) + 40]
        m = re.match(r'\s*\.\s*(\w+)', tail)
        if m and m.group(1) not in ('instance', 'I', 'i', 'shared', 'of', 'get', 'read', 'watch'):
            continue
        head = f.skel[max(0, off - 120):off]
        if re.search(r'\b(?:extends|with|implements)\s+(?:[\w<>?]+\s*,\s*)*$', head):
            continue
        return False
    return True


def _target(ctx, imp):
    t = imp['target']
    return ctx.files.get(t) if t else None


def _flutter_lib(imp):
    if imp['pkg'] == 'flutter':
        return imp['pkg_path'].split('/', 1)[1] if '/' in imp['pkg_path'] else ''
    return None


_UI_HARD_RE = re.compile(
    r'\b(?:Widget|BuildContext|Navigator|ScaffoldMessenger|Scaffold|SnackBar|MaterialPageRoute|'
    r'show(?:Dialog|ModalBottomSheet|BottomSheet|DatePicker|TimePicker|DateRangePicker|GeneralDialog|Menu|'
    r'SearchPage|AboutDialog|LicensePage|Cupertino\w+|Adaptive\w+)\s*[<(]|'
    r'CupertinoPageRoute|PageRoute|Theme|MediaQuery|Overlay|OverlayEntry|Text|AlertDialog|Dialog|Icon|Image|'
    r'Container|Column|Row|Stack|StatelessWidget|StatefulWidget|InheritedWidget|MaterialApp|Builder|Padding|'
    r'Center|SizedBox|ListView|GestureDetector|InkWell|[A-Z]\w*Button|AppBar|TextStyle|RenderObject|Element)\b')
_UI_CTRL_RE = re.compile(r'\b(?:TextEditingController|FocusNode|ScrollController|PageController|TabController|'
                         r'GlobalKey|FormState|AnimationController|TickerProvider)\b')
_ACCESSOR_RE = re.compile(r'\bstatic\s+[\w<>?]+\s+\w+\s*\(\s*BuildContext\s+(\w+)\s*\)\s*(?:=>|\{\s*return)\s*'
                          r'(?:BlocProvider\s*\.\s*of|Provider\s*\.\s*of|\1\s*\.\s*(?:read|watch))\b')


def flutter_ui_use(f):
    """'hard' (widgets/context/navigation used), 'ctrl' (only UI controllers/keys), 'accessor' (only the
    `static X get(BuildContext)` accessor idiom), or 'value' (value types such as Color, TimeOfDay)."""
    hard = {m.group() for m in _UI_HARD_RE.finditer(f.skel)
            if not _DIR_LINE_RE.match(f.skel, f.skel.rfind('\n', 0, m.start()) + 1)}
    if hard:
        if hard == {'BuildContext'} and _ACCESSOR_RE.search(f.skel) and \
                len(re.findall(r'\bBuildContext\b', f.skel)) == len(_ACCESSOR_RE.findall(f.skel)):
            return 'accessor'
        return 'hard'
    if _UI_CTRL_RE.search(f.skel):
        return 'ctrl'
    return 'value'


def rules_imports(ctx):
    files = ctx.files
    pres = ctx.pres
    ff = ctx.layout in ('feature-first', 'hybrid')
    feature_edges = defaultdict(list)
    has_domain_contracts = any(f.layer == 'domain' and f.role == 'repository-contract' for f in files.values())
    loose = pres in ('riverpod', 'provider')  # A4: logic reaches data through providers/DI
    for f in files.values():
        if f.layer == 'app' or f.role in SKIP_ROLES:
            continue  # composition root, DI wiring and barrels may import anything
        has_riverpod_annot = bool(re.search(r'@riverpod\b|@Riverpod\s*\(', f.skel))
        in_usecases = bool(set(f.segs) & {'usecases', 'use_cases', 'usecase', 'use_case'})
        wr = struct_of(f) and f.widget_ranges
        lr = logic_class_ranges(f)
        di = None
        for imp in f.imports:
            t = _target(ctx, imp)
            ev = imp['evidence']
            ln = imp['line']
            pkg = imp['pkg']
            io = pkg in IO_PACKAGES
            # ---- domain rules
            if f.layer == 'domain':
                if t and t.layer == 'data':
                    seam = (in_usecases and has_riverpod_annot and t.role == 'repository-impl')
                    # A1: Flutter-MVVM use cases depend on the repositories in data/repositories/
                    contract_like = t.role in ('repository-contract', 'repository')
                    if not (contract_like and (pres == 'mvvm' or not has_domain_contracts)):
                        ctx.hit('ARCH-001', f, ln, ev, mvn_seam=seam)
                if t and t.layer == 'presentation':
                    widgetless = not struct_of(t).classes or not t.widget_ranges
                    ctx.hit('ARCH-002', f, ln, ev, severity='medium' if widgetless else None,
                            note='the imported file declares no widget' if widgetless else '')
                if pkg:
                    fl = _flutter_lib(imp)
                    if fl is not None:
                        if fl == 'foundation.dart':
                            ctx.hit('ARCH-003', f, ln, ev, severity='low', note='foundation.dart only')
                        elif pres == 'mvvm' and flutter_ui_use(f) == 'value':
                            ctx.hit('ARCH-003', f, ln, ev, severity='low',
                                    note='value types only; import foundation.dart or `show` the type')
                        else:
                            ctx.hit('ARCH-003', f, ln, ev)
                    elif io or pkg in ('flutter_riverpod', 'hooks_riverpod', 'flutter_bloc', 'provider', 'get'):
                        ctx.hit('ARCH-003', f, ln, ev)
                    elif pkg in ('riverpod', 'riverpod_annotation'):
                        if not (pres == 'mvn' and in_usecases):
                            ctx.hit('ARCH-003', f, ln, ev)
            # ---- data -> presentation
            if f.layer == 'data' and t and t.layer == 'presentation':
                ctx.hit('ARCH-004', f, ln, ev)
            # ---- UI rules
            if f.role in UI_ROLES:
                if di is None:
                    di = di_site_ranges(f)
                if io and imp['kind'] == 'import':
                    uses = io_package_uses(f, imp)
                    if not uses:  # unknown package symbols, or an unused import: the import is the evidence
                        ctx.hit('ARCH-005', f, ln, ev)
                    else:
                        uses = [u for u in uses if in_ranges(u[0], wr)]  # A5: co-located providers are logic
                        kind = io_use_kind(uses)
                        if kind == 'exception':
                            ctx.hit('ARCH-005', f, ln, ev, severity='low',
                                    note='transport exception type reaches the UI; map it to a failure in the repository')
                        elif kind == 'io':
                            if all(in_ranges(u[0], di) for u in uses if u[1] not in IO_VALUE_SYMBOLS):
                                ctx.hit('ARCH-005', f, ln, ev, severity='low',
                                        note='transport constructed at a DI site; see ARCH-007')
                            else:
                                ctx.hit('ARCH-005', f, ln, ev)
                elif t and t.role in CONCRETE_DATA_ROLES and uses_primary(f, t, imp):
                    offs = _code_offsets(f, primary_symbols(t) & tokens(f))
                    if pres in ('riverpod', 'mvn'):
                        offs = [o for o in offs if in_ranges(o[0], wr)]
                    if imp['kind'] == 'export' or offs:
                        direct = [o for o in offs if not o[1].endswith('Provider') and re.match(
                            r'\s*(?:<[^()]*>)?\s*(?:\(|\.\s*(?:instance|I|shared)\b)', f.skel[o[0] + len(o[1]):o[0] + len(o[1]) + 60])]
                        if offs and all(in_ranges(o[0], di) for o in offs):
                            ctx.hit('ARCH-005', f, ln, ev, severity='low',
                                    note='only constructed/handed over at a DI site; see ARCH-007')
                        elif loose and t.role in ('service', 'repository-impl') and offs and not direct:
                            ctx.hit('ARCH-005', f, ln, ev, severity='low',
                                    note='reached through its provider (DI); consider moving the call into a notifier')
                        else:
                            ctx.hit('ARCH-005', f, ln, ev)
                if pres in ('mvvm', 'mvn', 'bloc', 'mvc', 'getx') and t and \
                        (t.role in ALL_REPO_ROLES or t.role == 'usecase') and uses_primary(f, t, imp):
                    offs = _code_offsets(f, primary_symbols(t) & tokens(f))
                    bloc_di = re.search(r'\b(?:BlocProvider|RepositoryProvider|MultiRepositoryProvider)\s*[(<.]', f.skel)
                    if not bloc_di and not (offs and all(in_ranges(o[0], di) for o in offs)):  # A2: DI seam
                        ctx.hit('ARCH-008', f, ln, ev)
            if f.layer == 'presentation' and t and t.role == 'dto':
                if ctx.profile['clean_architecture'] or t.stem.endswith(('_dto', '_request', '_response')):
                    ctx.hit('ARCH-006', f, ln, ev)
            # ---- logic rules
            if f.role == 'logic':
                if io and imp['kind'] == 'import':
                    uses = io_package_uses(f, imp)
                    kind = 'io' if uses is None else io_use_kind(uses)
                    if kind == 'io' and loose and not any(
                            _IO_CALL_RE.search(f.skel, a0, a1) for a0, a1 in (lr or [(0, len(f.skel))])):
                        kind = 'none'  # A4: injected through a provider, no construction or I/O call here
                    if kind == 'io':
                        ctx.hit('ARCH-007', f, ln, ev)
                elif t and t.role in CONCRETE_DATA_ROLES and uses_primary(f, t, imp):
                    names = _concrete_primaries(t) & tokens(f)  # A4: shared contract+impl file -> impl only
                    if loose:
                        names = {n for n in names if re.search(r'(?<![\w$.])%s\s*(?:<[^()]*>)?\s*\(' % re.escape(n), f.skel)}
                    if names or imp['kind'] == 'export':
                        ctx.hit('ARCH-007', f, ln, ev)
                fl = _flutter_lib(imp)
                if fl in ('material.dart', 'widgets.dart', 'cupertino.dart'):
                    use = flutter_ui_use(f)
                    if pres == 'getx':
                        if use == 'hard':  # A11: controllers, keys and Color are idiomatic in GetX controllers
                            ctx.hit('ARCH-009', f, ln, ev, severity='low')
                    elif use == 'value':
                        # Value types only (Color, DateTimeRange, ...): not reported. bloclibrary's own ThemeCubit and
                        # flutter/samples Compass do this; agents repeated even the low hit as a violation (benchmark).
                        pass
                    elif use != 'accessor':  # C6: reported once as ARCH-102 (low)
                        ctx.hit('ARCH-009', f, ln, ev)
                if pres not in ('mvn', 'riverpod') and t:
                    reached = [t] if t.role == 'logic' else (
                        [x for x in _barrel_reach(ctx, t) if _declared_names(x) & tokens(f)] if t.role == 'barrel' else [])
                    if any(x.rel != f.rel and x.rel not in f.parts for x in reached if x.role == 'logic'):
                        ctx.hit('ARCH-010', f, ln, ev, severity='medium' if pres == 'bloc' else 'low')
                if pres == 'mvn' and t and (t.role in ALL_REPO_ROLES or t.role in ('source', 'service')) \
                        and uses_primary(f, t, imp):
                    ctx.hit('ARCH-012', f, ln, ev)
            # ---- repository -> repository (A3/A7/C4)
            if f.role in ALL_REPO_ROLES and t and t.role in ALL_REPO_ROLES and t.rel != f.rel and \
                    imp['kind'] == 'import' and re.search(r'\bclass\s+\w*Repo(?:sitory)?\w*\b', f.skel):
                names = {n for n in primary_symbols(t) & tokens(f)
                         if re.search(r'Repo(?:sitory)?\w*$', n) or n.endswith('Provider')}
                names = {n for n in names if not n.endswith('Provider') or _PROVIDER_REPO_RE.search(n)}
                offs = _code_offsets(f, names)
                if offs and not _static_ref_only(f, offs) and not _own_contract(f, t):
                    ctx.hit('ARCH-011', f, ln, ev)
            # ---- features
            if ff and t:
                if f.is_core_area and t.feature:
                    ctx.hit('ARCH-013', f, ln, ev)
                if f.feature and t.feature and t.feature != f.feature:
                    nav_or_ui_wiring = f.role in ('view', 'widget') and (
                        t.role in ('view', 'widget') or  # a page opening another feature's page = navigation
                        (pres == 'bloc' and t.role in ('logic', 'state', 'event', 'barrel')))  # blocs connect via UI
                    if t.layer in ('data', 'presentation') and not _feature_public(t) and not nav_or_ui_wiring and \
                            not (pres in ('riverpod', 'mvn') and _provider_refs_only(f, t)):
                        ctx.hit('ARCH-014', f, ln, ev)
                    feature_edges[(f.feature, t.feature)].append((f, ln, _strong_edge(ctx, f, t)))
    if ff:
        rule_feature_cycles(ctx, feature_edges)


_PROVIDER_REPO_RE = re.compile(r'Repo(?:sitory)?Provider$')
_IO_CALL_RE = re.compile(
    r'\bhttp\.(?:get|post|put|patch|delete|head|read|send)\s*\(|\bDio\s*\(|'
    r'\b_?\w*[dD]io\s*!?\s*\.\s*(?:get|post|put|patch|delete|request|fetch|download|getUri|postUri)\s*[<(]|'
    r'\b(?:widget\s*\.\s*)?_?\w*(?:[hH]ttp[cC]lient|[cC]lient|[hH]ttp)\s*!?\s*\.\s*(?:get|post|put|patch|delete|head|send)\s*[<(]|'
    r'\bSharedPreferences\.getInstance\s*\(|\bFirebase(?:Firestore|Auth|Storage|Database|Functions)\.instance\b|'
    r'\bSupabase\.instance\b|\b\w*[cC]lient\s*!?\s*\.\s*functions\s*\.\s*invoke\s*\(|\bopenDatabase\s*\(|'
    r'\b(?:Web)?Socket\.connect\s*\(|\bWebSocketChannel\.connect\s*\(|\bHive\.openBox\s*[<(]')


def _concrete_primaries(t):
    """Primary symbols of t minus its abstract classes (a contract sharing the file with its impl)."""
    abstract = {c['name'] for c in struct_of(t).classes if c['mods'] & {'abstract', 'interface', 'sealed'}}
    return primary_symbols(t) - abstract


def _barrel_reach(ctx, t, depth=0, seen=None):
    """Files a barrel re-exports, transitively (C3/FN-5)."""
    seen = set() if seen is None else seen
    out = []
    for imp in t.imports:
        if imp['kind'] != 'export' or not imp['target'] or imp['target'] in seen:
            continue
        seen.add(imp['target'])
        x = ctx.files.get(imp['target'])
        if not x:
            continue
        out.append(x)
        if x.role == 'barrel' and depth < 4:
            out += _barrel_reach(ctx, x, depth + 1, seen)
    return out


def _feature_public(t):
    """A bloclibrary feature's models/ (and its barrel) are its public API."""
    return t.feature is not None and t.segs[:1] == [t.feature] and len(t.segs) >= 2 and \
        t.segs[1] in ('models', 'model') and t.layer == 'presentation'


def _declared_names(t):
    st = struct_of(t)
    names = {c['name'] for c in st.classes if c['name']}
    for cls, header, off, term in st.members:
        if cls is not None:
            continue
        if term == '=':
            pv = parse_var(header)
            if pv:
                names.add(pv[2])
        elif term in ('{', '=>') and not class_info(header):
            pm = parse_method(header)
            if pm:
                names.add(pm[1])
                if _RIVERPOD_ANNOT_RE.search(header):
                    names.add(pm[1] + 'Provider')
    for c in st.classes:
        if c['name'] and _RIVERPOD_ANNOT_RE.search(c.get('raw_header', '')):
            names.add(_lower_first(c['name']) + 'Provider')
            if c['name'].endswith('Notifier'):
                names.add(_lower_first(c['name'][:-8]) + 'Provider')
    return names


def _provider_refs_only(f, t):
    """A13: the importer only watches/reads the other feature's providers."""
    used = _declared_names(t) & tokens(f)
    return bool(used) and all(n.endswith('Provider') for n in used)


def _own_contract(impl, contract):
    if impl.role not in ('repository-impl', 'repository') or contract.role != 'repository-contract':
        return False
    if impl.stem.replace('_impl', '') == contract.stem or impl.stem.startswith(contract.stem):
        return True
    declared = set(m for m in _ABSTRACT_REPO_RE.findall(contract.skel))
    if declared:
        for m in re.finditer(r'\b(?:implements|extends)\s+([\w<>,\s]+?)\s*\{', impl.skel):
            names = set(re.findall(r'\w+', m.group(1)))
            if names & declared:
                return True
    return False


def _sccs(graph):
    """Tarjan's strongly connected components (iterative)."""
    index, low, stack, on, out = {}, {}, [], set(), []
    counter = [0]
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph.get(root, ()))))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on.add(root)
        while work:
            node, it = work[-1]
            nxt = next(it, None)
            if nxt is not None:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter[0]
                    counter[0] += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(sorted(graph.get(nxt, ())))))
                elif nxt in on:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                out.append(sorted(comp))
    return out


def _shortest_cycle(graph, start, members):
    """Shortest cycle start -> ... -> start inside one SCC (BFS)."""
    prev = {start: None}
    queue = [start]
    while queue:
        nq = []
        for n in queue:
            for nx in sorted(graph.get(n, ())):
                if nx not in members:
                    continue
                if nx == start:
                    path = [n]
                    while prev[path[-1]] is not None:
                        path.append(prev[path[-1]])
                    return list(reversed(path)) + [start]
                if nx not in prev:
                    prev[nx] = n
                    nq.append(nx)
        queue = nq
    return [start, start]


def _strong_edge(ctx, f, t):
    """False when f only uses t's routes (pages/screens) or its public models, directly or through a barrel."""
    used = [t]
    if t.role == 'barrel':
        used = [x for x in _barrel_reach(ctx, t) if _declared_names(x) & tokens(f)] or [t]
    return any(not (_feature_public(x) or x.role == 'view' or x.role == 'barrel') for x in used)


def rule_feature_cycles(ctx, edges):
    """ARCH-015, reported once per strongly connected component of the feature graph. A component that only
    exists through navigation (a page importing another feature's page) or shared models is low."""
    strong = defaultdict(set)
    graph = defaultdict(set)
    for (a, b), locs in edges.items():
        graph[a].add(b)
        if any(x[2] for x in locs):
            strong[a].add(b)
    strong_members = set()
    for comp in _sccs(strong):
        if len(comp) >= 2:
            strong_members |= set(comp)
    for comp in _sccs(graph):
        if len(comp) < 2:
            continue
        weak = not (set(comp) & strong_members)
        if weak and ctx.pres == 'bloc':
            continue  # navigation-only cycles are the bloclibrary example layout (flutter_weather)
        members = set(comp)
        cyc = _shortest_cycle(graph, comp[0], members)
        anchors = []
        for a, b in zip(cyc, cyc[1:]):
            locs = sorted(edges[(a, b)], key=lambda x: (x[0].rel, x[1]))
            anchors.append(locs[0][:2])
        f0, l0 = anchors[0]
        note = '; '.join('%s->%s: %s:%d' % (a, b, fx.rel, lx)
                         for (a, b), (fx, lx) in zip(zip(cyc, cyc[1:]), anchors))
        if len(comp) > len(cyc) - 1:
            note = 'one cycle among %d mutually dependent features (%s); %s' % (len(comp), ', '.join(comp), note)
        if weak:
            note = 'only through navigation or shared models; ' + note
        ctx.hit('ARCH-015', f0, l0, ' → '.join(cyc), note=note, severity='low' if weak else None,
                extra_files=[fx.rel for fx, _ in anchors])


# ---- code-pattern rules ---------------------------------------------------
_JSON_DECODE_RE = re.compile(r'\bjsonDecode\s*\(')
# jsonDecode is I/O evidence only on a response/file body (A9)
_JSON_BODY_RE = re.compile(r'\bjsonDecode\s*\(\s*(?:await\s+)?[\w$.!?()\[\]\'"]*?(?:\.body\b|\.data\b|readAsString\w*\s*\(|'
                           r'\bresponse\w*\b|\bres\b|\bresp\b)')
_CTX_LOGIC_RE = re.compile(
    r'\bBuildContext\b|\bNavigator\.(?:of|push\w*|pop\w*)\s*\(|\bScaffoldMessenger\.of\s*\(|'
    r'\bshowDialog\s*[<(]|\bshowModalBottomSheet\s*[<(]|\bcontext\.(?:go|push)\s*[<(]')
_LOCATOR_RE = re.compile(r'\bGetIt\.I\b|\bGetIt\.instance\b|\bgetIt\s*[<(]|\bgetIt\.get\s*<|\bsl\s*<|'
                         r'\bsl\s*\(\s*\)|\blocator\s*<|\bGet\.find\s*<|'
                         r'\b\w*(?:ServiceLocator|Locator|Injector|ServiceProvider)\s*\.\s*(?:instance|I|get)\b')
_GETIT_ALIAS_RE = re.compile(r'(?m)^[ \t]*(?:(?:final|var|late[ \t]+final|const)[ \t]+)?(?:GetIt[ \t]+)?'
                             r'([A-Za-z_]\w*)[ \t]*=[ \t]*GetIt[ \t]*\.[ \t]*(?:I|instance)\b')
_SDK_TRANSPORT_TYPES = {
    'firebase_auth': {'User', 'UserCredential', 'AuthCredential', 'IdTokenResult'},
    'cloud_firestore': {'DocumentSnapshot', 'QuerySnapshot', 'QueryDocumentSnapshot', 'DocumentReference',
                        'CollectionReference'},
    'supabase_flutter': {'AuthResponse', 'PostgrestResponse', 'User', 'Session'},
    'supabase': {'AuthResponse', 'PostgrestResponse', 'User', 'Session'},
    'firebase_storage': {'TaskSnapshot', 'UploadTask', 'Reference'},
}
_PROVIDER_DECL_RE = re.compile(r'@riverpod\b|@Riverpod\s*\(|\bProvider\s*(?:<[^;{}]*?>)?\s*(?:\.\w+\s*)?\(|'
                               r'\bNotifierProvider\b|\bChangeNotifierProvider\s*(?:<[^;{}]*?>)?\s*\(')
_EPHEMERAL_RE = re.compile(r'\b(?:TextEditingController|ScrollController|FocusNode|PageController|TabController)\s*\(')
_EVENT_FLAG_RE = re.compile(
    r'\bbool\s*\??\s+(_?(?:should(?:Show|Navigate|Pop|Open)\w*|navigate(?:[A-Z_]\w*)?|pop(?:[A-Z_]\w*)?|'
    r'open\w*(?:Dialog|Sheet)|show\w*(?:Snackbar|SnackBar|Toast|Dialog|Sheet|Error|Message)|is\w*Shown))\b(?!\s*[(<])')
_GETX_BUILD_RE = re.compile(r'\bGet\.(?:put|find|lazyPut)\s*[<(]')
_FORBIDDEN_NAME_RE = re.compile(r'(?:ViewModel|VM|Controller)$')
_TRANSPORT_TYPE_RE = re.compile(r'\bResponse\s*<|\bhttp\.Response\b|\bMap\s*<\s*String\s*,\s*dynamic\s*>|'
                                r'\b\w+(?:Dto|DTO|Response|Request)\b')


def _ev(f, line):
    return f.src_line(line)


def _decl_line(f, off, header, name, kw=''):
    """Line of a declaration's name (skips leading doc comments and annotations)."""
    pat = (r'\b%s\s+' % kw if kw else r'\b') + re.escape(name) + r'\b'
    m = None
    for m in re.finditer(pat, header):
        if kw:
            break
    if m:
        return f.line_of(off + m.start())
    return f.line_of(off + len(header) - len(header.lstrip()))


def rules_patterns(ctx):
    pres = ctx.pres
    files = ctx.files
    for f in files.values():
        st = struct_of(f)
        skel = f.skel
        role = f.role
        is_ui = role in UI_ROLES
        if role == 'barrel':
            continue
        # ARCH-101 io-in-widget: hits inside widget/State classes or top-level code of a widget file;
        # in the composition root only inside widget classes (bootstrap I/O in main() is fine, A4)
        if f.widget_ranges:
            hits = [m for m in _IO_CALL_RE.finditer(skel)]
            io_cls = [rng for rng in f.widget_ranges if any(rng[0] <= m.start() < rng[1] for m in hits)]
            for m in _JSON_DECODE_RE.finditer(skel):
                if _JSON_BODY_RE.match(skel, m.start()) or in_ranges(m.start(), io_cls):
                    hits.append(m)
            prov = provider_ranges(f) if pres in ('riverpod', 'mvn') else []
            for m in sorted(hits, key=lambda x: x.start()):
                if in_ranges(m.start(), f.other_class_ranges) or in_ranges(m.start(), prov):
                    continue  # co-located providers are logic, not the widget (K3 A5)
                if f.layer == 'app' and not in_ranges(m.start(), f.widget_ranges):
                    continue
                ln = f.line_of(m.start())
                ctx.hit('ARCH-101', f, ln, _ev(f, ln))
        # ARCH-102 context-in-logic
        if role == 'logic' and f.layer != 'app':  # routing helpers in the composition root may navigate
            seen = set()
            lr = logic_class_ranges(f)  # A17: only inside logic class bodies
            acc = [(m.start(), _skip_balanced(skel, skel.index('(', m.start()), '(', ')') + 60)
                   for m in _ACCESSOR_RE.finditer(skel)]
            acc_reported = False
            for m in _CTX_LOGIC_RE.finditer(skel):
                if in_ranges(m.start(), f.widget_ranges) or not in_ranges(m.start(), lr):
                    continue
                ln = f.line_of(m.start())
                if ln in seen:
                    continue
                seen.add(ln)
                if in_ranges(m.start(), acc):  # C6: `static XCubit get(BuildContext c) => BlocProvider.of(c)`
                    if not acc_reported:
                        acc_reported = True
                        ctx.hit('ARCH-102', f, ln, _ev(f, ln), severity='low',
                                note='accessor; use context.read<X>() at call sites')
                    continue
                ctx.hit('ARCH-102', f, ln, _ev(f, ln))
        # ARCH-103 god-file
        n = len(f.lines) - (1 if f.lines and f.lines[-1] == '' else 0)
        limit = 400 if role == 'logic' else 500 if is_ui else 800
        if n > limit:
            ctx.hit('ARCH-103', f, 1, '%d lines (limit %d for %s)' % (n, limit, role if limit != 800 else 'any file'),
                    note='%d lines' % n)
        # ARCH-104 service-locator-in-ui
        if is_ui and pres != 'getx':
            di = di_site_ranges(f) if pres == 'bloc' else []
            seen = set()
            for m in list(_LOCATOR_RE.finditer(skel)) + list(ctx.locator_alias_re.finditer(skel) if ctx.locator_alias_re else []):
                if in_ranges(m.start(), di):
                    continue  # C5: bloc.md allows get_it at the BlocProvider(create:) site
                ln = f.line_of(m.start())
                if ln in seen:
                    continue
                seen.add(ln)
                ctx.hit('ARCH-104', f, ln, _ev(f, ln))
        # ARCH-105 global-mutable-state, ARCH-106 mutable-state-class
        for cls, header, off, term in st.members:
            if term not in ('=', ';'):
                continue
            pv = parse_var(header)
            if not pv:
                continue
            mods, typ, name = pv
            if mods & {'final', 'const', 'external'}:
                continue
            npos = re.search(r'\b%s\b\s*$' % re.escape(name), header)
            ln = f.line_of(off + (npos.start() if npos else len(header) - len(header.lstrip())))
            if cls is None or 'static' in mods:
                if re.search(r'@visibleForTesting\b', header):
                    continue  # a deliberate test seam
            if cls is None or ('static' in mods and not is_state_class(cls)):
                what = 'top-level variable %s' % name if cls is None else 'static field %s.%s' % (cls['name'], name)
                sev, extra = None, ''
                if not ctx.is_reassigned(f, name, off + len(header)):
                    sev, extra = 'low', '; never reassigned in lib/: declare it final/const'  # A5
                if cls is not None and re.match(r'_?instance$', name) and \
                        re.search(r'\b%s\b' % re.escape(cls['name']), typ or ''):
                    extra += '; singleton holder, see AP-singleton-abuse'
                if term == '=' and re.search(r'(?i)(?:password|passwd|secret|token|api_?key|private_?key)', name) and \
                        re.match(r"\s*r?['\"]", f.code[off + len(header) + 1:off + len(header) + 40]):
                    extra += '; possible hard-coded credential, see flutter-secure-defaults SEC-*'
                ctx.hit('ARCH-105', f, ln, _ev(f, ln), severity=sev, note=what + extra)
            elif role == 'state' and pres in ('mvn', 'bloc', 'riverpod', 'mvvm') and cls['kind'] == 'class' \
                    and not is_state_class(cls) and not is_widget_class(cls) and 'abstract' not in mods:
                ctx.hit('ARCH-106', f, ln, _ev(f, ln), note='%s.%s' % (cls['name'], name))
        # ARCH-107 repository-leaks-transport
        if role in ALL_REPO_ROLES and ctx.profile['repository_pattern']:
            sdk = set()
            for imp in f.imports:
                if imp['pkg'] in _SDK_TRANSPORT_TYPES and not re.search(r'\bas\s+\w+|\bhide\b', imp['evidence']):
                    sdk |= _SDK_TRANSPORT_TYPES[imp['pkg']]
            sdk -= ctx.declared_classes
            sdk_re = re.compile(r'\b(?:%s)\b' % '|'.join(sorted(sdk))) if sdk else None
            for cls, header, off, term in st.members:
                if cls is None or cls['kind'] != 'class':
                    continue
                pm = parse_method(header)
                if not pm:
                    continue
                ret, name, _getter = pm
                if name.startswith('_') or name == cls['name'] or not ret:
                    continue
                leak = [m.group() for m in _TRANSPORT_TYPE_RE.finditer(ret)
                        if m.group() not in ctx.record_typedefs]  # a project record typedef is a domain value
                if leak or (sdk_re and sdk_re.search(ret)):  # FN-7: SDK types
                    ln = _decl_line(f, off, header, name)
                    ctx.hit('ARCH-107', f, ln, _ev(f, ln), note='%s.%s returns %s' % (cls['name'], name, ret))
        # ARCH-109 ephemeral-state-in-provider
        if pres in ('riverpod', 'mvn', 'provider') and (role == 'logic' or _PROVIDER_DECL_RE.search(skel)):
            for m in _EPHEMERAL_RE.finditer(skel):
                if in_ranges(m.start(), f.widget_ranges):
                    continue
                ln = f.line_of(m.start())
                ctx.hit('ARCH-109', f, ln, _ev(f, ln))
        # ARCH-110 provider-init-from-widget
        if pres in ('riverpod', 'mvn'):
            for cls, name, header, off, b0, b1 in st.funcs:
                if name != 'initState' or cls is None:
                    continue
                for ln in _ref_read_calls(f, b0, b1):
                    ctx.hit('ARCH-110', f, ln, _ev(f, ln))
        # ARCH-111 event-flag-in-state
        if role == 'state' and pres in ('mvn', 'bloc', 'mvvm', 'riverpod'):
            for m in _EVENT_FLAG_RE.finditer(skel):
                if in_ranges(m.start(), f.widget_ranges):
                    continue
                ln = f.line_of(m.start())
                ctx.hit('ARCH-111', f, ln, _ev(f, ln), note=m.group(1))
        # ARCH-112 mvn-forbidden-naming (class declarations)
        if pres == 'mvn':
            for c in st.classes:
                if c['kind'] != 'class' or not _FORBIDDEN_NAME_RE.search(c['name']):
                    continue
                if c['name'].endswith('Controller') and any(
                        s.endswith('Controller') and not s.startswith('_$') for s in c['supers']):
                    continue  # a customised Flutter/animation controller
                ln = _decl_line(f, c['start'], c['raw_header'], c['name'], 'class')
                ctx.hit('ARCH-112', f, ln, _ev(f, ln), note='class %s' % c['name'])
        # ARCH-113 getx-in-build
        if pres == 'getx' and f.widget_ranges:
            for cls, name, header, off, b0, b1 in st.funcs:
                if name != 'build' or cls is None or not (is_widget_class(cls) or is_state_class(cls)):
                    continue
                for m in _GETX_BUILD_RE.finditer(skel, b0, b1):
                    ln = f.line_of(m.start())
                    ctx.hit('ARCH-113', f, ln, _ev(f, ln))
    # ARCH-112 folders (once per folder)
    if pres == 'mvn':
        seen = {}
        for f in sorted(files.values(), key=lambda x: x.rel):
            parts = f.rel.split('/')
            for i, p in enumerate(parts[:-1]):
                if p.lower() in ('controller', 'controllers', 'view_model', 'view_models', 'viewmodel', 'viewmodels'):
                    folder = '/'.join(parts[:i + 1]) + '/'
                    if folder not in seen:
                        seen[folder] = f
                        ctx.hit('ARCH-112', f, 1, 'folder %s' % folder, note='folder %s' % folder)
    # ARCH-108 concrete-repository-only (project-wide)
    if ctx.profile['clean_architecture'] or pres in ('mvn', 'mvvm'):
        abstract_names, concrete = set(), []
        for f in files.values():
            for c in struct_of(f).classes:
                if c['kind'] != 'class' or not c['name'].endswith('Repository'):
                    continue
                if c['mods'] & {'abstract', 'interface', 'sealed'}:
                    abstract_names.add(c['name'])
                else:
                    concrete.append((f, c))
        for f, c in concrete:
            if c['name'] in abstract_names:
                continue
            if any(s.endswith('Repository') or s in abstract_names for s in c['supers']):
                continue
            ln = _decl_line(f, c['start'], c['raw_header'], c['name'], 'class')
            ctx.hit('ARCH-108', f, ln, _ev(f, ln), note='class %s' % c['name'])


def _ref_read_calls(f, b0, b1):
    s = f.skel
    out = []
    # A12: callbacks that initState only registers run later, so they are not provider initialisation
    cb = []
    for m in re.finditer(r'\.\s*(?:addListener|listen|listenManual|subscribe|on[A-Z]\w*)\s*(?:<[^()]*>)?\s*\(|'
                         r'\b(?:on[A-Z]\w*)\s*:', s[b0:b1]):
        p = b0 + m.end() - 1
        if s[p] == '(':
            cb.append((p, _skip_balanced(s, p, '(', ')')))
        else:
            cb.append((p, _arg_end(s, p + 1)))
    for m in re.finditer(r'\bref\.read\s*\(', s[b0:b1]):
        if in_ranges(b0 + m.start(), cb):
            continue
        p = b0 + m.end() - 1
        e = _skip_balanced(s, p, '(', ')')
        tail = s[e:min(b1, e + 120)]
        if re.match(r'\s*(?:\.\s*[A-Za-z_]\w*\s*(?:<[^()]*>)?\s*\(|\()', tail):
            out.append(f.line_of(b0 + m.start()))
    return sorted(set(out))


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
# One report per import line (CONTRACTS section 18): (rule kept on a tie, the other rule)
_DEDUPE_PAIRS = (('ARCH-005', 'ARCH-008'), ('ARCH-012', 'ARCH-007'))


def dedupe_imports(hits):
    """Keep the higher-severity (on a tie, the more specific) hit of each pair on the same import line."""
    by = defaultdict(dict)
    for v in hits:
        by[(v['file'], v['line'], v['evidence'])][v['id']] = v
    drop = set()
    for group in by.values():
        for keep, other in _DEDUPE_PAIRS:
            if keep in group and other in group:
                a, b = group[keep], group[other]
                if SEV_ORDER[b['severity']] < SEV_ORDER[a['severity']]:
                    a, b = b, a
                drop.add(id(b))
                a['note'] = ('%s; also %s' % (a['note'], b['id'])) if a['note'] else 'also %s' % b['id']
    return [v for v in hits if id(v) not in drop]


def build_report(root, package, files, profile, features, ctx, scope):
    by_layer = defaultdict(int)
    for f in files.values():
        by_layer[f.layer] += 1
    order = ['domain', 'data', 'presentation', 'core', 'app', 'other']
    by_layer = {k: by_layer[k] for k in order if by_layer.get(k)}

    def in_scope(v):
        if scope is None:
            return True
        return v['file'] in scope or any(x in scope for x in v.get('_files', ()))

    seen = set()
    viol = []
    for v in sorted(dedupe_imports(ctx.hits), key=lambda v: (v['id'], v['file'], v['line'], v['evidence'])):
        key = (v['id'], v['file'], v['line'], v['evidence'])
        if key in seen or not in_scope(v):
            continue
        seen.add(key)
        v.pop('_files', None)
        viol.append(v)
    sup = []
    sseen = set()
    for s in sorted(ctx.suppressed, key=lambda s: (s['id'], s['file'], s['line'])):
        key = (s['id'], s['file'], s['line'])
        if key in sseen or (scope is not None and s['file'] not in scope):
            continue
        sseen.add(key)
        sup.append(s)
    return {
        'schema': SCHEMA,
        'root': root,
        'package': package or '',
        'profile': profile,
        'stats': {'files': len(files), 'by_layer': by_layer, 'features': features},
        'files': file_table(files),
        'violations': viol,
        'suppressed': sup,
    }


def file_table(files):
    """Per-file classification for other skills (CONTRACTS section 10). Generated files are already skipped."""
    out = []
    for rel in sorted(files):
        f = files[rel]
        names = []
        for c in struct_of(f).classes:
            if c['kind'] in ('class', 'mixin', 'enum') and c['name'] and c['name'] not in names:
                names.append(c['name'])
        out.append({'file': rel, 'layer': f.layer, 'role': f.role, 'feature': f.feature, 'classes': names})
    return out


# --------------------------------------------------------------------------
# Baseline and CI mode
# --------------------------------------------------------------------------
_WS_RE = re.compile(r'\s+')
_GOD_FILE_RE = re.compile(r'^\d+ lines\b')


def baseline_key(v):
    """Evidence normalised so that moving or editing other lines keeps the key stable."""
    key = _WS_RE.sub(' ', v.get('evidence') or '').strip()
    if v['id'] == 'ARCH-103':
        key = _GOD_FILE_RE.sub('N lines', key)  # the line count changes with every edit
    return key


def baseline_doc(violations):
    entries = [{'id': v['id'], 'file': v['file'], 'key': baseline_key(v)} for v in violations]
    entries.sort(key=lambda e: (e['file'], e['id'], e['key']))
    return {'schema': BASELINE_SCHEMA, 'entries': entries}


def read_baseline(path):
    """Return a Counter-like dict {(id, file, key): count}; raise ValueError on a bad file."""
    with open(path, encoding='utf-8') as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or doc.get('schema') != BASELINE_SCHEMA or \
            not isinstance(doc.get('entries'), list):
        raise ValueError('not a %s file' % BASELINE_SCHEMA)
    counts = defaultdict(int)
    for e in doc['entries']:
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) for k in ('id', 'file', 'key')):
            raise ValueError('entries need string id, file and key')
        counts[(e['id'], e['file'], e['key'])] += 1
    return counts


def apply_baseline(rep, counts, path):
    """Keep only violations beyond the baselined count per (id, file, key), in line order."""
    left = dict(counts)
    new, old = [], 0
    for v in sorted(rep['violations'], key=lambda v: (v['file'], v['line'], v['id'])):
        k = (v['id'], v['file'], baseline_key(v))
        if left.get(k, 0) > 0:
            left[k] -= 1
            old += 1
        else:
            new.append(v)
    keep = set(id(v) for v in new)
    rep['violations'] = [v for v in rep['violations'] if id(v) in keep]
    rep['baseline'] = {'file': path, 'entries': sum(counts.values()), 'new': len(new), 'baselined': old,
                       'fixed': sum(left.values())}


def ci_failures(violations, fail_on):
    lim = SEV_ORDER[fail_on]
    return [v for v in violations if SEV_ORDER.get(v['severity'], 9) <= lim]


def print_text(rep, maxn):
    p = rep['profile']
    out = ['== ARCHITECTURE PROFILE']
    out.append('  root: %s' % rep['root'])
    out.append('  package: %s' % (rep['package'] or '?'))
    out.append('  presentation: %s' % p['presentation'])
    out.append('  confidence: %s' % p['confidence'])
    out.append('  clean_architecture: %s' % str(p['clean_architecture']).lower())
    out.append('  repository_pattern: %s' % str(p['repository_pattern']).lower())
    out.append('  use_cases: %s' % str(p['use_cases']).lower())
    out.append('  layout: %s' % p['layout'])
    out.append('  state_management: %s' % (', '.join(p['state_management']) or 'none'))
    out.append('  di: %s' % (', '.join(p['di']) or 'none'))
    st = rep['stats']
    out.append('  files: %d (%s)' % (st['files'], ', '.join('%s %d' % kv for kv in st['by_layer'].items())))
    out.append('  features: %s' % (', '.join(st['features']) or 'none'))
    out.append('  signals: %s' % ('; '.join(p['signals']) or 'none'))
    out.append('')
    out.append('== ARCHITECTURE VIOLATIONS')
    groups = defaultdict(list)
    for v in rep['violations']:
        groups[(v['id'], v['severity'])].append(v)
    if not groups:
        out.append('  none')
    for (rid, sev), items in sorted(groups.items(), key=lambda kv: (SEV_ORDER.get(kv[0][1], 9), kv[0][0])):
        out.append('  [%s] %s (%s) x%d — %s' % (rid, items[0]['name'], sev, len(items), items[0]['message']))
        for v in items[:maxn]:
            out.append('      %s:%d  %s' % (v['file'], v['line'], v['evidence']))
        if len(items) > maxn:
            out.append('      ... %d more' % (len(items) - maxn))
    if rep['suppressed']:
        out.append('  suppressed: %d (see --json)' % len(rep['suppressed']))
    b = rep.get('baseline')
    if b is not None:
        line = '  summary: %d new, %d baselined' % (b['new'], b['baselined'])
        if b['fixed']:
            line += ' (%d baseline entries no longer found)' % b['fixed']
        out.append(line)
    c = rep.get('ci')
    if c is not None:
        out.append('  ci: %s (%d at or above %s)' % ('fail' if c['failed'] else 'pass', c['at_or_above'],
                                                    c['fail_on']))
    print('\n'.join(out))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write('arch_check.py: error: %s\n' % message)
        sys.exit(2)


def main(argv=None):
    ap = _Parser(prog='arch_check.py', description='Static architecture checker for Dart/Flutter (read-only).')
    ap.add_argument('root')
    ap.add_argument('--json', action='store_true', help='print the arch-profile@1 JSON instead of text')
    ap.add_argument('--files', help='file with project-relative paths; limits reported violations to them')
    ap.add_argument('--profile', default='auto', choices=('auto',) + PROFILES,
                    help='declared presentation architecture (overrides detection)')
    ap.add_argument('--max', type=int, default=5, help='example locations per rule in text mode (default 5)')
    ap.add_argument('--baseline', metavar='FILE', help='report only violations not recorded in this baseline')
    ap.add_argument('--write-baseline', metavar='FILE', help='write the current violations as a baseline, then exit 0')
    ap.add_argument('--ci', action='store_true', help='exit 1 if a reported violation is at or above --fail-on')
    ap.add_argument('--fail-on', default='high', choices=('high', 'medium', 'low'),
                    help='lowest severity that fails --ci (default high)')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    pub = os.path.join(root, 'pubspec.yaml')
    if not os.path.isfile(pub):
        sys.stderr.write('arch_check.py: error: no pubspec.yaml in %s\n' % root)
        return 2
    scope = None
    if a.files:
        try:
            with open(a.files, encoding='utf-8') as fh:
                scope = set()
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    if os.path.isabs(line):
                        line = os.path.relpath(line, root)
                    scope.add(os.path.normpath(line).replace(os.sep, '/'))
        except OSError as e:
            sys.stderr.write('arch_check.py: error: cannot read --files: %s\n' % e)
            return 2
    if a.max < 0:
        sys.stderr.write('arch_check.py: error: --max must be >= 0\n')
        return 2
    counts = None
    if a.baseline and not a.write_baseline:
        try:
            counts = read_baseline(a.baseline)
        except (OSError, ValueError) as e:
            sys.stderr.write('arch_check.py: error: cannot use --baseline %s: %s\n' % (a.baseline, e))
            return 2
    package, deps = parse_pubspec(pub)
    files = load_files(root, package)
    g = prepass(files)
    for f in files.values():
        classify(f, g)
    profile, features, has_domain = detect_profile(files, deps, a.profile, parse_path_deps(pub))
    ctx = Ctx(files, profile, package, has_domain)
    rules_imports(ctx)
    rules_patterns(ctx)
    rep = build_report(root, package, files, profile, features, ctx, scope)
    if a.write_baseline:
        doc = baseline_doc(rep['violations'])
        try:
            with open(a.write_baseline, 'w', encoding='utf-8') as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write('\n')
        except OSError as e:
            sys.stderr.write('arch_check.py: error: cannot write --write-baseline: %s\n' % e)
            return 2
        print('arch_check: wrote baseline %s (%d entries)' % (a.write_baseline, len(doc['entries'])))
        return 0
    if counts is not None:
        apply_baseline(rep, counts, a.baseline)
    elif a.ci:
        rep['baseline'] = {'file': None, 'entries': 0, 'new': len(rep['violations']), 'baselined': 0, 'fixed': 0}
    rc = 0
    if a.ci:
        bad = ci_failures(rep['violations'], a.fail_on)
        rep['ci'] = {'fail_on': a.fail_on, 'at_or_above': len(bad), 'failed': bool(bad)}
        rc = 1 if bad else 0
    if a.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        print_text(rep, a.max)
    return rc


if __name__ == '__main__':
    sys.exit(main())
