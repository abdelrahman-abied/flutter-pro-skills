#!/usr/bin/env python3
"""test_gaps.py: find untested units and test smells in a Dart / Flutter project.

Read-only, stdlib only (python3 >= 3.8). It maps every testable unit in lib/
(roles repository-impl, usecase, logic, source, service, view, widget) to the
test files under test/ that exercise it, ranks the untested ones by
architecture priority, and greps test/ for test smells (docs/CONTRACTS.md
section 11).

Roles (CONTRACTS.md section 18): `repository` counts like repository-impl;
`barrel`, `di` and unknown roles are not units; ChangeNotifier subclasses and
classic Riverpod notifiers are logic. Files holding only exception / value
types, dev stubs (`*Dev`, `Fake*`...), factories or providers are not units
(listed under stats.skipped).

Usage:
  python3 -I test_gaps.py <project-root> [--json] [--profile <p>] [--max <n>]

Classification comes from the sibling checker
../flutter-architecture/scripts/arch_check.py --json (its "files" array) when
it is installed. Otherwise this script falls back to its own path-based
classification and says so in the output.

A unit counts as tested when a test file
  1. mirrors its path      lib/a/b/x.dart -> test/a/b/x_test.dart (also test/<unit|widget|src>/a/b/...,
                           lib/src/a/x.dart -> test/a/x_test.dart, and x_widget_test.dart)
  2. matches its name      .../x_test.dart anywhere under test/ (x_impl -> x accepted; a trailing
                           _widget / _unit / _integration / _golden is stripped)
  3. imports it and uses it: constructs one of its concrete classes, calls one of
     its public top-level functions, or reads one of its providers (an import
     that only overrides or fakes it doesn't count).

Exit codes: 0 = report produced (gaps and smells never fail the run),
2 = usage or environment error (for example, no pubspec.yaml).
"""
import argparse
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/test-gaps@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')

# role -> (tier, gap id, severity, message)
GAP_RULES = {
    'repository-impl': (1, 'TEST-untested-repository', 'medium',
                        'Repository implementation with no test; test it against a fake source (mapping, errors, caching).'),
    'repository': (1, 'TEST-untested-repository', 'medium',
                   'Repository implementation with no test; test it against a fake source (mapping, errors, caching).'),
    'usecase': (1, 'TEST-untested-usecase', 'medium',
                'Use case with no test; test its rule with a fake repository.'),
    'logic': (2, 'TEST-untested-logic', 'medium',
              'Notifier / view model / bloc with no test; test its state transitions with faked dependencies.'),
    'source': (3, 'TEST-untested-source', 'low',
               'Data source with no test; test parsing and error mapping against a fake client or recorded fixtures.'),
    'service': (3, 'TEST-untested-service', 'low',
                'Service with no test; test it against a fake client or platform channel.'),
    'view': (4, 'TEST-untested-view', 'low',
             'Screen with no widget test; pump it with faked logic and assert each state renders.'),
    'widget': (5, 'TEST-untested-widget', 'info',
               'Widget with no widget test; cover it if it branches on its inputs.'),
}
UNIT_ROLES = tuple(GAP_RULES)
# roles that are never units, even when the file holds a notifier (section 18: barrel and di are skipped)
NEVER_UNIT_ROLES = ('barrel', 'di', 'repository-contract', 'generated')

SMELL_RULES = {
    'TEST-no-assertion': ('medium', 'Test has no expect/verify; it only fails on an exception, so it can pass while behaviour is wrong.'),
    'TEST-mock-of-sut': ('medium', 'Test mocks or fakes the class it is testing; it exercises the stub, not the code.'),
    'TEST-tests-the-mock': ('medium', 'Test stubs a method on a mock and then calls that same method on the mock; no code under test runs, so it can only test the mocking library.'),
    'TEST-real-delay': ('medium', 'Real wall-clock wait in a test (sleep / Future.delayed); slow and flaky. Use fakeAsync or tester.pump(duration).'),
    'TEST-real-network': ('medium', 'Real HTTP client in a unit test; it hits the network and is slow and flaky. Inject a fake client or adapter.'),
    'TEST-skip-no-reason': ('low', 'Test skipped without a reason; it rots silently. Use skip: \'<why and when to re-enable>\'.'),
    'TEST-giant-file': ('low', 'Test file over 800 lines; split it by unit or behaviour so failures point somewhere.'),
    'TEST-preview-only': ('info', 'Test renders and saves an image but asserts nothing; a golden (matchesGoldenFile) would catch regressions without a human looking.'),
}
SMELL_ORDER = ('TEST-no-assertion', 'TEST-mock-of-sut', 'TEST-tests-the-mock', 'TEST-real-delay', 'TEST-real-network',
               'TEST-skip-no-reason', 'TEST-giant-file', 'TEST-preview-only')
GIANT_LINES = 800

GENERATED_RE = re.compile(r'\.(g|gen|freezed|gr|mocks|config|chopper|pb|pbenum|pbjson|pbserver)\.dart$')
GENERATED_HEADER_RE = re.compile(r'GENERATED CODE - DO NOT MODIFY', re.I)


