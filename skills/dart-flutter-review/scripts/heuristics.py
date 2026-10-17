#!/usr/bin/env python3
"""Helpers for review.sh. Read-only. Subcommands:

  context   <root> <dart-sdk-version>                    -> one TSV line: is_flutter, sdk constraint,
                                                          lint include(s), sdk status, package_config path, note
  scope     <root> <files.all> [<arch_check --json file>] -> the non-generated files in scope
  analyzer  <root> <files> <machine-output> <max>
  fix       <root> <files> <dry-run-output> <max>
  mkoptions <root> <asset-options> <out-options> <is_flutter> [<package_config.json>]
  extra     <copy-root> <files> <machine-output> <max> <project-machine-output> <asset-options>
  grep      <root> <files> <max> <is_flutter> [defer-catch] [defer-perf] [defer-ds]
  errors    <root> <files> <machine-output>            -> "<errors> <codegen-cascade errors> <crashed 0|1>" in scope
  audit     <root> <files|-> <scan.sh --json output> <max> -> flutter-security-audit findings as groups
  summary   <section-dir> <scope> <ci 0|1> <fail-on> <exit-code> [arch-only]  -> GitHub step-summary Markdown

`defer-catch`: flutter-error-handling's check_errors.py ran too, so swallowed-catch
keeps only its count and points at the ERROR HANDLING section (reported once, as ERR-).
`defer-perf`: flutter-performance's check_performance.py ran, so eager-children-map keeps
only its count and points at PERFORMANCE (CONTRACTS §23, §33). opacity-widget is not deferred:
PERF-005 reports only animated or in-list Opacity, so a static one would be lost.
`defer-ds`: flutter-design-system's check_design_system.py ran, so hardcoded-color keeps
only its count and points at DESIGN SYSTEM.
"""
import json
import os
import re
import sys
from collections import defaultdict


def read_scope(path):
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]


def split_machine(line):
    # SEVERITY|TYPE|CODE|FILE|LINE|COL|LEN|MSG with '\|' escapes in FILE and MSG
    parts = re.split(r'(?<!\\)\|', line.rstrip('\n'))
    if len(parts) < 8:
        return None
    sev, typ, code, path, ln, col, _len = parts[:7]
    msg = '|'.join(parts[7:]).replace('\\|', '|')
    return sev, typ, code.lower(), path.replace('\\|', '|'), int(ln) if ln.isdigit() else 0, msg


def parse_machine(path, root, scope):
    """Analyzer machine-format lines as (sev, type, code, rel, line, msg); `scope=None` keeps all."""
    scope = None if scope is None else set(scope)
    out = []
    with open(path, errors='replace') as f:
        for line in f:
            p = split_machine(line)
            if not p:
                continue
            sev, typ, code, fpath, ln, msg = p
            rel = os.path.relpath(os.path.realpath(fpath), os.path.realpath(root)) if os.path.isabs(fpath) else fpath
            if scope is None or rel in scope:
                out.append((sev, typ, code, rel, ln, msg))
    return out


SEV_ORDER = {'ERROR': 0, 'WARNING': 1, 'INFO': 2}


def print_grouped(diags, maxn, indent='  '):
    groups = defaultdict(list)
    for d in diags:
        groups[(d[0], d[2])].append(d)
    for (sev, code), items in sorted(groups.items(), key=lambda kv: (SEV_ORDER.get(kv[0][0], 9), -len(kv[1]), kv[0][1])):
        print(f"{indent}{sev:<7} {code}  x{len(items)}")
        for _, _, _, rel, ln, msg in items[:maxn]:
            print(f"{indent}    {rel}:{ln}  {msg[:140]}")
        if len(items) > maxn:
            print(f"{indent}    ... {len(items) - maxn} more")


# ---- codegen cascades -------------------------------------------------------
# When build_runner (or gen-l10n, flutter_gen, slang ...) has not run, every reference to a
# generated symbol fails, and each failure types its expression as `dynamic`, which fails the
# next check. Real apps showed 2,471 (hiddify) and 7,148 (lichess) errors from this alone.
GEN_URI = re.compile(r"""['"]([^'"]*(?:\.(?:g|freezed|gr|gen|config|chopper|mocks|pb|pbenum|pbjson|pbserver|reflectable|drift|part)"""
                     r"""\.dart|/gen_l10n/[^'"]*|/l10n/[^'"]*\.dart|/generated/[^'"]*))['"]""")
CASCADE_CODE = re.compile(
    r'^(?:undefined_\w+|uri_has_not_been_generated|uri_does_not_exist|redirect_to_non_class|mixin_of_non_class|'
    r'extends_non_class|implements_non_class|mixin_with_non_class_superclass|creation_with_non_type|'
    r'non_type_as_type_argument|cast_to_non_type|type_test_with_undefined_name|not_a_type|non_type_in_catch_clause|'
    r'argument_type_not_assignable|invalid_assignment|return_of_invalid_type\w*|non_bool_\w+|'
    r'unchecked_use_of_nullable_value|for_in_of_invalid_type|\w+_element_type_not_assignable|'
    r'map_(?:key|value)_type_not_assignable|throw_of_invalid_type|not_iterable_spread|not_map_spread|'
    r'type_argument_not_matching_bounds|non_exhaustive_switch_\w+|dot_shorthand_\w+|pattern_type_mismatch\w*|'
    r'const_initialized_with_non_constant_value|invalid_constant|const_eval_throws_exception|'
    r'const_with_non_type|body_might_complete_normally\w*|invalid_override|'
    r'non_abstract_class_inherits_abstract_member\w*|missing_required_argument|extra_positional_arguments\w*|'
    r'not_enough_positional_arguments\w*|wrong_number_of_type_arguments\w*|invocation_of_non_function\w*|'
    r'no_default_super_constructor\w*|implicit_super_initializer_missing_arguments|'
    r'concrete_class_with_abstract_member|instance_access_to_static_member|'
    r'use_of_void_result|unqualified_reference_to_\w+|missing_default_value_for_parameter\w*)$')


# warnings that only appear because a generated base class/part is missing
CASCADE_WARNING = {'override_on_non_overriding_member', 'unused_element', 'unused_element_parameter'}


def is_cascade(d):
    return (d[0] == 'ERROR' and CASCADE_CODE.match(d[2])) or (d[0] == 'WARNING' and d[2] in CASCADE_WARNING)


