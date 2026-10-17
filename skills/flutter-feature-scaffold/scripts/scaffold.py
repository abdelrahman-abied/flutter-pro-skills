#!/usr/bin/env python3
"""Scaffold a new Flutter feature in the architecture the project already uses.

    python3 -I scaffold.py <project-root> <feature_name>
        [--profile auto|mvn|mvvm|bloc|cubit|getx|provider|riverpod]
        [--clean] [--entity <Name>] [--write] [--force-dir]

The default is a DRY RUN: it prints the plan, every file it would create with an
outline of its declarations, the missing dependencies and the next commands.
`--write` creates the files and never overwrites one: an existing file is
skipped and reported. This is the only script in the flutter-pro-skills suite
that writes into a project, and only with `--write`. It never edits
pubspec.yaml and never runs pub, build_runner or the analyzer.

`auto` runs the sibling checker (../flutter-architecture/scripts/arch_check.py
--json) as a subprocess, then copies the project's conventions: layout, folder
names (singular vs plural), the Screen/Page/View suffix, Impl/Remote naming and
relative vs package imports. Without the checker it falls back to a built-in
minimal classification and says so.

Templates live in ../assets/templates/<group>/*.tmpl. Placeholders:
  {{feature}} snake_case   {{Feature}} UpperCamel   {{featureCamel}} lowerCamel
  {{Entity}} entity class  {{package}} pubspec name  {{import:<key>}} the import
  URI of another generated file   {{#flag}}...{{/flag}} / {{^flag}}...{{/flag}}
  optional sections (flags: clean, modern, privnamed, riverpod, and the injected
  client: dio or getconnect).

Python >= 3.8, stdlib only. Exit 0 when the plan is printed (or files are
written), 2 on a usage or environment error.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
TEMPLATES = os.path.join(SKILL, 'assets', 'templates')
ARCH_CHECK = os.path.join(os.path.dirname(SKILL), 'flutter-architecture', 'scripts', 'arch_check.py')

PATTERNS = ('mvn', 'mvvm', 'bloc', 'cubit', 'getx', 'provider', 'riverpod')

DART_RESERVED = {
    'abstract', 'as', 'assert', 'async', 'await', 'base', 'break', 'case', 'catch', 'class', 'const',
    'continue', 'covariant', 'default', 'deferred', 'do', 'dynamic', 'else', 'enum', 'export',
    'extends', 'extension', 'external', 'factory', 'false', 'final', 'finally', 'for', 'function',
    'get', 'hide', 'if', 'implements', 'import', 'in', 'interface', 'is', 'late', 'library', 'mixin',
    'new', 'null', 'of', 'on', 'operator', 'part', 'required', 'rethrow', 'return', 'sealed', 'set',
    'show', 'static', 'super', 'switch', 'sync', 'this', 'throw', 'true', 'try', 'type', 'typedef',
    'var', 'void', 'when', 'while', 'with', 'yield',
    # would collide with Flutter / Dart core names in generated classes
    'core', 'test', 'flutter', 'widget', 'state', 'error',
}

# Pattern canonical folder names (flutter-architecture/references/<pattern>.md).
CANONICAL = {
    'mvn': dict(logic='notifier', state='state', view='view', widget='widget', sources='sources'),
    'riverpod': dict(logic='providers', view='screens', widget='widgets', sources='sources'),
    'provider': dict(logic='notifiers', state='state', view='screens', widget='widgets', sources='services'),
    'mvvm': dict(logic='view_models', view='widgets', widget='widgets', sources='services',
                 entities='models', usecases='use_cases'),
    'bloc': dict(logic='bloc', view='view', widget='widgets', sources='data_providers'),
    'cubit': dict(logic='cubit', view='view', widget='widgets', sources='data_providers'),
    'getx': dict(logic='controllers', state='controllers', view='views', widget='widgets',
                 sources='providers', binding='bindings'),
}
CLEAN_DIRS = dict(entities='entities', repositories='repositories', usecases='usecases', models='models',
                  sources='datasources')
VIEW_SUFFIX = {'mvn': 'View', 'riverpod': 'Screen', 'provider': 'Screen', 'mvvm': 'Screen',
               'bloc': 'Page', 'cubit': 'Page', 'getx': 'View'}
LOGIC_SUFFIX = {'mvn': 'Notifier', 'riverpod': 'Notifier', 'provider': 'Notifier', 'mvvm': 'ViewModel',
                'bloc': 'Bloc', 'cubit': 'Cubit', 'getx': 'Controller'}
LOGIC_FILE_SUFFIX = {'Notifier': 'notifier', 'ViewModel': 'viewmodel', 'Bloc': 'bloc', 'Cubit': 'cubit',
                     'Controller': 'controller', 'Store': 'store'}

# Folder-name variants a project may use instead of the canonical one, per slot.
LOGIC_VARIANTS = {
    'mvn': ('notifier', 'notifiers'),
    'riverpod': ('providers', 'provider', 'notifiers', 'notifier', 'controllers', 'controller'),
    'provider': ('notifiers', 'notifier', 'providers', 'controllers', 'stores'),
    'mvvm': ('view_models', 'view_model', 'viewmodels', 'viewmodel'),
    'bloc': ('bloc', 'blocs'),
    'cubit': ('cubit', 'cubits'),
    'getx': ('controllers', 'controller'),
}
SLOT_VARIANTS = {
    'state': ('state', 'states'),
    'view': ('view', 'views', 'screens', 'screen', 'pages', 'page'),
    'widget': ('widget', 'widgets', 'components'),
    'sources': ('sources', 'source', 'datasources', 'datasource', 'data_sources', 'data_source'),
    'usecases': ('usecases', 'use_cases'),
    'entities': ('entities', 'entity'),
}
ROLE_SLOT = {'logic': 'logic', 'state': 'state', 'view': 'view', 'widget': 'widget', 'source': 'sources',
             'usecase': 'usecases', 'entity': 'entities'}
LOGIC_SUFFIX_VARIANTS = {'riverpod': ('Notifier', 'Controller'), 'provider': ('Notifier', 'Controller', 'Store')}


class UsageError(Exception):
    pass


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def upper_camel(snake):
    return ''.join(p[:1].upper() + p[1:] for p in snake.split('_') if p)


def lower_camel(snake):
    s = upper_camel(snake)
    return s[:1].lower() + s[1:]


def snake(camel):
    s = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', camel)
    s = re.sub(r'(?<=[A-Z])([A-Z][a-z])', r'_\1', s)
    return s.lower()


def read(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return ''


def validate_feature(name):
    if not re.match(r'^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$', name or ''):
        hint = snake(re.sub(r'[^A-Za-z0-9]+', '_', name or '')).strip('_')
        hint = re.sub(r'_+', '_', hint)
        raise UsageError('feature name %r must be snake_case (lowercase letters, digits, single underscores), '
                         'e.g. %r' % (name, hint or 'order_history'))
    if name in DART_RESERVED:
        raise UsageError('feature name %r is a Dart keyword or collides with a core name; pick a more '
                         'specific one (e.g. %r)' % (name, name + '_feature'))
    if len(name) > 40:
        raise UsageError('feature name %r is longer than 40 characters' % name)


def parse_pubspec(root):
    text = read(os.path.join(root, 'pubspec.yaml'))
    m = re.search(r'(?m)^name:\s*["\']?([A-Za-z0-9_]+)', text)
    deps, dev = set(), set()
    section = None
    for line in text.splitlines():
        if re.match(r'^\S', line):
            key = line.split(':', 1)[0].strip()
            section = key if key in ('dependencies', 'dev_dependencies') else None
            continue
        km = re.match(r'^  ([A-Za-z0-9_]+)\s*:', line)
        if km and section:
            (deps if section == 'dependencies' else dev).add(km.group(1))
    return (m.group(1) if m else None), deps, dev, text


def sdk_lower_bound(pubspec_text):
    """(major, minor) of the SDK constraint's lower bound, or None."""
    m = re.search(r'(?m)^environment:\s*\n(?:[ \t]+.*\n)*?[ \t]+sdk:\s*["\']?(?:\^|>=)\s*(\d+)\.(\d+)', pubspec_text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def riverpod_naming(root, pubspec_text):
    """Return ('modern'|'legacy', reason). riverpod_generator >= 3 strips a trailing `Notifier`."""
    lock = read(os.path.join(root, 'pubspec.lock'))
    m = re.search(r'(?m)^  riverpod_generator:\n(?:    .*\n)*?    version: "?(\d+)\.', lock)
    if m:
        major = int(m.group(1))
        return ('modern' if major >= 3 else 'legacy'), 'riverpod_generator %s.x in pubspec.lock' % major
    m = re.search(r'(?m)^\s+riverpod_generator:\s*["\']?[\^>=<~ ]*(\d+)\.', pubspec_text)
    if m:
        major = int(m.group(1))
        return ('modern' if major >= 3 else 'legacy'), 'riverpod_generator constraint %s.x in pubspec.yaml' % major
    return 'modern', 'riverpod_generator not resolved yet; assuming >= 3.0 (what `pub add` installs)'


# --------------------------------------------------------------------------
# Project profile: arch_check (preferred) or a built-in minimal fallback
# --------------------------------------------------------------------------
_CLASS_RE = re.compile(r'(?m)^(?:abstract\s+|final\s+|sealed\s+|base\s+|interface\s+|mixin\s+)*'
                       r'(?:class|mixin|enum)\s+([A-Za-z_]\w*)')


def walk_lib(root):
    out = []
    lib = os.path.join(root, 'lib')
    for dp, dns, fns in os.walk(lib):
        dns[:] = sorted(d for d in dns if not d.startswith('.') and d != 'generated')
        for fn in sorted(fns):
            if not fn.endswith('.dart') or re.search(r'\.(g|freezed|gr|mocks|config)\.dart$', fn):
                continue
            full = os.path.join(dp, fn)
            out.append((os.path.relpath(full, root).replace(os.sep, '/'), read(full)))
    return out


def fallback_role(rel, text):
    segs = rel.split('/')[1:-1]
    stem = rel.rsplit('/', 1)[-1][:-5]
    s = set(segs)
    if s & {'notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
            'cubit', 'cubits', 'controller', 'controllers'} or \
            stem.endswith(('_notifier', '_view_model', '_viewmodel', '_bloc', '_cubit', '_controller', '_store')):
        return 'logic'
    if stem.endswith('_state') or s & {'state', 'states'}:
        return 'state'
    if s & {'usecases', 'use_cases'}:
        return 'usecase'
    if s & {'entities'}:
        return 'entity'
    if stem.endswith('_repository_impl') or ('repositories' in s and 'data' in s and 'abstract' not in text):
        return 'repository-impl'
    if s & set(SLOT_VARIANTS['sources']) or stem.endswith(('_source', '_datasource', '_data_source', '_api')):
        return 'source'
    if stem.endswith(('_screen', '_page', '_view')) or s & {'views', 'screens', 'pages', 'view'}:
        return 'view'
    if s & {'widget', 'widgets'}:
        return 'widget'
    return 'other'


def fallback_feature(rel):
    segs = rel.split('/')
    for i, seg in enumerate(segs[:-2]):
        if seg in ('features', 'feature', 'modules'):
            return segs[i + 1]
    return None


def fallback_profile(root, deps):
    files = []
    for rel, text in walk_lib(root):
        files.append({'file': rel, 'role': fallback_role(rel, text), 'feature': fallback_feature(rel),
                      'classes': _CLASS_RE.findall(text), 'layer': None})
    segs = [set(f['file'].split('/')[1:-1]) for f in files]
    riverpod = deps & {'flutter_riverpod', 'hooks_riverpod', 'riverpod', 'riverpod_annotation'}
    pres = 'unknown'
    if riverpod and any(s & {'notifier', 'notifiers'} and 'presentation' in s for s in segs):
        pres = 'mvn'
    elif 'get' in deps:
        pres = 'getx'
    elif any(s & {'view_model', 'view_models', 'viewmodel', 'viewmodels'} for s in segs):
        pres = 'mvvm'
    elif deps & {'bloc', 'flutter_bloc'}:
        pres = 'bloc'
    elif 'provider' in deps:
        pres = 'provider'
    elif riverpod:
        pres = 'riverpod'
    top = {f['file'].split('/')[1] for f in files if f['file'].count('/') >= 2}
    feats = sorted({f['feature'] for f in files if f['feature']})
    layer_first = bool(top & {'data', 'domain', 'presentation', 'ui', 'screens', 'models', 'services'})
    layout = 'feature-first' if feats else 'layer-first'
    if feats and layer_first:
        layout = 'hybrid'
    clean = any('domain' in s for s in segs) and any('data' in s for s in segs) and \
        any(s & {'usecases', 'use_cases', 'entities'} for s in segs)
    signals = [] if (feats or layer_first) else ['flat lib/ (no feature or layer folders)']
    return {
        'package': None,
        'profile': {'presentation': pres, 'clean_architecture': clean, 'layout': layout,
                    'use_cases': any(s & {'usecases', 'use_cases'} for s in segs),
                    'confidence': 'low', 'signals': signals},
        'stats': {'features': feats},
        'files': files,
    }


def load_profile(root, profile_arg, deps):
    """Return (report, source_description)."""
    if os.path.isfile(ARCH_CHECK):
        cmd = [sys.executable, '-I', ARCH_CHECK, root, '--json']
        if profile_arg != 'auto':
            cmd += ['--profile', 'bloc' if profile_arg == 'cubit' else profile_arg]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if proc.returncode == 0:
                report = json.loads(proc.stdout.decode('utf-8'))
                source = 'arch_check'
                if not isinstance(report.get('files'), list):
                    report['files'] = fallback_profile(root, deps)['files']
                    source = 'arch_check (no per-file "files" array; folder conventions from a built-in scan)'
                return report, source
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return fallback_profile(root, deps), 'built-in scan (arch_check.py failed to run)'
    return fallback_profile(root, deps), ('built-in scan (flutter-architecture skill not installed: %s)'
                                          % os.path.relpath(ARCH_CHECK, root))


# --------------------------------------------------------------------------
# Conventions
# --------------------------------------------------------------------------
class Conventions:
    def __init__(self):
        self.layout = 'feature-first'
        self.features_root = 'lib/features'
        self.pres_dir = 'presentation'
        self.dirs = {}
        self.inferred = set()       # slots whose folder name came from the project
        self.view_suffix = 'View'
        self.impl_suffix = 'Impl'
        self.logic_suffix = 'Notifier'
        self.import_style = 'relative'
        self.entity_suffix = None   # None = pattern default; True/False = inferred
        self.global_data = False    # getx get_cli: lib/app/data shared by modules
        self.notes = []             # (what, value, why)


def majority(counter, allowed=None):
    items = [(k, v) for k, v in counter.most_common() if allowed is None or k in allowed]
    return (items[0][0], items[0][1], sum(v for _, v in items)) if items else (None, 0, 0)


def infer_conventions(root, report, pattern, package):
    c = Conventions()
    prof = report.get('profile') or {}
    files = report.get('files') or []
    signals = ' '.join(prof.get('signals') or [])
    flat = 'flat lib/' in signals or not files
    canon = dict(CANONICAL[pattern])
    c.dirs = canon
    c.view_suffix = VIEW_SUFFIX[pattern]
    c.logic_suffix = LOGIC_SUFFIX[pattern]
    c.impl_suffix = 'Remote' if pattern == 'mvvm' else 'Impl'

    # ---- layout
    if flat:
        if pattern == 'mvvm':
            c.layout, c.pres_dir = 'layer-first', 'ui'
            c.notes.append(('layout', 'layer-first (lib/ui, lib/data, lib/domain)',
                            'canonical for mvvm: lib/ has no feature or layer folders yet'))
        else:
            c.layout = 'feature-first'
            c.features_root = 'lib/app/modules' if pattern == 'getx' else 'lib/features'
            c.pres_dir = '' if pattern in ('bloc', 'cubit', 'getx') else 'presentation'
            c.notes.append(('layout', 'feature-first under %s' % c.features_root,
                            'canonical for %s: lib/ has no feature or layer folders yet' % pattern))
    else:
        layout = prof.get('layout') or 'feature-first'
        c.layout = 'layer-first' if layout == 'layer-first' else 'feature-first'
        if c.layout == 'feature-first':
            roots = Counter()
            pres = Counter()
            for f in files:
                feat = f.get('feature')
                if not feat:
                    continue
                segs = f['file'].split('/')
                if feat not in segs[:-1]:
                    continue
                i = segs.index(feat)
                roots['/'.join(segs[:i])] += 1
                nxt = segs[i + 1] if i + 1 < len(segs) - 1 else None
                if nxt in ('presentation', 'ui'):
                    pres[nxt] += 1
                elif nxt and nxt not in ('data', 'domain', 'di', 'core'):
                    pres[''] += 1
            root_dir = majority(roots)[0]
            c.features_root = root_dir or ('lib/app/modules' if pattern == 'getx' else 'lib/features')
            p, n, total = majority(pres)
            if p is not None:
                c.pres_dir = p
                c.notes.append(('presentation folder', p or '(none: role folders sit in the feature)',
                                'inferred from %d of %d existing feature files' % (n, total)))
            else:
                c.pres_dir = {'mvvm': 'ui', 'bloc': '', 'cubit': '', 'getx': ''}.get(pattern, 'presentation')
            c.notes.append(('layout', 'feature-first under %s' % c.features_root,
                            'arch profile layout: %s' % layout))
        else:
            top = Counter(f['file'].split('/')[1] for f in files if f['file'].count('/') >= 2)
            if top.get('ui') and not top.get('presentation'):
                c.pres_dir = 'ui'
            elif top.get('presentation'):
                c.pres_dir = 'presentation'
            else:
                c.pres_dir = 'ui' if pattern == 'mvvm' else 'presentation'
            c.notes.append(('layout', 'layer-first (lib/%s, lib/data, lib/domain)' % c.pres_dir,
                            'arch profile layout: layer-first'))
    c.global_data = pattern == 'getx' and c.layout == 'feature-first' and c.features_root.endswith('app/modules')

    # ---- folder names per slot
    by_slot = {}
    for f in files:
        slot = ROLE_SLOT.get(f.get('role'))
        if not slot:
            continue
        parent = f['file'].split('/')[-2] if f['file'].count('/') >= 2 else None
        if parent:
            by_slot.setdefault(slot, Counter())[parent] += 1
    for slot, counter in sorted(by_slot.items()):
        allowed = LOGIC_VARIANTS[pattern] if slot == 'logic' else SLOT_VARIANTS.get(slot)
        if slot == 'view' and pattern == 'mvvm':
            allowed = tuple(allowed) + ('widgets',)
        if slot in ('state',) and pattern == 'getx':
            continue
        name, n, total = majority(counter, allowed)
        if name and name != (c.dirs.get(slot) or CLEAN_DIRS.get(slot) or slot):
            c.dirs[slot] = name
            c.inferred.add(slot)
            c.notes.append(('%s folder' % slot, name + '/', 'inferred from %d of %d existing %s files'
                            % (n, total, slot)))
    if 'widget' in c.dirs and pattern == 'mvvm':
        c.dirs['widget'] = c.dirs['view']

    # ---- view suffix (from view file stems)
    vs = Counter()
    for f in files:
        if f.get('role') == 'view':
            stem = f['file'].rsplit('/', 1)[-1][:-5]
            for suf in ('screen', 'page', 'view'):
                if stem.endswith('_' + suf):
                    vs[suf.capitalize()] += 1
    name, n, total = majority(vs)
    if name and name != c.view_suffix:
        c.view_suffix = name
        c.notes.append(('view suffix', name, 'inferred from %d of %d existing view files' % (n, total)))

    # ---- repository implementation suffix
    rs = Counter()
    for f in files:
        if f.get('role') == 'repository-impl':
            stem = f['file'].rsplit('/', 1)[-1][:-5]
            if stem.endswith('_repository_impl'):
                rs['Impl'] += 1
            elif stem.endswith('_repository_remote'):
                rs['Remote'] += 1
    name, n, total = majority(rs)
    if name and name != c.impl_suffix:
        c.impl_suffix = name
        c.notes.append(('repository implementation', 'X' + 'Repository' + name,
                        'inferred from %d of %d existing implementations' % (n, total)))

    # ---- logic suffix (only where the pattern has no fixed vocabulary)
    if pattern in LOGIC_SUFFIX_VARIANTS:
        ls = Counter()
        for f in files:
            if f.get('role') == 'logic':
                for cls in f.get('classes') or []:
                    for suf in LOGIC_SUFFIX_VARIANTS[pattern]:
                        if cls.endswith(suf):
                            ls[suf] += 1
        name, n, total = majority(ls)
        if name and name != c.logic_suffix:
            c.logic_suffix = name
            c.notes.append(('logic suffix', name, 'inferred from %d of %d existing logic classes' % (n, total)))

    # ---- entity suffix
    es = Counter()
    for f in files:
        if f.get('role') == 'entity':
            for cls in f.get('classes') or []:
                es['suffix' if cls.endswith('Entity') else 'plain'] += 1
    name, n, total = majority(es)
    if name:
        c.entity_suffix = name == 'suffix'

    # ---- import style
    rel_n = pkg_n = 0
    for _, text in walk_lib(root):
        for uri in re.findall(r'(?m)^\s*(?:import|export)\s+[\'"]([^\'"]+)[\'"]', text):
            if package and uri.startswith('package:%s/' % package):
                pkg_n += 1
            elif not re.match(r'^[a-z]+:', uri):
                rel_n += 1
    if pkg_n > rel_n:
        c.import_style = 'package'
    if pkg_n or rel_n:
        c.notes.append(('imports', c.import_style, 'inferred: %d package vs %d relative own-package imports'
                        % (pkg_n, rel_n)))
    return c


def find_mvvm_utils(root):
    """Locate an existing Compass-shaped Command / Result, if any."""
    found = {}
    for rel, text in walk_lib(root):
        if 'result' not in found and re.search(r'\bsealed\s+class\s+Result\s*<', text) and \
                re.search(r'\bclass\s+Ok\s*<', text) and 'Result.ok' in text:
            found['result'] = rel
        if 'command' not in found and re.search(r'\bclass\s+Command0\s*<', text):
            found['command'] = rel
    return found


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------
class Plan:
    def __init__(self, pattern, clean, conv, feature, entity_base, package, naming):
        self.pattern, self.clean, self.conv = pattern, clean, conv
        self.f = feature
        self.files = []   # dicts: key, path, template, test(bool), shared(bool)
        F = upper_camel(feature)
        fc = lower_camel(feature)
        suffix_entity = pattern == 'mvn' or (clean and pattern != 'mvvm')
        if conv.entity_suffix is not None and pattern != 'mvvm' and suffix_entity:
            suffix_entity = conv.entity_suffix
        base = entity_base or F
        entity = base + 'Entity' if suffix_entity and not base.endswith('Entity') else base
        logic = F + conv.logic_suffix
        view = F + conv.view_suffix
        n = {
            'feature': feature, 'Feature': F, 'featureCamel': fc, 'package': package,
            'title': feature.replace('_', ' ').capitalize(), 'title_lc': feature.replace('_', ' '),
            'Entity': entity, 'entity': snake(entity),
            'Repository': F + 'Repository', 'RepositoryImpl': F + 'Repository' + conv.impl_suffix,
            'State': F + 'State', 'Event': F + 'Event', 'Logic': logic, 'View': view,
            'InnerView': F + 'View' if conv.view_suffix != 'View' else F + 'Body',
            'ListWidget': F + 'Widget' if pattern == 'mvn' else F + 'List',
        }
        # raw-data class names, per pattern vocabulary (dart-naming §12)
        if clean and pattern not in ('mvn', 'mvvm'):
            n['Source'], n['SourceImpl'] = F + 'RemoteDataSource', F + 'RemoteDataSourceImpl'
            n['sourceFn'] = fc + 'RemoteDataSource'
        elif pattern in ('mvn', 'riverpod'):
            n['Source'], n['SourceImpl'], n['sourceFn'] = F + 'Source', F + 'RemoteSource', fc + 'Source'
        elif pattern == 'provider':
            n['Source'], n['SourceImpl'], n['sourceFn'] = F + 'Service', F + 'RemoteService', fc + 'Service'
        elif pattern in ('bloc', 'cubit'):
            n['Source'], n['SourceImpl'], n['sourceFn'] = F + 'Api', 'Remote' + F + 'Api', fc + 'Api'
        elif pattern == 'getx':
            n['Source'], n['SourceImpl'], n['sourceFn'] = F + 'Provider', F + 'ApiProvider', fc + 'Provider'
        elif pattern == 'mvvm':
            n['Source'], n['SourceImpl'], n['sourceFn'] = F + 'ApiClient', F + 'ApiClient', fc + 'ApiClient'
        n['UseCase'] = F + 'LoadUseCase' if pattern == 'mvvm' else 'Fetch' + F + 'List'
        n['useCase'] = n['UseCase'][:1].lower() + n['UseCase'][1:]
        uses_uc = clean and pattern not in ('mvn', 'riverpod')
        if uses_uc:
            n['Dep'], n['dep'] = n['UseCase'], n['useCase']
            n['depCall'] = '_%s()' % n['useCase']
            n['fakeDep'] = '%s(Fake%s())' % (n['UseCase'], n['Repository'])
            n['failingDep'] = '%s(Fake%s(const NetworkFailure()))' % (n['UseCase'], n['Repository'])
        else:
            n['Dep'], n['dep'] = n['Repository'], fc + 'Repository'
            n['depCall'] = '_%sRepository.fetch%sList()' % (fc, F)
            n['fakeDep'] = 'Fake%s()' % n['Repository']
            n['failingDep'] = 'Fake%s(const NetworkFailure())' % n['Repository']
        # The injected HTTP client (flutter-secure-defaults secure-scaffold-checklist S-5): GetX keeps its own
        # GetConnect; every other pattern gets Dio, configured once in core/network.
        self.client = 'getconnect' if pattern == 'getx' else 'dio'
        n['Client'] = 'GetConnect' if self.client == 'getconnect' else 'Dio'
        n['responseBody'] = 'body' if self.client == 'getconnect' else 'data'
        self.naming_style, self.naming_reason = naming
        n['logicProvider'] = provider_name(logic, self.naming_style == 'modern')
        self.names = n
        self.flags = {'clean': clean, 'modern': self.naming_style == 'modern', 'privnamed': False,
                      'dio': self.client == 'dio', 'getconnect': self.client == 'getconnect',
                      'riverpod': pattern in ('mvn', 'riverpod')}
        self.dep_key = 'usecase' if uses_uc else 'repository'

    # ----- paths
    def d(self, slot):
        c = self.conv
        if slot in c.inferred:
            return c.dirs[slot]
        if self.clean and self.pattern not in ('mvn', 'mvvm') and slot in CLEAN_DIRS:
            return CLEAN_DIRS[slot]
        return c.dirs.get(slot) or slot

    def path(self, layer, slot, fname):
        c, f = self.conv, self.f
        dirname = self.d(slot) if slot else ''
        if c.layout == 'feature-first':
            if layer == 'di':
                parts = [c.features_root, f, 'di', fname]
            elif layer == 'root':   # composition-ish files kept out of the presentation layer
                parts = [c.features_root, f, dirname, fname]
            elif layer == 'presentation':
                parts = [c.features_root, f, c.pres_dir, dirname, fname]
            elif c.global_data:
                parts = ['lib/app', layer, dirname, fname]
            else:
                parts = [c.features_root, f, layer, dirname, fname]
        else:
            if layer == 'di':
                parts = ['lib/di', fname]
            elif layer == 'root':
                parts = ['lib', dirname, fname]
            elif layer == 'presentation':
                parts = ['lib', c.pres_dir or 'presentation', f, dirname, fname]
            else:
                parts = ['lib', layer, dirname, fname]
        return '/'.join(p for p in parts if p)

    def add(self, key, path, template, test=None, shared=False):
        self.files.append({'key': key, 'path': path, 'template': template, 'test': False, 'shared': shared})
        if test:
            self.files.append({'key': 't_' + key, 'path': test_path(path), 'template': test,
                               'test': True, 'shared': False})

    def core_dir(self):
        """Where the app-wide failure type and HTTP client go (get_cli apps keep everything under lib/app)."""
        return 'lib/app/core' if self.conv.global_data else 'lib/core'

    def feature_dir(self):
        c = self.conv
        if c.layout == 'feature-first':
            return '%s/%s' % (c.features_root, self.f)
        return 'lib/%s/%s' % (c.pres_dir or 'presentation', self.f)


def provider_name(cls, modern):
    base = cls[:-len('Notifier')] if modern and cls.endswith('Notifier') and cls != 'Notifier' else cls
    return base[:1].lower() + base[1:] + 'Provider'


def test_path(lib_path):
    return 'test/' + lib_path[len('lib/'):-len('.dart')] + '_test.dart'


def build_plan(pattern, clean, conv, feature, entity_base, package, naming, mvvm_utils):
    p = Plan(pattern, clean, conv, feature, entity_base, package, naming)
    f, n = feature, p.names
    lsuf = LOGIC_FILE_SUFFIX.get(conv.logic_suffix, snake(conv.logic_suffix))
    view_file = '%s_%s.dart' % (f, conv.view_suffix.lower())
    impl_file = '%s_repository_%s.dart' % (f, conv.impl_suffix.lower())

    # App-wide, created once and reused by later features: the typed failures every repository maps to, and
    # the one configured HTTP client (base URL, timeouts, auth) every remote source receives.
    core = p.core_dir()
    p.add('failure', core + '/error/failure.dart', 'core/failure.dart.tmpl', shared=True)
    if pattern == 'getx':
        p.add('http_client', core + '/network/api_client.dart', 'getx/api_client.dart.tmpl', shared=True)
    else:
        p.add('http_client', core + '/network/http_client.dart', 'core/http_client.dart.tmpl', shared=True)

    if pattern == 'mvn':
        p.add('entity', p.path('domain', 'entities', '%s.dart' % n['entity']), 'mvn/entity.dart.tmpl')
        p.add('repository', p.path('domain', 'repositories', '%s_repository.dart' % f), 'mvn/repository.dart.tmpl')
        p.add('usecase', p.path('domain', 'usecases', '%s_usecase.dart' % f), 'mvn/usecase.dart.tmpl',
              'mvn/usecase_test.dart.tmpl')
        p.add('request', p.path('data', 'models', '%s_request.dart' % f), 'mvn/request.dart.tmpl')
        p.add('response', p.path('data', 'models', '%s_response.dart' % f), 'mvn/response.dart.tmpl')
        p.add('repository_impl', p.path('data', 'repositories', impl_file), 'mvn/repository_impl.dart.tmpl',
              'mvn/repository_impl_test.dart.tmpl')
        p.add('source', p.path('data', 'sources', '%s_source.dart' % f), 'mvn/source.dart.tmpl')
        p.add('notifier', p.path('presentation', 'logic', '%s_notifier.dart' % f), 'mvn/notifier.dart.tmpl',
              'mvn/notifier_test.dart.tmpl')
        p.add('state', p.path('presentation', 'state', '%s_state.dart' % f), 'mvn/state.dart.tmpl')
        p.add('view', p.path('presentation', 'view', view_file), 'mvn/view.dart.tmpl', 'mvn/view_test.dart.tmpl')
        p.add('widget', p.path('presentation', 'widget', '%s_widget.dart' % f), 'mvn/widget.dart.tmpl')
        return p

    if pattern == 'mvvm':
        lf = conv.layout == 'layer-first'
        if 'result' in mvvm_utils:
            p.files.append({'key': 'result', 'path': mvvm_utils['result'], 'template': None, 'test': False,
                            'shared': True, 'reuse': True})
        else:
            p.add('result', 'lib/utils/result.dart', 'mvvm/result.dart.tmpl', shared=True)
        if 'command' in mvvm_utils:
            p.files.append({'key': 'command', 'path': mvvm_utils['command'], 'template': None, 'test': False,
                            'shared': True, 'reuse': True})
        else:
            p.add('command', 'lib/utils/command.dart', 'mvvm/command.dart.tmpl', shared=True)
        p.add('entity', p.path('domain', 'entities', '%s.dart' % n['entity']), 'clean/entity.dart.tmpl')
        svc = 'api/' if lf else ''
        p.add('api_model', p.path('data', 'sources', '%smodel/%s%s_api_model.dart' % (svc, f + '/' if lf else '', f)),
              'mvvm/api_model.dart.tmpl')
        p.add('source', p.path('data', 'sources', '%s%s_api_client.dart' % (svc, f)), 'mvvm/api_client.dart.tmpl')
        sub = f + '/' if lf else ''
        # With --clean the domain owns the contract, so the use case never imports data/.
        p.add('repository', p.path('domain' if clean else 'data', 'repositories', '%s%s_repository.dart' % (sub, f)),
              'mvvm/repository.dart.tmpl')
        p.add('repository_impl', p.path('data', 'repositories', sub + impl_file), 'mvvm/repository_impl.dart.tmpl',
              'mvvm/repository_impl_test.dart.tmpl')
        if clean:
            p.add('usecase', p.path('domain', 'usecases', '%s%s_load_use_case.dart' % (sub, f)),
                  'mvvm/usecase.dart.tmpl', 'mvvm/usecase_test.dart.tmpl')
        vm_file = '%s_%s.dart' % (f, 'viewmodel' if conv.logic_suffix == 'ViewModel' else lsuf)
        p.add('logic', p.path('presentation', 'logic', vm_file), 'mvvm/viewmodel.dart.tmpl',
              'mvvm/viewmodel_test.dart.tmpl')
        p.add('view', p.path('presentation', 'view', view_file), 'mvvm/view.dart.tmpl', 'mvvm/view_test.dart.tmpl')
        p.add('list', p.path('presentation', 'widget', '%s_list.dart' % f), 'shared/list.dart.tmpl')
        return p

    # data + domain for riverpod / provider / bloc / cubit / getx
    if clean:
        p.add('entity', p.path('domain', 'entities', '%s.dart' % n['entity']), 'clean/entity.dart.tmpl')
        p.add('repository', p.path('domain', 'repositories', '%s_repository.dart' % f), 'clean/repository.dart.tmpl')
        p.add('usecase', p.path('domain', 'usecases', '%s.dart' % snake(n['UseCase'])), 'clean/usecase.dart.tmpl',
              'clean/usecase_test.dart.tmpl')
        p.add('dto', p.path('data', 'models', '%s_dto.dart' % f), 'clean/dto.dart.tmpl')
        p.add('source', p.path('data', 'sources', '%s_remote_data_source.dart' % f), 'clean/data_source.dart.tmpl')
        p.add('repository_impl', p.path('data', 'repositories', impl_file), 'clean/repository_impl.dart.tmpl',
              'clean/repository_impl_test.dart.tmpl')
    else:
        p.add('entity', p.path('data', 'models', '%s.dart' % n['entity']), 'shared/model.dart.tmpl')
        src_file = '%s_%s.dart' % (f, {'riverpod': 'source', 'provider': 'service', 'bloc': 'api', 'cubit': 'api',
                                        'getx': 'provider'}[pattern])
        p.add('source', p.path('data', 'sources', src_file), 'shared/source.dart.tmpl')
        p.add('repository', p.path('data', 'repositories', '%s_repository.dart' % f), 'shared/repository.dart.tmpl')
        p.add('repository_impl', p.path('data', 'repositories', impl_file), 'shared/repository_impl.dart.tmpl',
              'shared/repository_impl_test.dart.tmpl')

    if pattern == 'riverpod':
        p.add('di', p.path('di', None, '%s_providers.dart' % f), 'riverpod/providers.dart.tmpl')
        p.add('notifier', p.path('presentation', 'logic', '%s_%s.dart' % (f, lsuf)), 'riverpod/notifier.dart.tmpl',
              'riverpod/notifier_test.dart.tmpl')
        p.add('view', p.path('presentation', 'view', view_file), 'riverpod/view.dart.tmpl',
              'riverpod/view_test.dart.tmpl')
    elif pattern == 'provider':
        p.add('notifier', p.path('presentation', 'logic', '%s_%s.dart' % (f, lsuf)), 'provider/notifier.dart.tmpl',
              'provider/notifier_test.dart.tmpl')
        p.add('state', p.path('presentation', 'state', '%s_state.dart' % f), 'provider/state.dart.tmpl')
        p.add('view', p.path('presentation', 'view', view_file), 'provider/view.dart.tmpl',
              'provider/view_test.dart.tmpl')
    elif pattern in ('bloc', 'cubit'):
        kind = pattern
        p.add('logic', p.path('presentation', 'logic', '%s_%s.dart' % (f, kind)), '%s/%s.dart.tmpl' % (kind, kind),
              '%s/%s_test.dart.tmpl' % (kind, kind))
        if kind == 'bloc':
            p.add('event', p.path('presentation', 'logic', '%s_event.dart' % f), 'bloc/event.dart.tmpl')
        p.add('state', p.path('presentation', 'logic', '%s_state.dart' % f), 'bloc/state.dart.tmpl')
        p.add('view', p.path('presentation', 'view', view_file), '%s/view.dart.tmpl' % kind,
              'bloc/view_test.dart.tmpl')
        n['partOf'] = '%s_%s.dart' % (f, kind)
    elif pattern == 'getx':
        p.add('binding', p.path('root', 'binding', '%s_binding.dart' % f), 'getx/binding.dart.tmpl')
        p.add('logic', p.path('presentation', 'logic', '%s_controller.dart' % f), 'getx/controller.dart.tmpl',
              'getx/controller_test.dart.tmpl')
        p.add('state', p.path('presentation', 'state', '%s_state.dart' % f), 'getx/state.dart.tmpl')
        p.add('view', p.path('presentation', 'view', view_file), 'getx/view.dart.tmpl')
    p.add('list', p.path('presentation', 'widget', '%s_list.dart' % f), 'shared/list.dart.tmpl')
    return p


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
_SECTION_RE = re.compile(r'\{\{([#^])(\w+)\}\}(.*?)\{\{/\2\}\}', re.S)
_VAR_RE = re.compile(r'\{\{([A-Za-z_]+)(?::([a-z_]+))?\}\}')


def import_uri(plan, from_path, key, as_test):
    paths = {x['key']: x['path'] for x in plan.files if not x['test']}
    if key == 'dep':
        key = plan.dep_key
    if key not in paths:
        raise KeyError('template imports unknown file key %r' % key)
    target = paths[key]
    if as_test or plan.conv.import_style == 'package':
        return 'package:%s/%s' % (plan.names['package'], target[len('lib/'):])
    rel = os.path.relpath(target, os.path.dirname(from_path)).replace(os.sep, '/')
    return rel


def render(plan, entry):
    with open(os.path.join(TEMPLATES, entry['template']), encoding='utf-8') as fh:
        text = fh.read()

    def section(m):
        on = bool(plan.flags.get(m.group(2)))
        return m.group(3) if (on if m.group(1) == '#' else not on) else ''

    text = _SECTION_RE.sub(section, text)
    names = dict(plan.names, self=entry['path'].rsplit('/', 1)[-1][:-5])

    def var(m):
        name, arg = m.group(1), m.group(2)
        if name == 'import':
            return import_uri(plan, entry['path'], arg, entry['test'])
        if name not in names:
            raise KeyError('unknown placeholder {{%s}} in %s' % (name, entry['template']))
        return names[name]

    text = _VAR_RE.sub(var, text)
    return text


def outline(text, modern):
    decl = []
    for m in re.finditer(r'(?m)^(?:@[Rr]iverpod(?:\([^)]*\))?\s*\n)?(?:abstract\s+|final\s+|sealed\s+|base\s+|interface\s+)*'
                         r'(class|enum|mixin|typedef)\s+(\w+)', text):
        decl.append(m.group(2))
    for m in re.finditer(r'(?m)^@[Rr]iverpod(?:\([^)]*\))?\s*\nclass\s+(\w+)', text):
        decl.append('-> ' + provider_name(m.group(1), modern))
    for m in re.finditer(r'(?m)^@[Rr]iverpod(?:\([^)]*\))?\s*\n[\w<>?, ]+?\s+(\w+)\(', text):
        decl.append('-> ' + m.group(1) + 'Provider')
    for m in re.finditer(r'(?m)^(?!@)(?:Dio|Failure)\s+([a-z]\w*)\(', text):
        if not re.search(r'(?m)^@[Rr]iverpod(?:\([^)]*\))?\s*\n\w+\s+%s\(' % m.group(1), text):
            decl.append(m.group(1) + '()')
    return decl


# --------------------------------------------------------------------------
# Dependencies and next steps
# --------------------------------------------------------------------------
def needed_packages(rendered, package):
    lib, dev = set(), set()
    codegen = False
    for entry, text in rendered:
        for pkg in re.findall(r'(?m)^import\s+[\'"]package:([a-z0-9_]+)/', text):
            if pkg in ('flutter', 'flutter_test', package):
                continue
            (dev if entry['test'] else lib).add(pkg)
        if re.search(r'(?m)^part\s+[\'"][^\'"]+\.g\.dart[\'"]', text):
            codegen = True
    if codegen:
        dev |= {'build_runner', 'riverpod_generator'}
    dev -= lib
    return sorted(lib), sorted(dev), codegen


def wiring(plan):
    n, pat = plan.names, plan.pattern
    client = next(e['path'] for e in plan.files if e['key'] == 'http_client')
    if pat in ('mvn', 'riverpod'):
        return ['Wrap the app in `ProviderScope` (once, in main.dart) and route to `const %s()`.' % n['View'],
                'Remote sources read `httpClientProvider` (%s): set the https base URL and add the auth '
                'interceptor there, once.' % client]
    if pat == 'getx':
        return ["Register the shared client once at startup, e.g. in main() before runApp:",
                "  Get.put(ApiClient(), permanent: true);   // %s: base URL, timeout, auth" % client,
                "then add the route to app_pages.dart:",
                "  GetPage(name: '/%s', page: () => const %s(), binding: %sBinding())," % (
                    plan.f, n['View'], n['Feature'])]
    root = ['Create the HTTP client once at the root (%s: base URL, timeouts, auth):' % client,
            '  final httpClient = createHttpClient();']
    if pat == 'mvvm':
        dep = ('%s(%s(apiClient: %s(httpClient)))' % (n['UseCase'], n['RepositoryImpl'], n['Source'])
               if plan.clean else '%s(apiClient: %s(httpClient))' % (n['RepositoryImpl'], n['Source']))
        return root + ['then build the view model in the route (composition root), e.g. with go_router:',
                       "  builder: (context, state) => %s(viewModel: %s(%s: %s))," % (n['View'], n['Logic'], n['dep'], dep),
                       'or register the %s with `Provider` at the root and pass `context.read()`.' % n['Dep']]
    impl = '%s(%s(httpClient))' % (n['RepositoryImpl'], n['SourceImpl'])
    create = '%s(%s)' % (n['UseCase'], impl) if plan.clean else impl
    if pat == 'provider':
        return root + ['register `Provider<%s>(create: (context) => %s)` there, then provide the notifier '
                       'above the screen, e.g. in the route:' % (n['Dep'], create),
                       '  ChangeNotifierProvider(',
                       '    create: (context) => %s(%s: context.read<%s>())..load(),' % (n['Logic'], n['dep'], n['Dep']),
                       '    child: const %s(),' % n['View'],
                       '  )']
    if pat in ('bloc', 'cubit'):
        return root + ['then register the dependency near the root and route to `const %s()`:' % n['View'],
                       '  RepositoryProvider<%s>(create: (context) => %s, child: ...)' % (n['Dep'], create)]
    return []


def security_notes(root, plan, deps):
    """Hints when the project already has its own client or failure type (checklist S-31: reuse, don't duplicate)."""
    ours = {e['path'] for e in plan.files if e.get('shared')}
    notes = []
    clients, failures = [], []
    for rel, text in walk_lib(root):
        if rel in ours:
            continue
        if re.search(r'\bDio\s*\(|\bBaseOptions\s*\(|\bextends\s+GetConnect\b|\bhttp\.Client\s*\(', text):
            clients.append(rel)
        if re.search(r'(?m)^(?:sealed\s+|abstract\s+|base\s+)*class\s+Failure\b', text):
            failures.append(rel)
    shared = {e['key']: e['path'] for e in plan.files if e.get('shared')}
    if clients:
        notes.append('the project already configures an HTTP client in %s: inject that one into the new source '
                     'and drop %s, so the auth interceptor and timeouts apply (checklist S-31)'
                     % (', '.join(clients[:3]), shared.get('http_client')))
    if failures:
        notes.append('the project already declares a Failure type in %s: map to it instead of %s'
                     % (', '.join(failures[:3]), shared.get('failure')))
    if plan.client == 'dio' and 'http' in deps and 'dio' not in deps:
        notes.append('the project uses package:http; the templates inject a Dio client. Swap the client type in '
                     'the source and %s if you stay on http' % shared.get('http_client'))
    return notes


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def resolve_pattern(profile_arg, report):
    if profile_arg != 'auto':
        return profile_arg, 'declared with --profile %s' % profile_arg
    prof = report.get('profile') or {}
    pres = prof.get('presentation') or 'unknown'
    conf = prof.get('confidence') or 'low'
    if pres == 'bloc':
        files = report.get('files') or []
        cubits = sum(1 for f in files if f['file'].endswith('_cubit.dart'))
        blocs = sum(1 for f in files if f['file'].endswith('_bloc.dart'))
        if cubits > blocs:
            return 'cubit', 'detected bloc profile, mostly cubits (%d vs %d), confidence %s' % (cubits, blocs, conf)
        return 'bloc', 'detected bloc profile, confidence %s' % conf
    if pres in PATTERNS:
        return pres, 'detected %s, confidence %s' % (pres, conf)
    raise UsageError('could not infer a supported pattern (profile: %s). Pass --profile '
                     'mvn|mvvm|bloc|cubit|getx|provider|riverpod.' % pres)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='scaffold.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('root')
    ap.add_argument('feature')
    ap.add_argument('--profile', default='auto', choices=('auto',) + PATTERNS)
    ap.add_argument('--clean', action='store_true', help='add domain/ entities + use cases (non-MVN patterns)')
    ap.add_argument('--entity', help='UpperCamel name of the domain object (default: from the feature name)')
    ap.add_argument('--write', action='store_true', help='create the files (never overwrites)')
    ap.add_argument('--force-dir', action='store_true', help='allow adding files to an existing feature folder')
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    try:
        root = os.path.abspath(args.root)
        if not os.path.isfile(os.path.join(root, 'pubspec.yaml')):
            raise UsageError('no pubspec.yaml in %s' % root)
        validate_feature(args.feature)
        if args.entity and not re.match(r'^[A-Z][A-Za-z0-9]*$', args.entity):
            raise UsageError('--entity must be an UpperCamelCase class name, e.g. Movie')
        package, deps, dev_deps, pubspec_text = parse_pubspec(root)
        if not package:
            raise UsageError('pubspec.yaml has no name:')
        report, source = load_profile(root, args.profile, deps)
        pattern, why = resolve_pattern(args.profile, report)
        prof = report.get('profile') or {}
        clean = args.clean
        clean_why = '--clean'
        if pattern == 'mvn':
            clean, clean_why = True, 'MVN always has domain/ (entities, repositories, usecases)'
        elif not clean and pattern != 'mvvm' and prof.get('clean_architecture') and \
                'flat lib/' not in ' '.join(prof.get('signals') or []):
            clean, clean_why = True, 'the project already uses domain/ + data/ (clean_architecture: true)'
        elif not clean:
            clean_why = 'off (pass --clean to add domain/ use cases)'
        conv = infer_conventions(root, report, pattern, package)
        naming = riverpod_naming(root, pubspec_text) if pattern in ('mvn', 'riverpod') else ('modern', '')
        utils = find_mvvm_utils(root) if pattern == 'mvvm' else {}
        plan = build_plan(pattern, clean, conv, args.feature, args.entity, package, naming, utils)
        sdk = sdk_lower_bound(pubspec_text)
        # Dart 3.12 private named parameters: `X({required this._dep})`, called as `X(dep: ...)`.
        plan.flags['privnamed'] = bool(sdk and sdk >= (3, 12))
        rendered = [(e, render(plan, e)) for e in plan.files if e.get('template')]
    except UsageError as e:
        print('scaffold.py: error: %s' % e, file=sys.stderr)
        return 2
    except (KeyError, OSError) as e:
        print('scaffold.py: template error: %s' % e, file=sys.stderr)
        return 2

    existing = {e['path'] for e, _ in rendered if os.path.exists(os.path.join(root, e['path']))}
    feature_dir = plan.feature_dir()
    own_existing = [p for p in existing if not any(e['path'] == p and e['shared'] for e, _ in rendered)]
    blocked = (os.path.isdir(os.path.join(root, feature_dir)) or own_existing or
               args.feature in ((report.get('stats') or {}).get('features') or []))
    if blocked and not args.force_dir:
        print('scaffold.py: error: feature %r already exists (%s). Pick another name, or pass --force-dir to '
              'add only the missing files (existing files are never overwritten).'
              % (args.feature, feature_dir if os.path.isdir(os.path.join(root, feature_dir))
                 else ', '.join(sorted(own_existing)) or 'listed in the arch profile'), file=sys.stderr)
        return 2

    n = plan.names
    print('== SCAFFOLD PLAN')
    print('  project: %s (package: %s)' % (root, package))
    print('  feature: %s (%s)' % (args.feature, n['Feature']))
    print('  pattern: %s (%s)' % (pattern, why))
    print('  profile source: %s' % source)
    print('  clean layering: %s' % ('on (%s)' % clean_why if clean else clean_why))
    for what, value, reason in conv.notes:
        print('  %s: %s (%s)' % (what, value, reason))
    if pattern in ('mvn', 'riverpod'):
        print('  riverpod provider names: %s; %s -> %s (%s)' % (
            plan.naming_style, n['Logic'], n['logicProvider'], plan.naming_reason))
    for e in plan.files:
        if e.get('reuse'):
            print('  reusing existing %s: %s' % (e['key'].capitalize(), e['path']))
    if pattern == 'mvvm' and clean:
        print('  note: the Flutter guide adds use cases only when logic merges repositories, is complex or '
              'is reused; a pass-through use case is ceremony (AP-passthrough-usecase, Info).')
    for note in security_notes(root, plan, deps):
        print('  note: %s' % note)
    print('  mode: %s' % ('write' if args.write else 'dry run (nothing written; add --write to create the files)'))

    new = [x for x in rendered if x[0]['path'] not in existing]
    print()
    print('== FILES (%d new, %d existing)' % (len(new), len(rendered) - len(new)))
    created, skipped, reused = [], [], []
    for entry, text in rendered:
        path = entry['path']
        decl = ', '.join(outline(text, plan.flags['modern']))
        if path in existing and entry['shared']:
            # app-wide file from an earlier feature (failure type, HTTP client, Result/Command): reuse it
            reused.append(path)
            print('  %s %s  [shared: exists, reused as is]' % ('reused' if args.write else '=', path))
            continue
        if path in existing:
            skipped.append(path)
            if args.write:
                print('  skipped %s (exists, not overwritten)' % path)
            else:
                print('  = %s  [exists: will be skipped]' % path)
            continue
        if args.write:
            full = os.path.join(root, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            try:
                with open(full, 'x', encoding='utf-8') as fh:
                    fh.write(text)
            except FileExistsError:
                skipped.append(path)
                print('  skipped %s (exists, not overwritten)' % path)
                continue
            created.append(path)
            print('  created %s  [%s]' % (path, decl))
        else:
            print('  + %s  [%s]' % (path, decl))
    if args.write:
        print('  summary: %d created, %d skipped%s' % (len(created), len(skipped),
                                                     ', %d reused' % len(reused) if reused else ''))

    lib_pkgs, dev_pkgs, codegen = needed_packages(rendered, package)
    have = deps | dev_deps
    miss_lib = [x for x in lib_pkgs if x not in deps]
    miss_dev = [x for x in dev_pkgs if x not in have]
    print()
    print('== DEPENDENCIES')
    print('  needed: %s' % (', '.join(lib_pkgs) or '(none beyond flutter)'))
    print('  needed (dev): %s' % (', '.join(dev_pkgs) or '(none beyond flutter_test)'))
    misplaced = [x for x in miss_lib if x in dev_deps]
    if misplaced:
        print('  in dev_dependencies but imported from lib/: %s (move them to dependencies)' % ', '.join(misplaced))
    if not miss_lib and not miss_dev:
        print('  missing: none')
    else:
        print('  missing: %s' % ', '.join(miss_lib + ['dev:' + x for x in miss_dev]))
        if miss_lib:
            print('  run: flutter pub add %s' % ' '.join(miss_lib))
        if miss_dev:
            print('  run: flutter pub add %s' % ' '.join('dev:' + x for x in miss_dev))
    print('  (this script never edits pubspec.yaml)')

    test_paths = [e['path'] for e, _ in rendered if e['test']]
    todos = sum(t.count('TODO') for e, t in rendered if e['path'] not in existing)
    print()
    print('== NEXT STEPS')
    step = 1
    if not args.write:
        print('  %d. Confirm the plan above, then re-run with --write.' % step)
        step += 1
    if miss_lib or miss_dev:
        print('  %d. Add the missing dependencies (commands above).' % step)
        step += 1
    if codegen:
        print('  %d. Generate the providers: dart run build_runner build -d' % step)
        step += 1
    if conv.layout == 'feature-first' and not conv.global_data:
        targets = [feature_dir, 'test/' + feature_dir[len('lib/'):]]
        targets += [e['path'] for e, _ in rendered if e['shared']]
    else:
        targets = [e['path'] for e, _ in rendered]
    print('  %d. Check it: dart analyze %s' % (step, ' '.join(targets)))
    step += 1
    print('  %d. Run the tests: flutter test %s' % (step, ' '.join(test_paths)))
    step += 1
    for i, line in enumerate(wiring(plan)):
        print('  %s %s' % ('%d.' % step if i == 0 else '  ', line))
    step += 1
    print('  %d. Fill in the %d TODOs (placeholder fields, the endpoint path, the base URL and auth in the shared '
          'client, user-facing error text).' % (step, todos))
    return 0


if __name__ == '__main__':
    sys.exit(main())