# --------------------------------------------------------------------------
# Lexing helpers
# --------------------------------------------------------------------------
def mask(src, keep_strings=False):
    """Blank out comments and string contents, keeping offsets and newlines.

    Quotes stay, so `'...'` becomes `'   '`. Good enough for regex work.
    """
    out = list(src)
    i, n = 0, len(src)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != '\n':
                out[k] = ' '

    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == '/' and i + 1 < n and src[i + 1] == '*':
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith('/*', j):
                    depth, j = depth + 1, j + 2
                elif src.startswith('*/', j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            blank(i, j)
            i = j
        elif c in '\'"':
            raw = i > 0 and src[i - 1] in 'rR' and (i < 2 or not (src[i - 2].isalnum() or src[i - 2] == '_'))
            q = src[i:i + 3] if src[i:i + 3] in ("'''", '"""') else c
            j = i + len(q)
            while j < n:
                if not raw and src[j] == '\\':
                    j += 2
                    continue
                if src.startswith(q, j):
                    break
                if len(q) == 1 and src[j] == '\n':
                    break
                j += 1
            if not keep_strings:
                blank(i + len(q), min(j, n))
            i = j + len(q)
        else:
            i += 1
    return ''.join(out)


def match_paren(masked, open_idx):
    """Index just past the bracket matching masked[open_idx] (one of ( [ {)."""
    pairs = {'(': ')', '[': ']', '{': '}'}
    stack = []
    for j in range(open_idx, len(masked)):
        ch = masked[j]
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in ')]}':
            if not stack or stack[-1] != ch:
                return j + 1
            stack.pop()
            if not stack:
                return j + 1
    return len(masked)


def line_of(text, idx):
    return text.count('\n', 0, idx) + 1


def line_text(text, idx):
    a = text.rfind('\n', 0, idx) + 1
    b = text.find('\n', idx)
    return text[a:len(text) if b < 0 else b].strip()


def read(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def lower_first(name):
    return name[:1].lower() + name[1:]


# --------------------------------------------------------------------------
# Project discovery
# --------------------------------------------------------------------------
def pubspec_info(root):
    text = read(os.path.join(root, 'pubspec.yaml'))
    m = re.search(r'^name:\s*([A-Za-z0-9_]+)', text, re.M)
    deps = set(re.findall(r'^\s{2,}([a-z0-9_]+)\s*:', text, re.M))
    return (m.group(1) if m else ''), deps


def path_packages(root):
    """Local packages this app depends on by `path:` (and packages/*/ with a pubspec), which test_gaps does not scan.

    [{name, path, test_files}] -- a calibration note (K2 P4): their own test/ folders are not credited.
    """
    out, seen = [], set()
    lines = read(os.path.join(root, 'pubspec.yaml')).splitlines()
    for k, ln in enumerate(lines):
        m = re.match(r'^(\s+)path:\s*[\'"]?([^\'"#\s]+)', ln)
        if not m:
            continue
        name = ''
        for j in range(k - 1, -1, -1):
            mm = re.match(r'^(\s*)([A-Za-z0-9_]+)\s*:\s*$', lines[j])
            if mm and len(mm.group(1)) < len(m.group(1)):
                name = mm.group(2)
                break
        path = os.path.normpath(m.group(2)).replace(os.sep, '/')
        if name and path not in seen:
            seen.add(path)
            out.append((name, path))
    pk = os.path.join(root, 'packages')
    if os.path.isdir(pk):
        for d in sorted(os.listdir(pk)):
            rel = 'packages/' + d
            if rel not in seen and os.path.isfile(os.path.join(pk, d, 'pubspec.yaml')):
                seen.add(rel)
                out.append((d, rel))
    res = []
    for name, path in out:
        full = os.path.join(root, path)
        if not os.path.isfile(os.path.join(full, 'pubspec.yaml')):
            continue
        n = sum(1 for t in walk_dart(full, 'test') if t.endswith('_test.dart'))
        res.append({'name': name, 'path': path, 'test_files': n})
    return res


def walk_dart(root, top):
    base = os.path.join(root, top)
    out = []
    for d, dirs, files in os.walk(base):
        dirs[:] = sorted(x for x in dirs if not x.startswith('.') and x not in ('build', 'generated'))
        for f in sorted(files):
            if f.endswith('.dart'):
                out.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/'))
    return out


def is_generated(rel, text=None):
    if GENERATED_RE.search(rel) or '/generated/' in rel or os.path.basename(rel).startswith(('app_localizations', 'messages_')):
        return True
    if text is not None and GENERATED_HEADER_RE.search(text[:400]):
        return True
    return False


# --------------------------------------------------------------------------
# Classification: arch_check (preferred) or a minimal fallback
# --------------------------------------------------------------------------
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


def classify_with_arch_check(root, profile):
    here = os.path.dirname(os.path.abspath(__file__))
    checker = os.path.normpath(os.path.join(here, '..', '..', 'flutter-architecture', 'scripts', 'arch_check.py'))
    if not os.path.isfile(checker):
        return None, ('fallback', 'flutter-architecture skill not installed; path-based roles')
    cmd = [sys.executable or 'python3', '-I', checker, root, '--json']
    if profile and profile != 'auto':
        cmd += ['--profile', profile]
    try:
        data = _fps_arch_json(root, profile)
        if data is None:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
            data = json.loads(res.stdout.decode('utf-8', 'replace'))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, ('fallback', 'arch_check.py failed to run; path-based roles')
    if 'files' not in data:
        return None, ('fallback', 'arch_check.py has no "files" array; path-based roles')
    return data, ('arch_check', '../flutter-architecture/scripts/arch_check.py')


LAYER_SEGS = [
    ('domain', ('domain',)),
    ('data', ('data', 'models', 'services', 'repositories', 'api', 'datasources', 'data_sources')),
    ('presentation', ('presentation', 'ui', 'view', 'views', 'screens', 'pages', 'widgets', 'widget')),
    ('app', ('app', 'di', 'injection', 'router', 'routes', 'routing')),
    ('core', ('core', 'shared', 'common', 'utils')),
]
WIDGET_RE = re.compile(r'\bextends\s+(StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|HookWidget|HookConsumerWidget|State\s*<)')
LOGIC_RE = re.compile(r'\bextends\s+(_\$\w+|Bloc\s*<|Cubit\s*<|ChangeNotifier\b|GetxController\b|StateNotifier\s*<|AsyncNotifier\s*<|Notifier\s*<)|\bwith\s+ChangeNotifier\b')
REPO_DIRS = {'repositories', 'repository', 'repositories_impl', 'repository_impl', 'repos'}
REPO_SUFFIXES = ('_repository', '_repository_impl', '_repo_impl', '_repo')
REPO_IMPL_RE = re.compile(r'\bclass\s+\w+Repo(?:sitory)?Impl\b|\bimplements\s+(?:[\w<>,\s]*,\s*)?\w+Repository\b')
DI_NAME_RE = re.compile(r'(Factory|Module|Locator|Injector|ServiceLocator)$')


def fallback_role(rel, text):
    """Path- and content-based role, following CONTRACTS.md section 18 (barrel, di, repository)."""
    segs = [s.lower() for s in rel.split('/')[1:-1]]
    stem = os.path.basename(rel)[:-5].lower()
    sset = set(segs)
    masked = mask(text)
    layer = 'other'
    for name, keys in LAYER_SEGS:
        if sset & set(keys):
            layer = name
            break
    if rel.startswith('lib/main') and '/' not in rel[4:]:
        layer = 'app'
    feature = None
    parts = rel.split('/')
    for k, p in enumerate(parts[:-1]):
        if p in ('features', 'feature', 'modules') and k + 1 < len(parts) - 1:
            feature = parts[k + 1]
            break
    # barrel: only directives, no declarations
    body = re.sub(r'^\s*(?:library\b[^;]*|import\b[^;]*|export\b[^;]*|part\b[^;]*);', '', masked, flags=re.M)
    if re.search(r'^\s*(?:import|export)\b', masked, re.M) and not body.strip():
        return layer, 'barrel', feature
    classes = top_classes(masked)
    role = 'other'
    if sset & {'usecases', 'use_cases', 'usecase', 'use_case'} or stem.endswith(('_usecase', '_use_case')):
        role = 'usecase'
    elif sset & REPO_DIRS or stem.endswith(REPO_SUFFIXES) or REPO_IMPL_RE.search(masked):
        abstract = re.search(r'\b(abstract|interface|sealed)\s+(\w+\s+)*class\s+\w*Repo(sitory)?\b', masked)
        concrete = [c for c in classes if not c['abstract']]
        if REPO_IMPL_RE.search(masked) or any(re.search(r'\b(implements|extends)\s+\w*Repo', c['header']) for c in concrete):
            role = 'repository-impl'
        elif concrete and any(re.search(r'Repo(sitory)?\w*$', c['name']) for c in concrete):
            role = 'repository'
        elif abstract or layer == 'domain':
            role = 'repository-contract'
        else:
            role = 'repository'
    elif sset & {'sources', 'datasources', 'data_sources', 'api', 'remote', 'local'} or stem.endswith(('_source', '_api', '_client', '_datasource', '_data_source')):
        role = 'source'
    elif 'services' in sset or stem.endswith('_service'):
        role = 'service'
    elif sset & {'notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs', 'cubit', 'cubits', 'controller', 'controllers'} \
            or stem.endswith(('_notifier', '_view_model', '_viewmodel', '_bloc', '_cubit', '_controller', '_store')):
        role = 'logic'
    elif stem.endswith(('_state', '_event', '_events')) or 'state' in sset:
        role = 'state'
    elif sset & {'entities', 'entity'}:
        role = 'entity'
    elif sset & {'models', 'dto', 'dtos'} or stem.endswith(('_dto', '_request', '_response')):
        role = 'dto'
    elif sset & {'view', 'views', 'screens', 'pages'} or stem.endswith(('_screen', '_page', '_view')):
        role = 'view'
    elif sset & {'widget', 'widgets'}:
        role = 'widget'
    elif sset & {'di', 'injection'}:
        role = 'di'
    # ChangeNotifier and classic notifiers are logic in every profile (section 18), except repositories and Command*
    if role not in ('usecase', 'repository', 'repository-impl', 'repository-contract') and any(is_notifier_class(c) for c in classes):
        role = 'logic'
    if role in ('other', 'state', 'dto', 'entity'):
        if LOGIC_RE.search(masked) and role == 'other':
            role = 'logic'
        elif WIDGET_RE.search(masked) and role == 'other':
            role = 'view' if stem.endswith(('_screen', '_page', '_view')) else 'widget'
    # di: a *Factory / *Module / *Locator that only constructs objects, or top-level providers only
    if role in ('other', 'service', 'repository', 'repository-impl', 'source') and classes and \
            all(DI_NAME_RE.search(c['name']) for c in classes if not c['name'].startswith('_')) and \
            any(not c['name'].startswith('_') for c in classes):
        role = 'di'
    if role in ('logic', 'view', 'widget') and layer in ('other', 'core'):
        layer = 'presentation' if layer == 'other' else layer
    if layer == 'other':
        layer = {'usecase': 'domain', 'repository-impl': 'data', 'repository': 'data', 'source': 'data',
                 'service': 'data', 'di': 'app'}.get(role, 'other')
    return layer, role, feature


def fallback_profile(root, deps, lib_files, texts):
    dirs = set()
    for rel in lib_files:
        dirs.update(s.lower() for s in rel.split('/')[1:-1])
    riverpod = bool(deps & {'flutter_riverpod', 'riverpod', 'hooks_riverpod', 'riverpod_annotation'})
    notifier_classes = sum(len(re.findall(r'class\s+\w+Notifier\s+extends\s+_\$', t)) for t in texts.values())
    vm = dirs & {'view_model', 'view_models', 'viewmodel', 'viewmodels'}
    if riverpod and ('notifier' in dirs or 'notifiers' in dirs or notifier_classes >= 3) and not vm:
        p = 'mvn'
    elif 'get' in deps and any('GetxController' in t for t in texts.values()):
        p = 'getx'
    elif vm:
        p = 'mvvm'
    elif deps & {'bloc', 'flutter_bloc'}:
        p = 'bloc'
    elif 'provider' in deps:
        p = 'provider'
    elif riverpod:
        p = 'riverpod'
    else:
        p = 'setstate'
    clean = bool(dirs & {'domain'}) and bool(dirs & {'data'}) and bool(dirs & {'usecases', 'use_cases', 'entities'})
    return {'presentation': p, 'clean_architecture': clean, 'confidence': 'low',
            'signals': ['fallback classification from pubspec dependencies and folder names']}


# --------------------------------------------------------------------------
# Unit symbols
# --------------------------------------------------------------------------
# `class const Foo(...)` / `class Foo(...)`: Dart 3.13 primary constructors (lichess)
CLASS_DECL_RE = re.compile(r'^[ \t]*((?:(?:abstract|base|final|interface|sealed|mixin)\s+)*)class\s+(?:const\s+)?([A-Za-z_]\w*)', re.M)
RIVERPOD_FN_RE = re.compile(r'@[Rr]iverpod\b(?:\([^)]*\))?\s*(?:[\w<>,?\s]+?\s+)?([a-z]\w*)\s*\(\s*(?:\w*Ref)\b')
RIVERPOD_CLASS_RE = re.compile(r'@[Rr]iverpod\b(?:\([^)]*\))?\s*class\s+([A-Z]\w*)')
MANUAL_PROVIDER_RE = re.compile(r'^\s*final\s+([a-z]\w*Provider)\s*=', re.M)
BRANCH_RE = re.compile(r'\b(if|case|catch|for|while)\b|\?\?|&&|\|\|')
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'return', 'main', 'build', 'super', 'this', 'assert', 'print'}


def unit_symbols(root, rel, text, masked):
    """Return (concrete classes, abstract classes, top-level functions, providers)."""
    concrete, abstract = [], []
    for m in CLASS_DECL_RE.finditer(masked):
        mods, name = m.group(1), m.group(2)
        if name.startswith('_'):
            continue
        if re.search(r'\b(abstract|interface|sealed)\b', mods) or 'mixin' in mods:
            abstract.append(name)
        else:
            concrete.append(name)
    funcs = [name for name, top, _ in function_bodies(masked)
             if top and name[:1].islower() and name not in KEYWORDS]
    providers = set(MANUAL_PROVIDER_RE.findall(masked))
    for name in RIVERPOD_FN_RE.findall(masked):
        providers.add(name + 'Provider')
    for name in RIVERPOD_CLASS_RE.findall(masked):
        providers.add(lower_first(name) + 'Provider')
        if name.endswith('Notifier') and len(name) > 8:
            providers.add(lower_first(name[:-8]) + 'Provider')
    gen = os.path.join(root, rel[:-5] + '.g.dart')
    if os.path.isfile(gen):
        providers.update(n for n in re.findall(r'^final\s+([a-z]\w*)\s*=', read(gen), re.M) if n.endswith('Provider'))
    funcs = [f for f in funcs if f + 'Provider' not in providers]
    return sorted(set(concrete)), sorted(set(abstract)), sorted(set(funcs)), sorted(providers)


# --------------------------------------------------------------------------
# Class-level content checks (unit refinement)
# --------------------------------------------------------------------------
WIDGET_BASE_RE = re.compile(r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|HookWidget|'
                            r'HookConsumerWidget|StatefulHookWidget|StatefulHookConsumerWidget|InheritedWidget|'
                            r'InheritedNotifier|InheritedModel|LeafRenderObjectWidget|SingleChildRenderObjectWidget|'
                            r'MultiChildRenderObjectWidget|CustomPainter|CustomClipper|State\s*<|ConsumerState\s*<)')
NOTIFIER_BASE_RE = re.compile(r'\bextends\s+(?:ChangeNotifier\b|(?:AutoDispose)?(?:Family)?(?:Async|Stream)?Notifier\s*<|'
                              r'StateNotifier\s*<)|\bwith\s+(?:[\w<>,\s]*,\s*)?ChangeNotifier\b')
EXCEPTION_RE = re.compile(r'(Exception|Error|Failure|Failures)$')
EXCEPTION_BASE_RE = re.compile(r'\b(?:extends|implements|with)\s+(?:[\w<>,\s]*,\s*)?\w*(?:Exception|Error|Failure)\b')
VALUE_METHODS = {'toString', 'copyWith', 'toJson', 'fromJson', 'toMap', 'fromMap', 'noSuchMethod'}
DEV_STUB_RE = re.compile(r'^(?:Fake|Mock|Stub|Dummy|Demo)[A-Z]|(?:Dev|Fake|Stub|Mock|Demo|Dummy)$')
DI_CLASS_RE = re.compile(r'(?:Factory|Module|Locator|Injector)$')
# `Foo(...)` only: `Foo.bar(...)` may be a static call (Either.tryCatch, Store.get), not a construction
CONSTRUCT_ONLY_RE = re.compile(r'^\s*(?:return\s+)?(?:const\s+|new\s+)?[A-Z]\w*\s*(?:<[^;]*?>)?\s*\([^;]*\)\s*;?\s*$', re.S)
DELEGATE_RE = re.compile(r'^\s*(?:return\s+)?(?:await\s+)?(?:this\.)?_?[a-z]\w*(?:\s*\.\s*[a-z]\w*)+\s*(?:<[^;]*?>)?\s*\([^;]*\)\s*;?\s*$', re.S)


def top_classes(masked):
    """[{name, mods, header, body, abstract}] for every class declaration."""
    out = []
    n = len(masked)
    for m in CLASS_DECL_RE.finditer(masked):
        j = m.end()
        k = j
        while k < n and masked[k] in ' \t\n':
            k += 1
        if k < n and masked[k] == '<':  # type parameters
            depth = 0
            while k < n:
                depth += {'<': 1, '>': -1}.get(masked[k], 0)
                k += 1
                if depth == 0:
                    break
        mm = re.match(r'\s*(?:\.\s*\w+\s*)?\(', masked[k:k + 200])
        if mm:  # primary constructor parameters
            k = match_paren(masked, k + mm.end() - 1)
        hb = re.search(r'[{;]', masked[k:])
        if not hb:
            continue
        open_idx = k + hb.start()
        header = masked[k:open_idx]
        if masked[open_idx] == '{':
            body = masked[open_idx + 1:match_paren(masked, open_idx) - 1]
        else:
            body = ''
        mods = m.group(1)
        out.append({'name': m.group(2), 'mods': mods, 'header': header, 'body': body,
                    'abstract': bool(re.search(r'\b(abstract|interface|sealed)\b', mods) or 'mixin' in mods)})
    return out


def is_widget_class(c):
    return bool(WIDGET_BASE_RE.search(c['header']))


def is_notifier_class(c):
    """ChangeNotifier subclasses (not *Repository / Command*) and classic Riverpod notifiers (section 18)."""
    if not NOTIFIER_BASE_RE.search(c['header']):
        return False
    if re.search(r'\bextends\s+(?:RouterDelegate|RouteInformationParser|RouteInformationProvider|BackButtonDispatcher|'
                 r'Listenable|ValueNotifier|TextEditingController|ScrollController|AnimationController)\b', c['header']):
        return False  # navigation plumbing and Flutter controllers are not app logic
    return not (re.search(r'Repository\w*$', c['name']) or re.match(r'_?Command', c['name']))


CONTROL_WORDS = {'if', 'for', 'while', 'switch', 'catch', 'return', 'super', 'this', 'assert', 'await', 'yield', 'throw'}


def class_methods(c):
    """(name, body) of the methods declared in a class body (build included), constructors excluded."""
    out = []
    body = c['body']
    for m in HELPER_HEAD_RE.finditer(body):
        name = m.group(2)
        if name in CONTROL_WORDS or name == c['name']:
            continue
        close = match_paren(body, m.end() - 1)
        mm = re.match(r'\s*(?:async\s*\*?|sync\s*\*)?\s*(\{|=>)', body[close:close + 40])
        if not mm:
            continue
        start = close + mm.end()
        if mm.group(1) == '{':
            end = match_paren(body, start - 1)
        else:
            end = body.find(';', start)
            end = len(body) if end < 0 else end
        out.append((name, body[start:end]))
    return out


def has_ctor_body(c):
    """A constructor with a block body or registered handlers (Bloc's on<E>(...))."""
    return bool(re.search(r'(?<![\w$.])' + re.escape(c['name']) + r'(?:\.\w+)?\s*\([^;]*?\)\s*(?::[^;{]*)?\{\s*\S', c['body'], re.S))


def strip_generics(text):
    prev = None
    while prev != text:
        prev, text = text, re.sub(r'<[^<>]*>', '', text)
    return text


def is_exception_class(c):
    """An Exception / Error / Failure type (by name or direct supertype; generic arguments ignored)."""
    if is_widget_class(c) or is_notifier_class(c):
        return False  # `class WeatherError extends StatelessWidget` is a widget
    return bool(EXCEPTION_RE.search(c['name']) or EXCEPTION_BASE_RE.search(strip_generics(c['header'])))


def is_value_class(c):
    """No methods beyond toString/copyWith/toJson..., and no branching: a data holder."""
    if is_widget_class(c) or is_notifier_class(c) or has_ctor_body(c):
        return False
    base = re.search(r'\bextends\s+([A-Za-z_]\w*)', c['header'])
    if base and base.group(1) not in ('Equatable', 'Object') and not EXCEPTION_RE.search(base.group(1)):
        return False  # a subclass of Bloc, Cubit, a service base... has inherited behaviour
    if re.search(r'\bwith\b', c['header']) and not re.search(r'\bwith\s+EquatableMixin\s*$', c['header'].strip() + ' '):
        return False
    if any(n not in VALUE_METHODS for n, _ in class_methods(c)):
        return False
    return not BRANCH_RE.search(re.sub(r'\b(?:operator\s*==|hashCode)\b[^;{]*(?:\{[^{}]*\}|=>[^;]*;)', '', c['body']))


def constructs_only(c):
    """Every method body only returns a new object (a factory / module with no behaviour)."""
    ms = class_methods(c)
    return all(not b.strip() or CONSTRUCT_ONLY_RE.match(b.strip().strip('{}')) for _, b in ms)


def thin_delegation(classes):
    """Every method of every class is one call on a collaborator (`=> _source.x()`), no branches."""
    ms = [b for c in classes for _, b in class_methods(c)]
    if not ms:
        return False
    return all(DELEGATE_RE.match(b.strip().strip('{}').strip()) for b in ms) and \
        not any(BRANCH_RE.search(c['body']) for c in classes)


DATA_ROLES = ('repository-impl', 'repository', 'source', 'service', 'usecase')


def refine_unit(role, masked, concrete, funcs, providers):
    """Content checks on a candidate unit. Returns (role, skip_reason or '', classes kept, thin).

    Applied to arch_check roles and fallback roles alike, so both classifiers
    give the same units (CONTRACTS.md section 18; calibration K1-T2/T3, K2-T1, K3-T3).
    """
    classes = top_classes(masked)
    public = [c for c in classes if not c['name'].startswith('_') and not c['abstract']]
    kept = [c['name'] for c in public]
    if role == 'logic' and classes and all(is_widget_class(c) for c in classes if not c['abstract']) and \
            any(not c['abstract'] for c in classes):
        role = 'widget'  # K3 A10: a *_controller.dart that only holds widgets
    if role in DATA_ROLES:
        stubs = [c for c in public if DEV_STUB_RE.search(c['name'])]
        di = [c for c in public if c not in stubs and (DI_CLASS_RE.search(c['name']) or
              (role != 'usecase' and not re.search(r'\b(?:extends|implements)\b', c['header'])
               and class_methods(c) and constructs_only(c) and not BRANCH_RE.search(c['body'])))]
        rest = [c for c in public if c not in stubs and c not in di]
        if not rest and not funcs and (stubs or di):
            return role, ('dev stub or fake' if stubs and not di else 'factory / composition (di)'), [], False
        kept = [c['name'] for c in rest]
        if role in ('repository-impl', 'repository', 'source', 'service') and not public and not funcs and providers \
                and not BRANCH_RE.search(masked):
            return role, 'providers only (di)', [], False
    if public and not funcs and not providers and \
            all(is_exception_class(c) or is_value_class(c) for c in public):
        return role, 'exception, value or contract types only', [], False
    if not kept and not funcs and not providers:
        return role, 'contract only (no executable code)', [], False
    thin = role in ('repository-impl', 'repository') and thin_delegation([c for c in public if c['name'] in kept])
    return role, '', kept, thin


def uses_symbol(masked_test, concrete, funcs, providers, any_reference=False):
    """True when the test constructs a concrete class, calls a function or reads a provider.

    any_reference (widgets and views): find.byType(X) and tester.widget<X>() count too.
    """
    tail = r'\b' if any_reference else r'\s*(?:<[^;(){}]*?>)?\s*(\(|\.\s*[a-z]\w*\s*\(|\.\s*[a-z]\w*\b)'
    for c in concrete:
        for m in re.finditer(r'(?<![\w$])' + re.escape(c) + tail, masked_test):
            before = masked_test[max(0, m.start() - 40):m.start()]
            if re.search(r'\b(implements|extends|with)\s+(?:[\w<>,\s]*,\s*)?$', before) or re.search(r'MockSpec\s*<\s*$', before):
                continue
            return True
    for f in funcs:
        if re.search(r'(?<![\w$.])' + re.escape(f) + r'\s*(?:<[^;(){}]*?>)?\s*\(', masked_test):
            return True
    for p in providers:
        for m in re.finditer(r'(?<![\w$])' + re.escape(p) + r'\b', masked_test):
            after = masked_test[m.end():m.end() + 200]
            if re.match(r'\s*(?:\([^()]*\))?\s*\.\s*override', after):
                continue
            return True
    return False


# --------------------------------------------------------------------------
# Import resolution
# --------------------------------------------------------------------------
IMPORT_RE = re.compile(r'^\s*(import|export)\s+[\'"]([^\'"]+)[\'"]', re.M)


def resolve(uri, from_rel, package):
    if uri.startswith('package:'):
        rest = uri[len('package:'):]
        pkg, _, path = rest.partition('/')
        return ('lib/' + path) if pkg == package else None
    if uri.startswith('dart:') or ':' in uri:
        return None
    p = os.path.normpath(os.path.join(os.path.dirname(from_rel), uri)).replace(os.sep, '/')
    return p


# --------------------------------------------------------------------------
# Test-file analysis
# --------------------------------------------------------------------------
TEST_CALL_RE = re.compile(r'(?<![\w$.])(test|testWidgets|blocTest|testGoldens|goldenTest|patrolTest|patrolWidgetTest)\s*(?:<[^;(){}]*?>)?\s*\(')
ASSERT_RE = re.compile(r'(?<![\w$])(expect|expectLater|expectAsync\d*|verify|verifyNever|verifyInOrder|verifyZeroInteractions|verifyNoMoreInteractions|fail|check|validate|migrateAndValidate|screenMatchesGolden|multiScreenGolden|matchesGoldenFile|expectGolden\w*)\s*(?:<[^;(){}]*?>)?\s*\(')
# expectX / verifyX / validateX helpers; drift's SchemaVerifier.migrateAndValidate throws on a mismatch (K3-T1)
ASSERT_PREFIX_RE = re.compile(r'(?<![\w$])_?(expect|verify|assert|check|ensure|should|must|validate)[A-Z_]\w*\s*(?:<[^;(){}]*?>)?\s*\(')
BLOCTEST_ASSERT_RE = re.compile(r'(?<![\w$])(expect|errors|verify)\s*:')
HELPER_HEAD_RE = re.compile(r'^([ \t]*)(?:[\w<>,?\[\]]+\s+)*?([A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\(', re.M)
CAPTURE_RE = re.compile(r'(?<![\w$])(toImage|toByteData|takeScreenshot|writeAsBytes\w*|captureScreenshot)\s*\(')
REAL_TAG_RE = re.compile(r'@Tags\s*\(\s*\[[^\]]*(integration|network|real|live|e2e|slow)', re.I)
REAL_PATH_SEGS = {'real', 'integration', 'e2e', 'live', 'network', 'manual'}
NOT_HELPERS = KEYWORDS | {'test', 'testWidgets', 'group', 'setUp', 'setUpAll', 'tearDown', 'tearDownAll', 'blocTest'}


def function_bodies(masked):
    """Yield (name, top_level, body) for function and method declarations."""
    for m in HELPER_HEAD_RE.finditer(masked):
        name = m.group(2)
        if name in NOT_HELPERS:
            continue
        close = match_paren(masked, m.end() - 1)
        rest = masked[close:close + 40]
        mm = re.match(r'\s*(?:async\s*\*?|sync\s*\*)?\s*(\{|=>)', rest)
        if not mm:
            continue
        start = close + mm.end()
        if mm.group(1) == '{':
            end = match_paren(masked, start - 1)
        else:
            end = masked.find(';', start)
            end = len(masked) if end < 0 else end
        yield name, not m.group(1), masked[start:end]


def assertion_helpers(masked, known_assert=(), known_capture=()):
    """(asserting helpers, image-capturing helpers) declared in this file.

    A helper asserts when its body calls expect/verify/fail (or an
    expectX/verifyX helper), or, for a top-level function, throws. It
    captures when it renders to an image. Both propagate through helpers that
    call helpers (in this file, or the known ones from shared test helpers).
    """
    bodies = list(function_bodies(masked))
    asserting, capturing = set(known_assert), set(known_capture)
    for name, top, body in bodies:
        if ASSERT_RE.search(body) or ASSERT_PREFIX_RE.search(body) or (top and re.search(r'(?<![\w$])throw\b', body)):
            asserting.add(name)
        if CAPTURE_RE.search(body):
            capturing.add(name)
    for _ in range(3):
        grew = False
        for name, top, body in bodies:
            if name not in asserting and calls_any(asserting, body):
                asserting.add(name)
                grew = True
            if name not in capturing and calls_any(capturing, body):
                capturing.add(name)
                grew = True
        if not grew:
            break
    return asserting - set(known_assert), capturing - set(known_capture)


def find_calls(masked, name_re):
    """Yield (name, start, open_paren_idx, end) for calls matched by name_re."""
    for m in name_re.finditer(masked):
        op = m.end() - 1
        yield m.group(1), m.start(), op, match_paren(masked, op)


def enclosing(spans, idx):
    best = None
    for s in spans:
        if s[1] <= idx < s[3] and (best is None or s[1] >= best[1]):
            best = s
    return best


def calls_any(names, body):
    if not names:
        return None
    return re.search(r'(?<![\w$])(' + '|'.join(re.escape(h) for h in sorted(names)) + r')\s*\(', body)


DURATION_MICROS = {'microseconds': 1, 'milliseconds': 1000, 'seconds': 1000000, 'minutes': 60000000}


def event_loop_flush(arg):
    """True for Duration.zero, `.zero`, Duration() and literal durations of at most 1 ms."""
    if re.fullmatch(r'(?:const\s+)?(?:Duration\s*)?\.\s*zero|(?:const\s+)?Duration\s*\(\s*\)', arg):
        return True
    m = re.fullmatch(r'(?:const\s+)?Duration\s*\((.*)\)', arg, re.S)
    if not m:
        return False
    total = 0
    for part in m.group(1).split(','):
        if not part.strip():
            continue
        pm = re.fullmatch(r'\s*(\w+)\s*:\s*(\d+)\s*', part)
        if not pm or pm.group(1) not in DURATION_MICROS:
            return False
        total += int(pm.group(2)) * DURATION_MICROS[pm.group(1)]
    return total <= 1000


STUB_CTX_RE = re.compile(r'(?<![\w$])(when|verify|verifyNever|verifyInOrder|untilCalled|reset|clearInteractions)\s*\(')
STUB_RE = re.compile(r'(?<![\w$])when\s*\(\s*(?:\(\s*\)\s*(?:=>|\{\s*return)\s*)?(?:await\s+)?([a-z_]\w*)\s*\.\s*([a-z_]\w*)\s*(?:<[^;(){}]*?>)?\s*\(')
MOCK_CTX_RE = re.compile(r'(?<![\w$])(when|verify|verifyNever|verifyInOrder|untilCalled|expect|expectLater|reset|clearInteractions)\s*\(')


def tests_the_mock(masked, calls):
    """(start, evidence) per test that stubs mock.m() and then calls mock.m() directly (K1 FN).

    The mock must never reach real code: it is not passed as an argument or
    assigned anywhere in the file (outside when/verify/expect).
    """
    stubs = {}
    for m in STUB_RE.finditer(masked):
        stubs.setdefault(m.group(1), set()).add(m.group(2))
    if not stubs:
        return []
    ctx = list(find_calls(masked, MOCK_CTX_RE))
    stub_ctx = list(find_calls(masked, STUB_CTX_RE))

    def in_ctx(idx, spans):
        return any(c[2] < idx < c[3] for c in spans)

    def escapes(var, here):
        """var reaches real code: passed or stored outside when/verify/expect, in this test or shared setup."""
        for m in re.finditer(r'(?<![\w$.])' + re.escape(var) + r'\b', masked):
            if in_ctx(m.start(), ctx) or any(c is not here and c[2] < m.start() < c[3] for c in calls):
                continue
            after = masked[m.end():m.end() + 3]
            before = masked[max(0, m.start() - 30):m.start()]
            if re.match(r'\s*(?:\.|\?\.|;|=[^=>])', after) or re.search(r'\b(?:late|final|var)\s+(?:[\w<>?]+\s+)?$', before) \
                    or re.search(r'[A-Z]\w*(?:<[^;]*?>)?\??\s+$', before):
                continue
            return True  # passed as an argument, put in a list, returned...
        return False

    out = []
    for kind, start, op, end in calls:
        body_hits = []
        for var, meths in stubs.items():
            for m in re.finditer(r'(?<![\w$.])' + re.escape(var) + r'\s*\.\s*(' + '|'.join(re.escape(x) for x in sorted(meths)) +
                                 r')\s*(?:<[^;(){}]*?>)?\s*\(', masked[:end]):
                if m.start() > op and not in_ctx(m.start(), stub_ctx):
                    body_hits.append((m.start(), var, m.group(1)))
        body_hits = [h for h in body_hits if not escapes(h[1], (kind, start, op, end))]
        if body_hits:
            h = min(body_hits)
            out.append((start, '%s.%s() is stubbed with when() and then called on the mock itself' % (h[1], h[2])))
    return out


def analyse_test(rel, text, sut_classes, helpers):
    masked = mask(text)
    smells = []
    lines = len(text.splitlines())
    calls = list(find_calls(masked, TEST_CALL_RE))
    own_assert, own_capture = assertion_helpers(masked, helpers[0], helpers[1])
    asserting = own_assert | helpers[0]
    capturing = own_capture | helpers[1]

    def add(rid, idx, evidence):
        smells.append({'id': rid, 'severity': SMELL_RULES[rid][0], 'file': rel, 'line': line_of(text, idx),
                       'evidence': evidence.strip()[:160], 'message': SMELL_RULES[rid][1]})

    # no assertion
    for kind, start, op, end in calls:
        body = masked[op + 1:end - 1]
        if not body.strip():
            continue
        ok = ASSERT_RE.search(body) or ASSERT_PREFIX_RE.search(body)
        if not ok and kind == 'blocTest':
            ok = BLOCTEST_ASSERT_RE.search(body)
        if not ok:
            ok = calls_any(asserting, body)
        if not ok and kind in ('testGoldens', 'goldenTest'):
            ok = True
        if not ok:
            nm = re.match(r'\s*([\'"]{1,3})(.*?)\1', text[op + 1:op + 300], re.S)
            label = "%s('%s')" % (kind, (nm.group(2) if nm else '').replace('\n', ' '))
            if CAPTURE_RE.search(body) or calls_any(capturing, body):
                add('TEST-preview-only', start, label)
            else:
                add('TEST-no-assertion', start, label)

    # real delays
    zones = list(find_calls(masked, re.compile(r'(?<![\w$])(fakeAsync|runAsync|run)\s*\(')))
    for m in re.finditer(r'(?<![\w$.])(?:io\.)?sleep\s*\(', masked):
        if enclosing(calls, m.start()):
            add('TEST-real-delay', m.start(), line_text(text, m.start()))
    for m in re.finditer(r'(?<![\w$])Future\s*(?:<[^;(){}]*?>)?\s*\.\s*delayed\s*\(', masked):
        arg_end = match_paren(masked, m.end() - 1)
        arg = masked[m.end():arg_end - 1]
        first = arg.split(',')[0].strip()
        if event_loop_flush(first):
            continue  # K3-T2: Duration.zero / .zero / <= 1 ms only yields to the event loop
        call = enclosing(calls, m.start())
        if call is None:
            continue
        zone = enclosing([z for z in zones if z[1] > call[1]], m.start())
        if call[0] in ('testWidgets', 'testGoldens', 'patrolWidgetTest', 'patrolTest', 'goldenTest'):
            if not (zone and zone[0] == 'runAsync'):
                continue  # fake clock: tester.pump drives it
        elif zone and zone[0] in ('fakeAsync', 'run'):
            continue
        add('TEST-real-delay', m.start(), line_text(text, m.start()))

    # real network
    segs = set(s.lower() for s in rel.split('/')[1:-1])
    exempt = (segs & REAL_PATH_SEGS) or REAL_TAG_RE.search(text) or \
        re.search(r'httpClientAdapter\s*=|DioAdapter\s*\(|HttpServer\s*\.\s*bind|HttpOverrides\s*\.\s*(runZoned|global)', masked)
    if not exempt:
        for m in re.finditer(r'(?<![\w$])(?:http\s*\.\s*Client\s*\(\s*\)|Dio\s*\(|HttpClient\s*\(\s*\)|IOClient\s*\(|RetryClient\s*\(\s*http\s*\.\s*Client)', masked):
            add('TEST-real-network', m.start(), line_text(text, m.start()))
        if re.search(r'^\s*import\s+[\'"]package:http/http\.dart[\'"]\s*;', text, re.M):
            for m in re.finditer(r'(?<![\w$.])Client\s*\(\s*\)', masked):
                add('TEST-real-network', m.start(), line_text(text, m.start()))

    # skip without a reason
    for m in re.finditer(r'(?<![\w$])skip\s*:\s*true\b|@Skip\s*\(\s*\)', masked):
        add('TEST-skip-no-reason', m.start(), line_text(text, m.start()))

    # mocks / fakes of the class under test
    if sut_classes:
        for m in re.finditer(r'\bclass\s+(\w+)\s+extends\s+(Mock|Fake|SmartFake|MockBloc|MockCubit)\b[^{;]*?\bimplements\s+([^{;]+)\{', masked):
            impls = [x.strip() for x in re.sub(r'<[^<>]*>', '', m.group(3)).split(',')]
            hit = [x for x in impls if x in sut_classes]
            if hit:
                add('TEST-mock-of-sut', m.start(), 'class %s extends %s implements %s' % (m.group(1), m.group(2), ', '.join(hit)))
        for m in re.finditer(r'@Generate(?:Nice)?Mocks\s*\(\s*\[([^\]]*)\]', masked):
            names = re.findall(r'MockSpec\s*<\s*(\w+)|(?<![\w<])([A-Z]\w*)(?![\w>])', m.group(1))
            hit = sorted({a or b for a, b in names if (a or b) in sut_classes})
            if hit:
                add('TEST-mock-of-sut', m.start(), '@GenerateMocks of %s' % ', '.join(hit))

    for start, evidence in tests_the_mock(masked, [c for c in calls if c[0] != 'group']):
        add('TEST-tests-the-mock', start, evidence)

    if lines > GIANT_LINES:
        add('TEST-giant-file', 0, '%d lines' % lines)
    return smells, len(calls), masked


# --------------------------------------------------------------------------
# Main analysis
# --------------------------------------------------------------------------
def analyse(root, profile_arg):
    package, deps = pubspec_info(root)
    lib_files_all = walk_dart(root, 'lib')
    test_files_all = walk_dart(root, 'test')
    integration = walk_dart(root, 'integration_test')
    texts = {}
    for rel in lib_files_all:
        t = read(os.path.join(root, rel))
        if not is_generated(rel, t):
            texts[rel] = t
    lib_files = sorted(texts)

    data, classifier = classify_with_arch_check(root, profile_arg)
    entries = {}
    if data is not None:
        prof = data.get('profile', {})
        profile = {'presentation': prof.get('presentation', 'unknown'),
                   'clean_architecture': bool(prof.get('clean_architecture')),
                   'confidence': prof.get('confidence', 'low'),
                   'signals': prof.get('signals', [])}
        for f in data.get('files', []):
            entries[f['file']] = (f.get('layer'), f.get('role'), f.get('feature'))
        # section 18: arch_check's files[] is the source of truth for scope (it drops generated files)
        if entries:
            lib_files = [rel for rel in lib_files if rel in entries]
    else:
        profile = fallback_profile(root, deps, lib_files, texts)
        if profile_arg and profile_arg != 'auto':
            profile['presentation'] = profile_arg
            profile['signals'] = ['declared with --profile']
    profile['classifier'], profile['classifier_note'] = classifier
    for rel in lib_files:
        if rel not in entries:
            entries[rel] = fallback_role(rel, texts[rel])
        elif entries[rel][1] not in UNIT_ROLES and entries[rel][1] not in NEVER_UNIT_ROLES:
            # an older arch_check (or an unknown role): ChangeNotifier / classic notifiers are logic (section 18)
            if any(is_notifier_class(c) for c in top_classes(mask(texts[rel]))):
                layer, _, feature = entries[rel]
                entries[rel] = ('presentation' if layer in (None, 'other') else layer, 'logic', feature)

    # export map (barrels) and the lib import graph
    exports, imports_of = {}, {}
    for rel in lib_files:
        ex, im = [], set()
        for kind, uri in IMPORT_RE.findall(mask_keep_strings(texts[rel])):
            r = resolve(uri, rel, package)
            if not r:
                continue
            im.add(r)
            if kind == 'export':
                ex.append(r)
        exports[rel], imports_of[rel] = ex, im

    def reach(rel, seen=None):
        seen = set() if seen is None else seen
        if rel in seen:
            return seen
        seen.add(rel)
        for e in exports.get(rel, ()):
            reach(e, seen)
        return seen

    # units
    units = []
    stems = {}
    skipped = []
    for rel in lib_files:
        layer, role, feature = entries[rel]
        if role not in UNIT_ROLES:
            continue
        text = texts[rel]
        masked = mask(text)
        if re.search(r'^\s*part\s+of\b', masked, re.M):
            continue
        concrete, abstract, funcs, providers = unit_symbols(root, rel, text, masked)
        role, reason, kept, thin = refine_unit(role, masked, concrete, funcs, providers)
        if reason:
            skipped.append({'file': rel, 'role': role, 'reason': reason})
            continue
        code_lines = sum(1 for ln in masked.split('\n') if ln.strip())
        units.append({'file': rel, 'role': role, 'layer': layer, 'feature': feature,
                      'classes': sorted(kept),
                      'abstract': abstract, 'functions': funcs, 'providers': providers,
                      'lines': code_lines, 'complexity': len(BRANCH_RE.findall(masked)), 'thin': thin,
                      'tested': False, 'tests': [], 'note': '', 'via': []})
        stems.setdefault(os.path.basename(rel)[:-5], []).append(len(units) - 1)

    # test files
    tests = [t for t in test_files_all if t.endswith('_test.dart') and not is_generated(t)]
    test_texts = {t: read(os.path.join(root, t)) for t in tests}
    by_path = {u['file']: k for k, u in enumerate(units)}
    mapping_counts = {'mirror': 0, 'name': 0, 'import': 0}
    weak, overridden = {}, {}

    def link(k, test, method):
        u = units[k]
        if any(x['file'] == test for x in u['tests']):
            return
        u['tests'].append({'file': test, 'method': method})
        u['tested'] = True

    sut_by_test = {}
    masked_tests = {}
    for t in tests:
        base = os.path.basename(t)[:-len('_test.dart')]
        tpath = t[len('test/'):]
        tdir = os.path.dirname(tpath)
        # K1-T1: login_widget_test.dart tests login.dart (also _unit, _integration, _golden)
        kind = re.search(r'_(widget|unit|integration|golden)$', base)
        bases = [base] + ([base[:kind.start()]] if kind and kind.start() > 0 else [])
        hint = kind.group(1) if kind else ''
        under = tpath.split('/', 1)
        # 1. mirror (test/a/x_test.dart -> lib/a/x.dart, lib/src/a/x.dart (K3-T4), lib/a/x_impl.dart)
        cands = []
        for b in bases:
            rest = (tdir + '/' if tdir else '') + b + '.dart'
            cands += ['lib/' + rest, 'lib/src/' + rest]
            if len(under) == 2 and under[0] in ('unit', 'widget', 'widgets', 'src', 'lib', 'unit_test', 'widget_test',
                                                 'unit_tests', 'widget_tests'):
                inner = rest.split('/', 1)[1]
                cands += ['lib/' + inner, 'lib/src/' + inner]
        hit = False
        for c in cands:
            for alt in (c, c[:-5] + '_impl.dart'):
                if alt in by_path:
                    link(by_path[alt], t, 'mirror')
                    sut_by_test.setdefault(t, set()).add(by_path[alt])
                    hit = True
            if hit:
                break
        # 2. name
        if not hit:
            for b in bases:
                for stem in (b, b + '_impl'):
                    ks = pick_by_name(stems.get(stem, []), units, t, hint)
                    for k in ks:
                        link(k, t, 'name')
                        sut_by_test.setdefault(t, set()).add(k)
                        hit = True
                if hit:
                    break
        # 3. import + use
        mt = mask(test_texts[t])
        masked_tests[t] = mt
        imported = set()
        for kind, uri in IMPORT_RE.findall(mask_keep_strings(test_texts[t])):
            r = resolve(uri, t, package)
            if r and r.startswith('lib/'):
                imported |= reach(r)
        for r in imported:
            k = by_path.get(r)
            if k is None or any(x['file'] == t for x in units[k]['tests']):
                continue
            u = units[k]
            if uses_symbol(mt, u['classes'], u['functions'], u['providers'], u['role'] in ('view', 'widget')):
                link(k, t, 'import')
            else:
                weak[k] = weak.get(k, 0) + 1
            if u['providers'] and re.search(r'(?<![\w$])(' + '|'.join(re.escape(x) for x in u['providers']) +
                                            r')\s*(?:\([^()]*\))?\s*\.\s*override', mt):
                overridden[k] = overridden.get(k, 0) + 1

    for u in units:
        for x in u['tests']:
            mapping_counts[x['method']] += 1

    # assertion helpers declared in non-test files under test/ (shared harnesses)
    helper_assert, helper_capture, helper_masks = set(), set(), []
    for h in test_files_all:
        if h.endswith('_test.dart') or is_generated(h):
            continue
        helper_masks.append(mask(read(os.path.join(root, h))))
    for _ in range(2):  # helpers that call helpers in other helper files
        for hm in helper_masks:
            a, c = assertion_helpers(hm, helper_assert, helper_capture)
            helper_assert |= a
            helper_capture |= c

    smells = []
    test_count = 0
    for t in tests:
        sut = set()
        for k in sut_by_test.get(t, ()):
            sut.update(units[k]['classes'])
        s, n, _ = analyse_test(t, test_texts[t], sut, (helper_assert, helper_capture))
        smells.extend(s)
        test_count += n
    order = {rid: k for k, rid in enumerate(SMELL_ORDER)}
    smells.sort(key=lambda s: (order[s['id']], s['file'], s['line']))

    # indirect reach: a tested unit (one hop up the lib import graph) imports this one
    tested_files = [u['file'] for u in units if u['tested']]
    for k, u in enumerate(units):
        if u['tested']:
            continue
        via = [] if overridden.get(k) else sorted(
            f for f in tested_files if u['file'] in imports_of.get(f, ()) or
            any(u['file'] in reach(x) for x in imports_of.get(f, ()) if exports.get(x)))
        u['via'] = via
        notes = []
        if via:
            notes.append('likely exercised indirectly through %s%s' % (via[0], ' (+%d more)' % (len(via) - 1) if len(via) > 1 else ''))
        if overridden.get(k):
            notes.append('its provider is overridden with a fake in %d test file(s)' % overridden[k])
        elif weak.get(k):
            notes.append('imported by %d test file(s) that never construct or read it' % weak[k])
        if u['role'] == 'usecase' and u['complexity'] == 0:
            notes.append('pass-through (no branches): a logic test that runs the real use case over a fake repository covers it')
        if u['thin']:
            notes.append('thin delegation (every method is one call, no branches): low value on its own; '
                         'a test of its caller over a fake source covers it')
        u['note'] = '; '.join(notes)

    # gaps, ranked by architecture tier, then branching before trivial, direct before indirect, then size
    untested = [u for u in units if not u['tested']]
    untested.sort(key=lambda u: (GAP_RULES[u['role']][0], u['thin'] or u['complexity'] == 0, bool(u['via']),
                                 -u['complexity'], -u['lines'], u['file']))
    gaps = []
    for rank, u in enumerate(untested, 1):
        tier, gid, sev, msg = GAP_RULES[u['role']]
        if u['thin']:
            sev = 'low'
        gaps.append({'rank': rank, 'id': gid, 'severity': sev, 'tier': tier, 'file': u['file'], 'role': u['role'],
                     'feature': u['feature'], 'lines': u['lines'], 'complexity': u['complexity'],
                     'indirect': u['via'], 'message': msg, 'note': u['note']})

    by_role = {}
    for role in UNIT_ROLES:
        rs = [u for u in units if u['role'] == role]
        if rs:
            tested = sum(1 for u in rs if u['tested'])
            by_role[role] = {'units': len(rs), 'tested': tested, 'pct': round(100.0 * tested / len(rs), 1)}
    total_tested = sum(1 for u in units if u['tested'])
    stats = {'root': os.path.abspath(root), 'package': package,
             'lib_files': len(lib_files), 'units': len(units), 'tested': total_tested,
             'coverage_pct': round(100.0 * total_tested / len(units), 1) if units else 0.0,
             'coverage_by_role': by_role, 'test_files': len(tests), 'tests': test_count,
             'integration_test_files': len(integration), 'mapping': mapping_counts,
             'smells': {rid: sum(1 for s in smells if s['id'] == rid) for rid in SMELL_ORDER},
             'skipped': skipped, 'path_packages': path_packages(root)}
    out_units = []
    for u in units:
        out_units.append({k: u[k] for k in ('file', 'role', 'layer', 'feature', 'classes', 'functions', 'providers',
                                            'lines', 'complexity', 'tested', 'tests', 'note')})
    return {'schema': SCHEMA, 'profile': profile, 'units': out_units, 'gaps': gaps, 'smells': smells, 'stats': stats}


def pick_by_name(ks, units, test, hint):
    """Disambiguate units sharing a file name: same feature, then the kind the test name says, then folders."""
    if len(ks) <= 1:
        return ks
    feat = [k for k in ks if units[k]['feature'] and ('/' + units[k]['feature'] + '/') in ('/' + test)]
    if len(feat) == 1:
        return feat
    if hint in ('widget', 'golden'):
        ui = [k for k in ks if units[k]['role'] in ('view', 'widget')]
        if len(ui) == 1:
            return ui
    elif hint == 'unit':
        nonui = [k for k in ks if units[k]['role'] not in ('view', 'widget')]
        if len(nonui) == 1:
            return nonui
    tsegs = set(test.split('/')[1:-1])
    score = [(len(tsegs & set(units[k]['file'].split('/')[1:-1])), k) for k in ks]
    best = max(sc for sc, _ in score)
    top = [k for sc, k in score if sc == best]
    return top if best > 0 and len(top) == 1 else []


def mask_keep_strings(text):
    """Comments blanked, strings kept: for reading import URIs."""
    return mask(text, keep_strings=True)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def text_report(r, max_n):
    p, st = r['profile'], r['stats']
    lines = ['== TEST GAPS']
    arch = p['presentation'] + (' + clean architecture' if p.get('clean_architecture') else '')
    lines.append('  root: %s' % st['root'])
    lines.append('  profile: %s (confidence %s)' % (arch, p.get('confidence', 'low')))
    lines.append('  classifier: %s (%s)' % (p['classifier'], p['classifier_note']))
    lines.append('  units: %d, tested %d (%.1f%%); test files: %d with %d tests; integration_test files: %d (not mapped)'
                 % (st['units'], st['tested'], st['coverage_pct'], st['test_files'], st['tests'], st['integration_test_files']))
    cov = ', '.join('%s %d/%d %.0f%%' % (role, v['tested'], v['units'], v['pct']) for role, v in st['coverage_by_role'].items())
    lines.append('  coverage by role: %s' % (cov or 'no units'))
    m = st['mapping']
    lines.append('  mapped by: mirror %d, name %d, import %d' % (m['mirror'], m['name'], m['import']))
    if st.get('skipped'):
        reasons = {}
        for x in st['skipped']:
            reasons[x['reason']] = reasons.get(x['reason'], 0) + 1
        lines.append('  not units: %d (%s)' % (len(st['skipped']), ', '.join('%s %d' % kv for kv in sorted(reasons.items()))))
    if st.get('path_packages'):
        lines.append('  path packages (not scanned; run test_gaps.py on each): %s' % ', '.join(
            '%s (%d test files)' % (x['path'], x['test_files']) for x in st['path_packages']))
    if not r['gaps']:
        lines.append('  no untested units')
    groups = {}
    for g in r['gaps']:
        groups.setdefault(g['id'], []).append(g)
    for gid, items in groups.items():
        lines.append('  [%s] (%s) x%d — %s' % (gid, items[0]['severity'], len(items), items[0]['message']))
        for g in items[:max_n]:
            extra = '  (%s, %d lines, %d branches)' % (g['role'], g['lines'], g['complexity'])
            note = ('  — ' + g['note']) if g['note'] else ''
            lines.append('      #%d %s%s%s' % (g['rank'], g['file'], extra, note))
        if len(items) > max_n:
            lines.append('      ... %d more' % (len(items) - max_n))
    lines.append('')
    lines.append('== TEST SMELLS')
    if not r['smells']:
        lines.append('  no smells found')
    for rid in SMELL_ORDER:
        items = [s for s in r['smells'] if s['id'] == rid]
        if not items:
            continue
        lines.append('  [%s] (%s) x%d — %s' % (rid, items[0]['severity'], len(items), items[0]['message']))
        for s in items[:max_n]:
            lines.append('      %s:%d  %s' % (s['file'], s['line'], s['evidence']))
        if len(items) > max_n:
            lines.append('      ... %d more' % (len(items) - max_n))
    return '\n'.join(lines) + '\n'


def main(argv):
    ap = argparse.ArgumentParser(prog='test_gaps.py', description='Find untested units and test smells (read-only).')
    ap.add_argument('root')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--profile', default='auto', choices=PROFILES)
    ap.add_argument('--max', type=int, default=5)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    root = os.path.abspath(args.root)
    if not os.path.isfile(os.path.join(root, 'pubspec.yaml')):
        sys.stderr.write('test_gaps.py: no pubspec.yaml in %s\n' % root)
        return 2
    if args.max < 0:
        sys.stderr.write('test_gaps.py: --max must be >= 0\n')
        return 2
    report = analyse(root, args.profile)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + '\n')
    else:
        sys.stdout.write(text_report(report, args.max))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