def missing_codegen(root, diags_all, scope):
    """Generated files the project references but that don't exist: from the analyzer
    (uri_has_not_been_generated, uri_does_not_exist on a generated-looking URI) and from
    `part '*.g.dart'` directives on disk. Returns a sorted list of 'file -> target'."""
    found = set()
    for sev, _t, code, rel, _ln, msg in diags_all:
        if code == 'uri_has_not_been_generated' or (code == 'uri_does_not_exist' and GEN_URI.search(msg)):
            m = re.search(r":\s*'([^']+)'\s*\.?\s*$", msg)  # the URI is the last quoted part ("hasn't" has a quote too)
            found.add(f"{rel} -> {m.group(1).rsplit('/', 1)[-1] if m else msg[:80]}")  # same key as the part scan
    for rel in scope:
        if not rel.endswith('.dart'):
            continue
        try:
            text = open(os.path.join(root, rel), errors='replace').read()
        except OSError:
            continue
        for m in re.finditer(r"^part\s+'([^']+)'\s*;", text, re.M):
            target = os.path.normpath(os.path.join(os.path.dirname(os.path.join(root, rel)), m.group(1)))
            if GEN_URI.search("'" + m.group(1) + "'") and not os.path.exists(target):
                found.add(f"{rel} -> {m.group(1).rsplit('/', 1)[-1]}")
    return sorted(found)


def split_cascades(root, out, scope):
    """(real diags in scope, cascade diags in scope, missing generated files, crash line or '')."""
    diags_all = parse_machine(out, root, None)
    inscope = set(scope)
    diags = [d for d in diags_all if d[3] in inscope]
    missing = missing_codegen(root, diags_all, scope)
    if missing:
        casc = [d for d in diags if is_cascade(d)]
        real = [d for d in diags if not is_cascade(d)]
    else:
        casc, real = [], diags
    return real, casc, missing, analyzer_crash(out)


CRASH_MARKERS = ('An unexpected error was encountered by the Analysis Server',
                 'Analysis server exited', 'Unhandled exception:')


def analyzer_crash(out):
    """One-line description of an analyzer / analysis-server crash, or ''."""
    raw = open(out, errors='replace').read()
    marker = next((m for m in CRASH_MARKERS if m in raw), None)
    if not marker:
        return ''
    lines = [l.strip() for l in raw[raw.index(marker):].split('\n')]
    detail = next((l for l in lines[1:] if l and not l.startswith(('Please file', '#', 'http'))), '')
    plugin = re.search(r'\(package:(\w+)/', raw)
    where = f"; in analyzer plugin package:{plugin.group(1)}" if plugin and 'plugin' in raw.lower() else ''
    return f"{marker.rstrip('.:')}: {detail[:120]}{where}".rstrip(': ')


def cmd_analyzer(root, files, out, maxn):
    scope = read_scope(files)
    diags, casc, missing, crash = split_cascades(root, out, scope)
    if crash:
        # a stack trace is useless in a review; say what happened in one line
        print(f"  analyzer crashed ({crash}); results unavailable, not counted in CI. "
              "Rerun `dart analyze` locally; if a plugin crashed, disable it in analysis_options.yaml and retry")
    if missing:
        print(f"  codegen: {len(missing)} generated file(s) missing (e.g. {missing[0]}). "
              "Run `dart run build_runner build` (and `flutter gen-l10n` if used) first")
        if casc:
            by_code = defaultdict(int)
            for d in casc:
                by_code[d[2]] += 1
            top = ', '.join(f"{c} x{n}" for c, n in sorted(by_code.items(), key=lambda kv: -kv[1])[:4])
            ne = sum(1 for d in casc if d[0] == 'ERROR')
            nw = len(casc) - ne
            what = f"{ne} error(s)" + (f" and {nw} warning(s)" if nw else '')
            print(f"  collapsed: {what} are likely codegen cascades, not counted in CI ({top})")
    if not diags:
        raw = open(out, errors='replace').read()
        if crash:
            return
        if casc:
            print("  no other issues in scope")
        elif 'No issues found' in raw or not raw.strip():
            print("  no issues")
        else:
            print("  no issues in scope" if '|' in raw else "  analyzer output:\n" + raw[:800])
        return
    counts = defaultdict(int)
    for d in diags:
        counts[d[0]] += 1
    print("  " + ", ".join(f"{counts[s]} {s.lower()}" for s in ('ERROR', 'WARNING', 'INFO') if counts[s]))
    print_grouped(diags, maxn)


def cmd_fix(root, files, out, maxn):
    scope = set(read_scope(files))
    per_code = defaultdict(int)
    per_code_files = defaultdict(set)
    cur = None
    for line in open(out, errors='replace'):
        s = line.rstrip('\n')
        if re.match(r'^\S.*\.dart$', s):
            cur = s.strip()
            continue
        m = re.match(r'^\s+(\w+)\s+(?:•|-)\s+(\d+)\s+fix', s)
        if m and cur and cur in scope:
            per_code[m.group(1)] += int(m.group(2))
            per_code_files[m.group(1)].add(cur)
    if not per_code:
        print("  nothing auto-fixable in scope")
        return
    total = sum(per_code.values())
    nfiles = len(set().union(*per_code_files.values()))
    print(f"  {total} fix(es) in {nfiles} file(s) -> one collapsed 'Mechanical' finding: dart fix --apply")
    for code, n in sorted(per_code.items(), key=lambda kv: -kv[1])[: max(maxn, 10)]:
        print(f"    {code:<45} x{n}")


def asset_rules(asset):
    rules, in_rules = [], False
    for line in open(asset):
        if re.match(r'^\s+rules:\s*$', line):
            in_rules = True
            continue
        if in_rules:
            m = re.match(r'^\s+-\s+([a-z_0-9]+)', line)
            if m:
                rules.append(m.group(1))
    return rules


def cmd_mkoptions(root, asset, out, is_flutter, pkg_config=''):
    pkgs = set()
    try:
        cfg = json.load(open(pkg_config or os.path.join(root, '.dart_tool', 'package_config.json')))
        pkgs = {p['name'] for p in cfg.get('packages', [])}
    except Exception:
        pass
    include = ''
    if is_flutter == '1' and 'flutter_lints' in pkgs:
        include = 'include: package:flutter_lints/flutter.yaml\n'
    elif 'lints' in pkgs:
        include = 'include: package:lints/recommended.yaml\n'
    text = open(asset).read()
    text = re.sub(r'^include:.*\n', include, text, flags=re.M)
    text = re.sub(r'^formatter:\n(?:[ \t]+.*\n|[ \t]*#.*\n)*', '', text, flags=re.M)
    with open(out, 'w') as f:
        f.write(text)


def cmd_extra(copy_root, files, out, maxn, project_out, asset):
    scope = read_scope(files)
    wanted = set(asset_rules(asset))
    diags = [d for d in parse_machine(out, copy_root, scope)
             if d[2] in wanted or d[2] == 'strict_raw_type' or d[2].startswith('inference_failure')]
    # drop anything the project's own config already reports
    seen = set()
    for line in open(project_out, errors='replace'):
        p = split_machine(line)
        if p:
            seen.add((p[2], p[4], os.path.basename(p[3])))
    diags = [d for d in diags if (d[2], d[4], os.path.basename(d[3])) not in seen]
    if not diags:
        print("  nothing extra")
        return
    print(f"  {len(diags)} additional issue(s) the stricter set would flag (suggest adopting rules, don't report as violations):")
    print_grouped([('INFO',) + d[1:] for d in diags], maxn)


# ----------------------------------------------------------------- heuristics
DISPOSABLE = (r'AnimationController|TextEditingController|ScrollController|PageController|TabController|'
              r'FocusNode|TransformationController|SearchController|WebViewController|VideoPlayerController|'
              r'StreamController(?:<[^>]*>)?(?:\.broadcast)?|ValueNotifier(?:<[^>]*>)?')

HEURISTICS = [
    # id, severity hint, description, regex (applied per line, comments stripped), path filter
    ('get-prefixed-method', 'low',
     "Zero-argument, synchronous get*() method — Effective Dart: AVOID starting a method name with `get`; if it is cheap, make it a getter. (Methods with parameters or Future/Stream returns, e.g. repository `getBooking(id)`, are not flagged.)",
     re.compile(r'^\s*(?:static\s+)?(?!(?:Future|Stream|FutureOr)\b)(?:[A-Z]\w*|int|double|num|bool|String|void|dynamic)(?:<[^=;{}()]*>)?\??\s+get[A-Z]\w*\s*(?:<[^>]*>)?\s*\(\s*\)'), None),
    ('async-suffix', 'low',
     "`Async` suffix — the Future return type already says it; drop the suffix.",
     re.compile(r'^\s*(?:static\s+)?(?:Future|Stream|FutureOr)(?:<[^=;{}]*>)?\s+\w+Async\s*\('), None),
    ('k-or-hungarian-prefix', 'low',
     "Prefix-letter name (kFoo / mFoo / strFoo) — Effective Dart: DON'T use prefix letters. Skip if the project consistently uses k-constants.",
     re.compile(r'\b(?:const|final|static|var)\s+(?:[\w<>?,\s]+\s)?(?:k|m|str|int|bool|lst|arr)[A-Z]\w*\s*='), None),
    ('i-prefixed-interface', 'low',
     "I-prefixed type (IFoo) — every Dart class is an interface; name it for its role.",
     re.compile(r'\b(?:abstract\s+(?:interface\s+)?)?class\s+I[A-Z][a-z]\w*'), None),
    ('noise-word-type', 'low',
     "Noise-word type name (Manager/Helper/Util/Utils/Info/Data) — prefer a precise role name; static-only Utils classes violate avoid_classes_with_only_static_members. (`*Impl` is deliberately not flagged: Clean Architecture/MVN prescribe it.)",
     re.compile(r'\b(?:class|mixin|extension|enum)\s+\w*(?:Manager|Helper|Helpers|Utils?|Info|Data)\b'), None),
    ('negative-boolean', 'low',
     "Negatively named boolean — Effective Dart: PREFER the positive name (isEnabled over isDisabled).",
     re.compile(r'\bbool\??\s+(?:_?(?:is|has|should|can)?(?:Not|Dis|Un|No)[A-Z]\w*|_?(?:isHidden|isDisabled|isInvisible|hidden|disabled|notVisible))\b'), None),
    ('on-named-method', 'low',
     "Public method named on*() — Flutter style: `onFoo` is reserved for callback *properties*; name the method `handleFoo`. (Private `_onTap` handlers are a common app convention and not flagged.)",
     re.compile(r'^\s*(?:void|Future<void>)\s+on[A-Z]\w*\s*\([^)]*\)\s*(?:async\s*)?\{'), None),
    ('widget-helper-method', 'low',
     "Widget-returning helper method — prefer a private StatelessWidget class (own element, const-able, rebuilds independently).",
     re.compile(r'^\s*Widget\s+_?build[A-Z]\w*\s*\('), 'flutter'),
    ('mediaquery-of', 'low',
     "MediaQuery.of(context).<x> — use MediaQuery.sizeOf/paddingOf/viewInsetsOf/... to rebuild only on that aspect.",
     re.compile(r'MediaQuery\.of\(\s*\w+\s*\)\s*\.\s*(?:size|padding|viewInsets|viewPadding|orientation|textScaler|textScaleFactor|devicePixelRatio|platformBrightness|alwaysUse24HourFormat)\b'), 'flutter'),
    ('eager-children-map', 'low',
     "children built with .map(...) — fine for small fixed sets; for long/unbounded data use ListView.builder / slivers.",
     re.compile(r'children:\s*[\w.?!]+\s*\.map\s*[(<]'), 'flutter'),
    ('future-in-build', 'high',
     "FutureBuilder/StreamBuilder inside build() given a call expression — it refires every rebuild; create the future in initState / the state layer.",
     None, 'flutter'),
    ('opacity-widget', 'low',
     "Opacity widget — expensive (saveLayer); in animations use FadeTransition/AnimatedOpacity, for static use a translucent color.",
     re.compile(r'(?<![\w.])Opacity\s*\('), 'flutter'),
    ('unique-key', 'medium',
     "UniqueKey() inside build() — forces a remount every rebuild; use a stable ValueKey(id).",
     re.compile(r'\bUniqueKey\s*\(\s*\)'), 'flutter'),
    ('hardcoded-color', 'low',
     "Hard-coded Color(0x...) outside theme files — read from Theme.of(context).colorScheme.",
     re.compile(r'\bColor\s*\(\s*0x[0-9A-Fa-f]+'), 'flutter-nontheme'),
    ('dynamic-in-api', 'medium',
     "`dynamic` as a declared variable/param/return type — AVOID dynamic unless you mean to disable checking; use Object? or a real type. (Type arguments like Map<String, dynamic> / Route<dynamic> are not flagged.)",
     re.compile(r'(?:^|[(,{\s])(?:final\s+|late\s+|static\s+)*dynamic\s+[A-Za-z_]\w*\s*[;=,)({]'), None),
    ('then-chain', 'low',
     ".then(...) whose result is used (returned, assigned, awaited, passed on, or in an async function) — PREFER async/await. Fire-and-forget statements in sync callbacks are not flagged.",
     re.compile(r'\.then\s*[(<]'), None),
]

# Downgraded variants: same smell, weaker evidence (reported under their own id and severity)
VARIANTS = {
    'unique-key-outside-build': ('low', "UniqueKey() outside build() (constructor default `key ?? UniqueKey()`, a helper) — "
                                 "a remount whenever that code runs; prefer a stable ValueKey(id). State fields are not flagged."),
    'dynamic-closure-param': ('low', "`dynamic` on a closure parameter (`(dynamic json) {`) — local; prefer Object? or the "
                              "real type, or let inference type it."),
}
VARIANT_OF = {'unique-key': 'unique-key-outside-build', 'dynamic-in-api': 'dynamic-closure-param'}

LINE_COMMENT = re.compile(r'(^|\s)//.*$')
# catch block whose whole body is empty or `return <default>;` (multi-line aware)
SWALLOWED_CATCH = re.compile(
    r'catch\s*\([^)]*\)\s*\{\s*(?:return\s*(?:null|false|true|\[\]|\{\}|\'\'|""|0|const\s*\[\])?\s*;\s*)?\}')


def released(name, code, verbs):
    """True if `name` is plausibly released in this file:
    direct call or tear-off (`x.dispose()`, `ref.onDispose(x.cancel)`), cascade,
    listed/passed somewhere while the file releases things generically
    (`for (final c in [a, b]) c.dispose()`), or handed off (`_out = x;`)."""
    n = re.escape(name)
    v = '|'.join(verbs)
    if re.search(r'\b' + n + r'\s*[?!]?\s*\.\s*(?:' + v + r')\b', code):
        return True
    generic = re.search(r'\b\w+\s*[?!]?\s*\.\s*(?:' + v + r')\b', code)
    if generic and re.search(r'[\[(,]\s*' + n + r'\s*[,\])]', code):
        return True
    if re.search(r'\b\w+\s*=\s*' + n + r'\s*;', code):
        return True
    return False


def is_theme_file(rel):
    return bool(re.search(r'(theme|color|colour|palette|style|token)', rel, re.I))


def cmd_errors(root, files, out):
    real, casc, _missing, crash = split_cascades(root, out, read_scope(files))
    print(sum(1 for d in real if d[0] == 'ERROR'), sum(1 for d in casc if d[0] == 'ERROR'), 1 if crash else 0)


# ---- context ------------------------------------------------------------------
def _version(v):
    """'3.9.0-0' -> (3, 9, 0, 0, '0'); a release sorts after its prereleases."""
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([\w.]+))?', v.strip())
    if not m:
        return None
    pre = m.group(4)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if pre is not None else 1, pre or '')


def sdk_status(constraint, sdk):
    """'ok', or why the installed SDK can't analyse a project with this environment.sdk constraint."""
    c = (constraint or '').strip().strip('\'"').strip()
    have = _version(sdk)
    if not c or c == 'any' or not have:
        return 'ok'
    lo = hi = None  # (version, inclusive)
    if c.startswith('^'):
        v = _version(c[1:])
        if not v:
            return 'ok'
        lo = (v, True)
        hi = (((v[0] + 1, 0, 0, 0, '') if v[0] > 0 else (0, v[1] + 1, 0, 0, '')), False)
    else:
        for op, ver in re.findall(r'(>=|<=|>|<)?\s*(\d+\.\d+\.\d+(?:-[\w.]+)?)', c):
            v = _version(ver)
            if op in ('>=', '>'):
                lo = (v, op == '>=')
            elif op in ('<=', '<'):
                hi = (v, op == '<=')
            else:
                lo = hi = (v, True)
    if lo and lo[0][:3] < (2, 12, 0):
        return f"pubspec sdk constraint {c} is pre-null-safety (Dart 3 needs >=2.12.0); installed Dart {sdk}"
    # Dart 3 reads `<3.0.0` with a null-safe lower bound as `<4.0.0` (dart.dev/null-safety#dart-3-and-null-safety)
    if hi and hi[0][:3] == (3, 0, 0) and not hi[1] and lo and lo[0][:3] >= (2, 12, 0):
        hi = ((4, 0, 0, 0, ''), False)
    if lo and (have < lo[0] or (have == lo[0] and not lo[1])):
        return f"pubspec sdk constraint {c} needs a newer Dart than the installed {sdk}"
    if hi:
        # exclusive `<4.0.0` also excludes 4.0.0 prereleases (pub semantics)
        if (hi[1] and have > hi[0]) or (not hi[1] and have[:3] >= hi[0][:3]):
            return f"pubspec sdk constraint {c} excludes the installed Dart {sdk}"
    return 'ok'


def _yaml_block(text, key):
    """Value of a top-level `key:`; for a block list, the `- item` lines joined by ', '."""
    lines = text.split('\n')
    for i, l in enumerate(lines):
        m = re.match(r'^' + key + r':[ \t]*(.*?)[ \t]*(?:#.*)?$', l)
        if not m:
            continue
        if m.group(1):
            return m.group(1).strip('\'"').strip()
        items = []
        for nxt in lines[i + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith('#'):
                continue
            im = re.match(r'^[ \t]*-[ \t]+(\S.*?)[ \t]*(?:#.*)?$', nxt)
            if not im:
                break
            items.append(im.group(1).strip('\'"'))
        return ', '.join(items)
    return ''


def find_package_config(root):
    """The package_config.json that resolves this package: its own, or a pub workspace root's
    (`resolution: workspace` members have none of their own). Returns (path, note)."""
    real_root = os.path.realpath(root)
    d = real_root
    while True:
        cand = os.path.join(d, '.dart_tool', 'package_config.json')
        if os.path.isfile(cand):
            if d == real_root:
                return cand, ''
            try:
                cfg = json.load(open(cand))
                base = os.path.dirname(cand)
                for p in cfg.get('packages', []):
                    uri = p.get('rootUri', '')
                    if uri.startswith('file://'):
                        path = uri[7:]
                    elif '://' in uri:
                        continue
                    else:
                        path = os.path.join(base, uri)
                    if os.path.realpath(path.rstrip('/')) == real_root:
                        return cand, f"pub workspace member; packages resolved at {os.path.dirname(os.path.dirname(cand))}"
            except (OSError, ValueError):
                pass
            return '', ''  # nearest config doesn't list this package: unrelated, don't use it
        parent = os.path.dirname(d)
        if parent == d:
            return '', ''
        d = parent


def cmd_context(root, sdk):
    try:
        pub = open(os.path.join(root, 'pubspec.yaml'), errors='replace').read()
    except OSError:
        pub = ''
    is_flutter = '1' if re.search(r'^[ \t]+sdk:[ \t]*flutter\b', pub, re.M) else '0'
    env = re.search(r'^environment:[ \t]*\n((?:[ \t]+.*\n?|[ \t]*\n)*)', pub, re.M)
    cm = re.search(r'^[ \t]+sdk:[ \t]*(.+?)[ \t]*(?:#.*)?$', env.group(1), re.M) if env else None
    constraint = cm.group(1).strip() if cm else ''
    include = ''
    try:
        include = _yaml_block(open(os.path.join(root, 'analysis_options.yaml'), errors='replace').read(), 'include')
    except OSError:
        pass
    status = sdk_status(constraint, sdk)
    pkg, note = find_package_config(root)
    print('\t'.join(x.replace('\t', ' ') or '-' for x in (is_flutter, constraint, include, status, pkg, note)))


# ---- scope --------------------------------------------------------------------
GENERATED_NAME = re.compile(
    r'(\.g|\.freezed|\.gr|\.gen|\.mocks|\.config|\.chopper|\.pb|\.pbenum|\.pbjson|\.pbserver|\.reflectable)\.dart$|'
    r'(^|/)generated/|(^|/)l10n/app_localizations.*\.dart$|(^|/)app_localizations.*\.dart$|'
    r'(^|/)messages_\w+\.dart$|^\.dart_tool/|^build/')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|AUTO[- ]GENERATED|DO NOT EDIT|Generated by|@generated', re.I)


def _l10n_outputs(root):
    """(dir, stem) of the gen-l10n output named in l10n.yaml (output-dir defaults to arb-dir)."""
    try:
        text = open(os.path.join(root, 'l10n.yaml'), errors='replace').read()
    except OSError:
        return None
    arb = _yaml_block(text, 'arb-dir') or 'lib/l10n'
    out_dir = _yaml_block(text, 'output-dir') or arb
    stem = os.path.splitext(_yaml_block(text, 'output-localization-file') or 'app_localizations.dart')[0]
    return out_dir.strip('/').rstrip('/'), stem


def is_generated(root, rel, l10n):
    if GENERATED_NAME.search(rel):
        return True
    if l10n and os.path.dirname(rel) == l10n[0] and os.path.basename(rel).startswith(l10n[1]):
        return True
    try:
        with open(os.path.join(root, rel), errors='replace') as f:
            head = f.read(600)
    except OSError:
        return False
    return bool(GENERATED_HEADER.search(head))


def cmd_scope(root, files_all, arch_json=''):
    """Drop generated files. arch_check's files[] is the source of truth for lib/ (CONTRACTS §18);
    other folders (test/, bin/, tool/) and runs without it use the same rules as a fallback."""
    lib_ok = None
    if arch_json:
        try:
            data = json.load(open(arch_json))
            lib_ok = {f['file'] for f in data.get('files', []) if isinstance(f, dict) and 'file' in f}
        except (OSError, ValueError, TypeError):
            lib_ok = None
    l10n = _l10n_outputs(root)
    for rel in read_scope(files_all):
        if lib_ok is not None and rel.startswith('lib/'):
            keep = rel in lib_ok
        else:
            keep = not is_generated(root, rel, l10n)
        if keep:
            print(rel)


# ---- flutter-security-audit (scan.sh --json) ----------------------------------
AUDIT_SEV = {'CRITICAL': 'high', 'HIGH': 'high', 'MEDIUM': 'medium', 'LOW': 'low', 'INFO': 'info'}


def cmd_audit(root, files, out, maxn):
    """Regroup scan.sh findings in the suite's group format. In diff mode (files != '-') keep only
    hits in changed files; project-wide absence checks ("MISSING: ...") are left to a full run."""
    try:
        data = json.load(open(out, errors='replace'))
        findings = data.get('findings', [])
    except (OSError, ValueError, AttributeError):
        print("  could not parse scan.sh --json output")
        return
    scope = None if files == '-' else set(read_scope(files))
    real_root = os.path.realpath(root)
    groups, omitted = {}, 0
    for f in findings:
        loc = f.get('location', '')
        path, _, ln = loc.rpartition(':') if re.search(r':\d+$', loc) else (loc, '', '')
        if path and path != '(project-wide)':
            ap = os.path.realpath(path if os.path.isabs(path) else os.path.join(os.getcwd(), path))
            rel = os.path.relpath(ap, real_root) if ap.startswith(real_root) else path
            loc = rel + (':' + ln if ln else '')
        else:
            rel = ''
        if scope is not None and rel not in scope:
            omitted += 1
            continue
        sev = (f.get('severity') or 'LOW').upper()
        key = f.get('id', '?')
        g = groups.setdefault(key, {'sev': AUDIT_SEV.get(sev, 'low'), 'crit': sev == 'CRITICAL',
                                    'tag': ' · '.join(x for x in (f.get('masvs'), f.get('cwe')) if x), 'items': [],
                                    'absent': (f.get('evidence') or '').startswith('MISSING:')})
        g['items'].append((loc or '(project-wide)', f.get('evidence', '')))
    print(f"  {sum(len(g['items']) for g in groups.values())} candidate(s) from flutter-security-audit scan.sh "
          "(MASVS/CWE-tagged; confirm each, absence checks may not apply)")
    if scope is not None:
        print(f"  diff mode: {omitted} hit(s) outside the changed files or project-wide omitted; run without --diff for all")
    order = sorted(groups.items(), key=lambda kv: (SEV_RANK.get(kv[1]['sev'], 9), not kv[1]['crit'], kv[0]))
    for key, g in order:
        kind = 'absence check' if g['absent'] else 'pattern'
        crit = 'CRITICAL; ' if g['crit'] else ''
        print(f"  [{key}] ({g['sev']}) x{len(g['items'])} — {crit}{g['tag']} ({kind})")
        for loc, ev in g['items'][:maxn]:
            print(f"      {loc}  {ev[:140]}")
        if len(g['items']) > maxn:
            print(f"      ... {len(g['items']) - maxn} more")
    if not groups:
        print("  no security-audit candidates")


# group lines of every section: arch_check `[ARCH-005] name (high) x3 — msg`, test_gaps/check_errors
# `[TEST-slug] (medium) x2 — msg`, candidates `[CANDIDATE] id (high) x2 — desc`, analyzer `ERROR   code  x3`
GROUP_RE = re.compile(r'^\s+\[([A-Z]+(?:-[\w-]+)?)\]\s+(?:([\w-]+)\s+)?\((high|medium|low|info)\)\s+x(\d+)\s+\S\s+(.*)$')
ANALYZER_RE = re.compile(r'^\s+(ERROR|WARNING|INFO)\s+(\S+)\s+x(\d+)$')
LOC_RE = re.compile(r'^\s{4,}(?:#\d+\s+)?(\S+\.dart(?::\d+)?)(?:\s+(.*))?$')
SEV_RANK = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
SECTIONS = (('format', 'Format'), ('analyzer', 'Analyzer'), ('fix', 'Auto-fixable'), ('arch', 'Architecture'),
            ('tests', 'Test gaps'), ('errors', 'Error handling'), ('secure', 'Security defaults'),
            ('audit', 'Security audit (scan.sh)'), ('nav', 'Navigation'), ('forms', 'Forms'), ('i18n', 'I18n'),
            ('perf', 'Performance'), ('persist', 'Persistence'), ('net', 'Networking'), ('platform', 'Platform'), ('ds', 'Design system'), ('a11y', 'Accessibility'), ('release', 'Release'),
            ('candidates', 'Candidates (unconfirmed)'))
SECTION_RANK = {'arch': 0, 'errors': 1, 'secure': 2, 'persist': 3, 'net': 4, 'platform': 5, 'nav': 6, 'forms': 7, 'a11y': 8,
                'i18n': 9, 'perf': 10, 'ds': 11, 'tests': 12, 'release': 13, 'audit': 14}


def _groups(lines):
    out = []
    for i, line in enumerate(lines):
        m = GROUP_RE.match(line)
        a = None if m else ANALYZER_RE.match(line)
        if not (m or a):
            continue
        loc, locmsg = '', ''
        if i + 1 < len(lines):
            lm = LOC_RE.match(lines[i + 1])
            if lm:
                loc, locmsg = lm.group(1), lm.group(2) or ''
        if m:
            rid, name, sev, n, msg = m.groups()
            if rid == 'CANDIDATE':
                rid, name = name or '?', ''
            out.append({'id': rid, 'sev': sev, 'n': int(n), 'msg': msg, 'loc': loc, 'cand': m.group(1) == 'CANDIDATE'})
        else:
            sev = {'ERROR': 'high', 'WARNING': 'medium', 'INFO': 'low'}[a.group(1)]
            out.append({'id': 'LINT:' + a.group(2), 'sev': sev, 'n': int(a.group(3)),
                        'msg': '%s: %s' % (a.group(1).lower(), locmsg) if locmsg else a.group(1).lower(),
                        'loc': loc, 'cand': False})
    return out


def _md(text):
    return text.replace('|', '\\|').replace('\n', ' ')


def cmd_summary(secdir, scope, ci, fail_on, rc, mode=''):
    rows, top = [], []
    for key, label in SECTIONS:
        path = os.path.join(secdir, key + '.txt')
        if not os.path.isfile(path):
            continue
        lines = open(path, errors='replace').read().split('\n')
        head = lines[0] if lines else ''
        if '(skipped' in head:
            rows.append((label, '–', head.split('(', 1)[1].rstrip(')')))
            continue
        if '(error' in head:
            rows.append((label, '–', head.split('(', 1)[1].rstrip(')')))
            continue
        groups = _groups(lines)
        total = sum(g['n'] for g in groups)  # analyzer: errors + warnings + infos
        note = ''
        if key == 'format':
            m = re.search(r'(\d+) file\(s\) not formatted', '\n'.join(lines))
            total = int(m.group(1)) if m else 0
        elif key == 'fix':
            m = re.search(r'(\d+) fix\(es\) in (\d+) file', '\n'.join(lines))
            total = int(m.group(1)) if m else 0
            note = 'one Mechanical finding: `dart fix --apply`' if total else ''
        elif key == 'analyzer':
            m = re.search(r'^  (\d+ error.*|\d+ warning.*|\d+ info.*)$', '\n'.join(lines), re.M)
            note = m.group(1) if m else ''
            cm = re.search(r'^  collapsed: (\d+) error', '\n'.join(lines), re.M)
            if cm:
                note = (note + '; ' if note else '') + cm.group(1) + ' codegen-cascade errors not counted (run build_runner)'
            if os.path.isfile(os.path.join(secdir, 'analyzer.unresolved')):
                note += ' (unresolved: no `pub get`, not counted)'
                groups = []  # unresolved-import noise; keep it out of the top findings
        elif key == 'arch':
            m = re.search(r'summary: (\d+ new, \d+ baselined)', '\n'.join(lines))
            prof = re.search(r'^  presentation: (\S+)', '\n'.join(lines), re.M)
            note = '; '.join(x for x in (('profile ' + prof.group(1)) if prof else '', m.group(1) if m else '') if x)
        rows.append((label, str(total), note))
        if key != 'candidates':
            for g in groups:
                g['src'] = SECTION_RANK.get(key, 15)
            top += groups
    out = ['## Flutter review', '', 'Scope: %s' % scope, '']
    if ci == '1':
        why = ('new architecture violations at or above it' if mode == 'arch-only' else
               'new architecture violations at or above it, or analyzer errors')
        res = {'0': 'pass', '1': 'FAIL'}.get(rc, 'ERROR (exit %s)' % rc)
        out.append('**Result: %s** (fail-on: `%s`; CI fails on %s)' % (res, fail_on, why))
        out.append('')
    out += ['| Section | Findings | Notes |', '|---|---:|---|']
    out += ['| %s | %s | %s |' % (_md(a), b, _md(c)) for a, b, c in rows]
    top.sort(key=lambda g: (SEV_RANK.get(g['sev'], 9), g['src'], -g['n'], g['id']))
    # the 8 most severe overall, plus the best 2 of each other section so one pass cannot crowd out the rest
    picked = top[:8]
    for src in sorted({g['src'] for g in top}):
        picked += [g for g in top if g['src'] == src and g not in picked][:max(0, 2 - sum(1 for p in picked if p['src'] == src))]
    top = sorted(picked, key=lambda g: (SEV_RANK.get(g['sev'], 9), g['src'], -g['n'], g['id']))
    if top:
        out += ['', '### Top findings', '', '| Severity | ID | Count | Example | Message |', '|---|---|---:|---|---|']
        for g in top:
            out.append('| %s | `%s` | %d | %s | %s |' % (g['sev'], _md(g['id']), g['n'],
                                                     ('`%s`' % _md(g['loc'])) if g['loc'] else '', _md(g['msg'][:160])))
    if mode == 'arch-only':
        out += ['', '_Architecture check only (`flutter: false`); set `flutter: true` for format, analyzer, '
                    'test-gap and error-handling sections._']
    out += ['', '_Mechanical pass only: confirm each finding by reading the code. '
                'Generated by [flutter-pro-skills](https://github.com/abdelrahman-abied/flutter-pro-skills)._', '']
    print('\n'.join(out))


# ---- code-structure helpers for the heuristics ----------------------------------
STRING_LIT = re.compile(r"""'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*\"""")
BUILD_HDR = re.compile(r'\bWidget\s+build\s*\(\s*BuildContext\s+\w+[^)]*\)\s*(?:async\s*)?(\{|=>)')
CLASS_HDR = re.compile(r'\b(?:class|mixin|extension(?:\s+type)?)\s+(\w+)[^{;]*\{')
OVERRIDE_CHECKED = ('get-prefixed-method', 'async-suffix', 'on-named-method', 'widget-helper-method')


def mask_strings(code):
    """Same length as `code`, string literal contents blanked, so braces in strings don't count."""
    return STRING_LIT.sub(lambda m: m.group(0)[0] + ' ' * (len(m.group(0)) - 2) + m.group(0)[-1], code)


def block_end(code, i):
    """Index of the `}` matching the `{` at i."""
    depth = 0
    for j in range(i, len(code)):
        c = code[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j
    return len(code)


def expr_end(code, i):
    """End of an `=> expr;` body starting at i."""
    depth = 0
    for j in range(i, len(code)):
        c = code[j]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth < 0:
                return j
        elif c == ';' and depth == 0:
            return j
    return len(code)


def build_ranges(masked):
    out = []
    for m in BUILD_HDR.finditer(masked):
        if m.group(1) == '{':
            out.append((m.end() - 1, block_end(masked, m.end() - 1)))
        else:
            out.append((m.end(), expr_end(masked, m.end())))
    return out


def class_ranges(masked):
    return [(m.group(1), m.end() - 1, block_end(masked, m.end() - 1)) for m in CLASS_HDR.finditer(masked)]


def inside(ranges, off):
    return any(a <= off <= b for a, b in ranges)


def statement_context(masked, off):
    """Look back from `off` (the `.then`) to where its expression starts.
    Returns ('stmt', enclosing_is_async) for an expression statement, else ('value', None)."""
    depth, i = 0, off - 1
    while i >= 0:
        c = masked[i]
        if c in ')]':
            depth += 1
        elif c == '}':
            if depth == 0:
                break
            depth += 1
        elif c in '([{':
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and c in ';,':
            break
        elif depth == 0 and c == '>' and i > 0 and masked[i - 1] == '=':
            return 'value', None  # arrow body: the future is the callback's result
        i -= 1
    boundary = masked[i] if i >= 0 else ';'
    if boundary in '([,':
        return 'value', None  # an argument or list element
    text = masked[i + 1:off].strip()
    if re.match(r'^(?:return|await|yield|throw|var|final|late|const)\b', text) or \
            re.match(r'^[\w.\[\]<>?, ]+\s*(?:[-+*/~%&|^]|\?\?)?=(?!=)', text):
        return 'value', None
    # enclosing function: the nearest unmatched `{` before the statement
    j = i if boundary == '{' else None
    if j is None:
        depth, j = 0, i
        while j >= 0:
            c = masked[j]
            if c == '}':
                depth += 1
            elif c == '{':
                if depth == 0:
                    break
                depth -= 1
            j -= 1
    head = masked[max(0, j - 40):j] if j is not None and j >= 0 else ''
    return 'stmt', bool(re.search(r'\basync\s*\*?\s*$', head))


def has_override(lines, idx):
    """`@override` on line idx (0-based) or on the annotation lines right above it."""
    if '@override' in lines[idx]:
        return True
    k = idx - 1
    while k >= 0 and (not lines[k].strip() or lines[k].strip().startswith('@')):
        if lines[k].strip().startswith('@override'):
            return True
        k -= 1
    return False


def snake(name):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name.lstrip('_')).lower()


TOP_DECL = re.compile(r'^(?:(?:abstract|final|sealed|base|interface|mixin)\s+)*(?:class|mixin|enum|extension(?:\s+type)?|typedef)\s+(\w+)|'
                      r'^(?:[A-Za-z_][\w<>?,\[\] ]*\s+)?([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\([^;{]*\)\s*(?:async\s*\*?\s*)?(?:\{|=>)|'
                      r'^(?:final|const|var|late)\s+(?:[\w<>?,]+\s+)?(\w+)\s*=', re.M)


def top_level_names(code):
    return [next(g for g in m.groups() if g) for m in TOP_DECL.finditer(code)]


def future_in_build_hits(masked, builds):
    """`future:`/`stream:` of a FutureBuilder/StreamBuilder inside build() given a call expression."""
    hits = []
    for a, b in builds:
        # type arguments may nest: StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
        for m in re.finditer(r'\b(?:FutureBuilder|StreamBuilder)\s*(?:<[^(){};]*>)?\s*\(', masked[a:b]):
            open_at = a + m.end() - 1
            depth, j = 0, open_at
            while j < len(masked):
                c = masked[j]
                if c in '([{':
                    depth += 1
                elif c in ')]}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            args = masked[open_at:j]
            for am in re.finditer(r'\b(?:future|stream)\s*:\s*', args):
                # depth of this named argument must be the builder's own argument list
                pre = args[:am.start()]
                if sum(pre.count(x) for x in '([{') - sum(pre.count(x) for x in ')]}') != 1:
                    continue
                k, d = am.end(), 0
                while k < len(args):
                    c = args[k]
                    if c in '([{':
                        d += 1
                    elif c in ')]}':
                        if d == 0:
                            break
                        d -= 1
                    elif c == ',' and d == 0:
                        break
                    k += 1
                expr = args[am.end():k].strip()
                if re.search(r'[A-Za-z_]\w*\s*(?:<[^>]*>)?\s*\(', expr) and \
                        not re.match(r'^(?:widget\.|ref\.watch\s*\()', expr) and '??=' not in expr:
                    hits.append(open_at + am.start())
    return hits


# heuristic id -> (defer flag, section that owns it, owning checker) when that checker ran (CONTRACTS §23)
DEFERRED = {
    'swallowed-catch': ('defer-catch', 'ERROR HANDLING', 'check_errors.py covers these with ERR- ids'),
    'eager-children-map': ('defer-perf', 'PERFORMANCE', 'check_performance.py covers these with PERF- ids'),
    'hardcoded-color': ('defer-ds', 'DESIGN SYSTEM', 'check_design_system.py covers these with DS- ids'),
}


def cmd_grep(root, files, maxn, is_flutter, defer=()):
    scope = [f for f in read_scope(files) if f.startswith(('lib/', 'bin/'))] or read_scope(files)
    hits = defaultdict(list)
    dispose_hits = []
    file_hits = []
    catch_hits = []
    for rel in scope:
        try:
            raw = open(os.path.join(root, rel), errors='replace').read()
        except OSError:
            continue
        lines = raw.split('\n')
        code_lines = [LINE_COMMENT.sub(r'\1', l) for l in lines]
        code = '\n'.join(code_lines)
        masked = mask_strings(code)
        starts = [0]
        for l in code_lines:
            starts.append(starts[-1] + len(l) + 1)
        builds = build_ranges(masked)
        classes = class_ranges(masked)
        token_classes = [(a, b) for n, a, b in classes if re.search(r'(?:Colors|Colours|Palette|Tokens)$', n)]
        class_bodies = [(a, b) for _n, a, b in classes]

        def add(hid, i):
            hits[hid].append(f"{rel}:{i}  {lines[i - 1].strip()[:120]}")

        for hid, sev, desc, rx, filt in HEURISTICS:
            if filt and filt.startswith('flutter') and is_flutter != '1':
                continue
            if filt == 'flutter-nontheme' and is_theme_file(rel):
                continue
            if rx is None:
                continue
            for i, l in enumerate(code_lines, 1):
                m = rx.search(l)
                if not m:
                    continue
                off = starts[i - 1] + m.start()
                if hid in OVERRIDE_CHECKED and has_override(code_lines, i - 1):
                    continue  # framework/interface member: the name isn't this file's choice
                if hid == 'hardcoded-color':
                    if inside(token_classes, off) or \
                            re.match(r'^\s*(?:static\s+)?(?:const|final)\s+(?:Color\s+)?\w+\s*=\s*(?:const\s+)?Color\s*\(', l):
                        continue  # a palette definition is where the colour belongs
                elif hid == 'unique-key':
                    if not inside(builds, off):
                        if re.match(r'^\s*(?:late\s+)?(?:final|var|static\s+final)?\s*(?:Key\s+|UniqueKey\s+)?_?\w+\s*=\s*UniqueKey\s*\(\s*\)\s*;', l) \
                                and inside(class_bodies, off):
                            continue  # a State/class field: one stable key per instance
                        add('unique-key-outside-build', i)
                        continue
                elif hid == 'dynamic-in-api':
                    if re.search(r'(?:^|[(,:=]\s*)\(\s*(?:[^()]*,\s*)?(?:final\s+)?dynamic\s+\w+[^()]*\)\s*(?:async\s*)?(?:\{|=>)', l) and \
                            not re.search(r'\w\s*\(\s*(?:[^()]*,\s*)?(?:final\s+)?dynamic\s+\w+[^()]*\)\s*(?:async\s*)?(?:\{|=>)', l):
                        add('dynamic-closure-param', i)
                        continue
                elif hid == 'then-chain':
                    if re.match(r'\.then\s*\(\s*\w+\s*:', l[m.start():]):
                        continue  # flutter_animate's `.then(delay: ...)`, not Future.then
                    kind, is_async = statement_context(masked, off)
                    if kind == 'stmt' and not is_async:
                        continue  # fire-and-forget in a sync callback
                add(hid, i)
        if is_flutter == '1':
            for off in future_in_build_hits(masked, builds):
                add('future-in-build', code.count('\n', 0, off) + 1)
        # lifecycle: disposables created and never disposed/cancelled/closed in this file
        verbs = ('dispose', 'close', 'cancel')
        for m in re.finditer(r'(\b_?\w+)\s*=\s*(?:' + DISPOSABLE + r')\s*\(', code):
            if not released(m.group(1), code, verbs):
                ln = code.count('\n', 0, m.start()) + 1
                dispose_hits.append(f"{rel}:{ln}  `{m.group(1)}` created, no dispose()/close() found in file")
        for m in re.finditer(r'(\b_?\w+)\s*=\s*(?:([\w.?!()]+)\.listen\s*\(|Timer(?:\.periodic)?\s*\()', code):
            if m.group(2) and re.search(r'(?:^|\.)ref$', m.group(2)):
                continue  # ref.listen: Riverpod closes it with the widget/provider
            if not released(m.group(1), code, verbs):
                ln = code.count('\n', 0, m.start()) + 1
                dispose_hits.append(f"{rel}:{ln}  `{m.group(1)}` (subscription/timer) never cancelled in file")
        for m in SWALLOWED_CATCH.finditer(code):
            ln = code.count('\n', 0, m.start()) + 1
            catch_hits.append(f"{rel}:{ln}  {' '.join(m.group(0).split())[:120]}")
        base = os.path.basename(rel)
        if re.match(r'^(utils?|helpers?|common|misc|constants?|manager)s?\.dart$', base) or \
           re.search(r'_(utils?|helpers?|manager)\.dart$', base):
            names = [n for n in top_level_names(masked) if n != 'main']
            stem = base[:-5]
            if not (len(names) == 1 and snake(names[0]) == stem):
                file_hits.append(f"{rel}  grab-bag file name — name the file after what it contains")
    sections = [('undisposed-resource', 'high',
                 "Disposable created but not disposed/cancelled/closed in the same file (Flutter: dispose what you create). "
                 "False positive if ownership is handed elsewhere.", dispose_hits),
                ('swallowed-catch', 'high',
                 "catch block that is empty or only returns a default — Effective Dart: DON'T discard errors; log, report, rethrow, or map to a typed failure.",
                 catch_hits)]
    for hid, sev, desc, _, _ in HEURISTICS:
        sections.append((hid, sev, desc, hits[hid]))
        if hid in VARIANT_OF:
            vid = VARIANT_OF[hid]
            sections.append((vid, VARIANTS[vid][0], VARIANTS[vid][1], hits[vid]))
    sections.append(('grab-bag-file', 'low',
                     "utils/helpers/common file names holding several unrelated declarations (a file named after its only class is fine).",
                     file_hits))
    any_hit = False
    for hid, sev, desc, items in sections:
        if not items:
            continue
        any_hit = True
        if hid in DEFERRED and DEFERRED[hid][0] in defer:
            _flag, section, why = DEFERRED[hid]
            print(f"  [CANDIDATE] {hid} ({sev}) x{len(items)} — see {section}: {why}; report each once, there")
            continue
        print(f"  [CANDIDATE] {hid} ({sev}) x{len(items)} — {desc}")
        for it in items[:maxn]:
            print(f"      {it}")
        if len(items) > maxn:
            print(f"      ... {len(items) - maxn} more")
    if not any_hit:
        print("  no heuristic candidates")


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'analyzer':
        cmd_analyzer(args[0], args[1], args[2], int(args[3]))
    elif cmd == 'fix':
        cmd_fix(args[0], args[1], args[2], int(args[3]))
    elif cmd == 'mkoptions':
        cmd_mkoptions(*args)
    elif cmd == 'extra':
        cmd_extra(args[0], args[1], args[2], int(args[3]), args[4], args[5])
    elif cmd == 'grep':
        cmd_grep(args[0], args[1], int(args[2]), args[3], set(args[4:]))
    elif cmd == 'errors':
        cmd_errors(args[0], args[1], args[2])
    elif cmd == 'context':
        cmd_context(args[0], args[1])
    elif cmd == 'scope':
        cmd_scope(args[0], args[1], args[2] if len(args) > 2 else '')
    elif cmd == 'audit':
        cmd_audit(args[0], args[1], args[2], int(args[3]))
    elif cmd == 'summary':
        cmd_summary(*args[:6])
    else:
        sys.exit(f"unknown subcommand {cmd}")


if __name__ == '__main__':
    main()
