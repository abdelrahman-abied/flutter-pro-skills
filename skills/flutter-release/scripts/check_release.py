#!/usr/bin/env python3
"""check_release.py: find release, signing, flavor, store-readiness and CI/CD problems in a Flutter project (read-only).

Usage:
  python3 -I check_release.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing project-relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (flavors are compared across Gradle, Xcode and
             lib/main_*.dart); only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  REL-001 release-signed-with-debug-key      REL-007 debug-switch-left-on
  REL-002 signing-file-not-ignored           REL-008 target-sdk-below-play-minimum
  REL-003 placeholder-application-id         REL-009 usage-description-missing
  REL-004 flavor-mismatch                    REL-010 pr-target-runs-untrusted-code
  REL-005 environment-by-build-mode          REL-011 secret-printed-in-ci
  REL-006 flavor-read-outside-root           REL-012 signing-key-exposed-in-ci

Besides lib/**.dart it reads android/**/build.gradle(.kts), android/key.properties (presence only),
ios/Runner/Info.plist, ios/**/*.xcconfig, ios/Runner.xcodeproj (project.pbxproj, shared schemes),
pubspec.yaml, .gitignore files, .github/workflows/*.y*ml, codemagic.yaml and fastlane/**. When the
project sits inside a larger repository, that repository's workflows and codemagic.yaml are read too
if they mention the project's folder; their findings carry a ../ path.

App-aware: a sample or example app (no release intent, or inside an examples/ or samples/ folder)
gets info at most for the store-readiness rules (REL-001, REL-003, REL-008).

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py --json when that
sibling skill is installed; otherwise a path-based fallback is used and the output says so.

Suppression (in the analysed files):
  // rel-ignore: REL-005 <reason>        (Dart, Gradle, xcconfig) on the reported line or the line above
  # rel-ignore: REL-011 <reason>         (YAML, fastlane, properties)
  // rel-ignore-file: REL-006 <reason>   anywhere in the file (also with #)

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import fnmatch
import json
import os
import plistlib
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/release@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

# Google Play target API level for new apps and app updates. Google raises it every year at the end
# of August; update both values when it does (developer.android.com/google/play/requirements/target-sdk).
PLAY_MIN_TARGET_SDK = 35
PLAY_MIN_TARGET_SDK_SINCE = '2025-08-31'

RULES = {
    'REL-001': ('release-signed-with-debug-key', 'high',
                'The release build type is signed with the debug keystore. Google Play rejects a debug-signed '
                'upload, and every machine has a different debug key, so builds are not reproducible and updates '
                'cannot be installed over each other. Sign release with an upload key loaded from key.properties '
                'or CI secrets.'),
    'REL-002': ('signing-file-not-ignored', 'high',
                'A keystore, key.properties, .p12, .p8 or provisioning profile is in the project and no '
                '.gitignore covers it, so it is (or will be) committed. Anyone with read access can then sign '
                'builds as you. Ignore it, remove it from history, and rotate the key.'),
    'REL-003': ('placeholder-application-id', 'medium',
                'The Android applicationId or the iOS bundle identifier is still com.example.*. The stores refuse '
                'com.example ids, and the id can never change after the first upload, so pick the final one '
                'before any release.'),
    'REL-004': ('flavor-mismatch', 'medium',
                'Flavors disagree between Android productFlavors, iOS schemes and lib/main_<flavor>.dart. '
                '`flutter run --flavor x` then fails on one platform, or an entrypoint exists that no flavor '
                'builds. Keep one list of flavors and mirror it on every platform.'),
    'REL-005': ('environment-by-build-mode', 'medium',
                'The environment (base URL, host or key) is chosen with kDebugMode/kReleaseMode/kProfileMode. '
                'A profile build then talks to production, a release build can never be pointed at staging, '
                'and QA tests a different backend than users. Choose it per flavor or --dart-define-from-file '
                'and inject one config object at the root.'),
    'REL-006': ('flavor-read-outside-root', 'low',
                'Feature, logic or data code reads the flavor or environment directly (appFlavor, '
                'String.fromEnvironment, a FlavorConfig singleton). Each such read is a hidden global that '
                'tests cannot override. Read it once in the composition root and inject the values.'),
    'REL-007': ('debug-switch-left-on', 'medium',
                'A debugging switch is hard-coded on: performance overlay, checkerboarding, the semantics '
                'debugger, or a debugPaint* flag. Some of them render in profile and release builds too, and '
                'all of them distort what developers see. Remove it, or tie it to a dev-only setting.'),
    'REL-008': ('target-sdk-below-play-minimum', 'medium',
                'targetSdk is hard-coded below the level Google Play requires for new apps and updates, so the '
                'upload is rejected. Use flutter.targetSdkVersion, or raise the number and test the behaviour '
                'changes of each skipped Android version.'),
    'REL-009': ('usage-description-missing', 'medium',
                'A plugin that needs an iOS permission is a dependency, but ios/Runner/Info.plist has no usage '
                'description for it. iOS terminates the app the moment the permission is requested, and App '
                'Store processing rejects binaries that use the API without the purpose string.'),
    'REL-010': ('pr-target-runs-untrusted-code', 'high',
                'A pull_request_target workflow checks out the pull request\'s code and then runs it. That job '
                'has a write token and the repository secrets, so anyone who opens a pull request can steal '
                'them or push to the repository. Use pull_request for building PR code.'),
    'REL-011': ('secret-printed-in-ci', 'high',
                'A CI step prints a secret to the build log (echo/printf/Write-Host of a secret). Masking only '
                'hides exact single-line values; multi-line, encoded or partial copies leak to anyone who can '
                'read the logs. Write secrets to a file or pass them through env, never to stdout.'),
    'REL-012': ('signing-key-exposed-in-ci', 'high',
                'CI decodes a signing key into the workspace and then uploads a build artifact that includes it, '
                'or leaves it behind on a persistent runner. Decode keys to $RUNNER_TEMP, upload only the build '
                'outputs, and delete the key in an always() step.'),
}
STORE_RULES = ('REL-001', 'REL-003', 'REL-008')

# where the environment config lives, per architecture (appended to REL-005/006 notes)
ENV_PLACE = {
    'mvn': 'MVN: build AppConfig in main_<flavor>.dart and pass it as ProviderScope(overrides: '
           '[appConfigProvider.overrideWithValue(config)]); the Dio provider in core/network reads it, use cases '
           'and notifiers never do.',
    'riverpod': 'Riverpod: override a keepAlive appConfigProvider in ProviderScope(overrides: [...]) from '
                'main_<flavor>.dart; only the providers that build clients read it.',
    'mvvm': 'MVVM: main_<flavor>.dart builds AppConfig and passes it to the API service in the root provider '
            'list (as compass_app does with main_development.dart and main_staging.dart); view models never read it.',
    'bloc': 'Bloc: main_<flavor>.dart calls bootstrap(config), which builds the API client from config.baseUrl and '
            'hands repositories down with RepositoryProvider; blocs and widgets never read the flavor.',
    'provider': 'Provider: build AppConfig in main_<flavor>.dart and expose it with a root Provider<AppConfig>.value; '
                'services take it in their constructor.',
    'getx': 'GetX: Get.put(config, permanent: true) in the initial binding called from main_<flavor>.dart; '
            'services read it, controllers and views do not.',
    'mvc': 'MVC: build AppConfig in main_<flavor>.dart and pass it to the model/service layer by constructor.',
    'setstate': 'Build AppConfig in main_<flavor>.dart and pass it down by constructor to the data layer.',
    'unknown': 'Build one AppConfig in main_<flavor>.dart (or from --dart-define-from-file) and inject it.',
}
GETIT_PLACE = 'get_it: GetIt.I.registerSingleton<AppConfig>(config) in main_<flavor>.dart before runApp, ' \
              'and resolve it only where clients are built.'
ARCH_CITE = 'Cross-reference: AP-hardcoded-config-in-sources (flutter-architecture).'

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.gen|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
GENERATED_HEADER = re.compile(r'GENERATED CODE - DO NOT MODIFY|Generated file\. Do not edit|'
                              r'AUTO-GENERATED FILE, DO NOT MODIFY|Generated by: OpenAPI Generator', re.I)
SUPPRESS_RE = re.compile(r'rel-ignore(-file)?\s*:\s*((?:REL-\d{3})(?:\s*,\s*REL-\d{3})*)\s*(.*)')
SKIP_DIRS = {'.git', 'build', '.dart_tool', 'Pods', 'node_modules', '.symlinks', 'ephemeral', '.gradle',
             '.idea', '.fvm', '.pub-cache', 'DerivedData', '.cxx'}
# signing material; debug.keystore is the public Android debug key and is not reported
SIGNING_FILE_RE = re.compile(r'(\.jks|\.keystore|\.p12|\.p8|\.mobileprovision|\.provisionprofile)$|'
                             r'^(key|keystore|signing)\.properties$', re.I)
EXAMPLE_SEGS = {'example', 'examples', 'sample', 'samples'}

# dependency -> (required Info.plist keys, any-of alternatives)
USAGE_KEYS = {
    'camera': ['NSCameraUsageDescription'],
    'mobile_scanner': ['NSCameraUsageDescription'],
    'qr_code_scanner': ['NSCameraUsageDescription'],
    'qr_code_scanner_plus': ['NSCameraUsageDescription'],
    'local_auth': ['NSFaceIDUsageDescription'],
    'geolocator': ['NSLocationWhenInUseUsageDescription|NSLocationAlwaysAndWhenInUseUsageDescription'],
    'location': ['NSLocationWhenInUseUsageDescription|NSLocationAlwaysAndWhenInUseUsageDescription'],
    'record': ['NSMicrophoneUsageDescription'],
    'flutter_sound': ['NSMicrophoneUsageDescription'],
    'speech_to_text': ['NSSpeechRecognitionUsageDescription', 'NSMicrophoneUsageDescription'],
    'flutter_contacts': ['NSContactsUsageDescription'],
    'contacts_service': ['NSContactsUsageDescription'],
    'photo_manager': ['NSPhotoLibraryUsageDescription'],
    'health': ['NSHealthShareUsageDescription'],
    'flutter_blue_plus': ['NSBluetoothAlwaysUsageDescription'],
    'flutter_reactive_ble': ['NSBluetoothAlwaysUsageDescription'],
    'device_calendar': ['NSCalendarsUsageDescription|NSCalendarsFullAccessUsageDescription'],
    'gal': ['NSPhotoLibraryAddUsageDescription'],
    'image_gallery_saver': ['NSPhotoLibraryAddUsageDescription'],
    'app_tracking_transparency': ['NSUserTrackingUsageDescription'],
    'nfc_manager': ['NFCReaderUsageDescription'],
}

# REL-007: (pattern, severity, what)
DEBUG_SWITCHES = [
    (re.compile(r'\bshowPerformanceOverlay\s*:\s*true\b'), 'medium', 'the performance overlay renders in profile and release builds'),
    (re.compile(r'\bcheckerboardRasterCacheImages\s*:\s*true\b'), 'medium', 'checkerboarding renders in profile and release builds'),
    (re.compile(r'\bcheckerboardOffscreenLayers\s*:\s*true\b'), 'medium', 'checkerboarding renders in profile and release builds'),
    (re.compile(r'\bshowSemanticsDebugger\s*:\s*true\b'), 'medium', 'the semantics debugger replaces the UI in every build mode'),
    (re.compile(r'\bdebugShowMaterialGrid\s*:\s*true\b'), 'low', 'debug builds only, but every developer sees a baseline grid'),
    (re.compile(r'\b(debugPaintSizeEnabled|debugPaintBaselinesEnabled|debugPaintLayerBordersEnabled|'
                r'debugPaintPointersEnabled|debugRepaintRainbowEnabled|debugRepaintTextRainbowEnabled)\s*=\s*true\b'),
     'low', 'debug builds only, but it paints over every screen for every developer'),
]

BUILD_MODE_RE = re.compile(r'\bk(?:Debug|Release|Profile)Mode\b|bool\.fromEnvironment\(\s*[\'"]dart\.vm\.product[\'"]\s*\)')
URLISH_NAME_RE = re.compile(r'(?i)(url|uri|host|endpoint|server|domain|baseapi|apibase|backend)')
URL_LIT_RE = re.compile(r'''^r?['"](?:https?|wss?)://''')
FLAVOR_READ_RE = re.compile(r'\bappFlavor\b|\bF\.(?:appFlavor|name|title)\b|\bFlavorConfig\s*\.\s*(?:instance|of)\b|'
                            r'\bString\.fromEnvironment\(\s*[\'"](?:FLAVOR|FLUTTER_APP_FLAVOR|APP_FLAVOR|ENV|ENVIRONMENT|'
                            r'APP_ENV|APP_ENVIRONMENT|BUILD_ENV)[\'"]')
STRONG_SECRET_NAME_RE = re.compile(r'(?i)(password|passwd|secret|token|private_?key|keystore|signing_?key|'
                                   r'api_?key|certificate|cert_p12|p12|credentials|service_account|_jks|key_jks)')
SIGNING_PATH_RE = re.compile(r'(?i)(\.jks|\.keystore|\.p12|\.p8|\.mobileprovision|key\.properties)\b')
RELEASE_CI_RE = re.compile(r'(?i)(\.jks\b|\.keystore\b|key\.properties|\.p12\b|\.mobileprovision|upload-google-play|'
                           r'app-store-connect|appstore|testflight|fastlane|google-play|play_store|playstore|'
                           r'apple-actions/import-codesign-certs|\bpilot\b|supply\b)')
HOSTED_RUNNER_RE = re.compile(r'^(ubuntu|macos|windows)-[\w.-]+$|^\$\{\{')

# ---------------------------------------------------------------------------------------- lexing (Dart; also good enough for Groovy, Kotlin and pbxproj)

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


# ---------------------------------------------------------------------------------------- files


def _suppressions(raw):
    """(per-line {line: {id: reason}}, file-wide {id: reason}) from //, # or <!-- comments."""
    per_line, per_file = {}, {}
    for ln, text in enumerate(raw.split('\n'), 1):
        if 'rel-ignore' not in text:
            continue
        mm = re.search(r'(?://|#|<!--)\s*' + SUPPRESS_RE.pattern, text)
        if not mm:
            continue
        ids = [x.strip() for x in mm.group(2).split(',')]
        reason = re.sub(r'\s*-->\s*$', '', mm.group(3)).strip() or '(no reason given)'
        for rid in ids:
            if mm.group(1):
                per_file[rid] = reason
            else:
                per_line.setdefault(ln, {})[rid] = reason
    return per_line, per_file


class SrcFile(object):
    """Any analysed file. Dart, Gradle and pbxproj files are lexed (comments blanked, strings masked)."""

    def __init__(self, root, rel, kind):
        self.rel = rel
        self.kind = kind
        with open(os.path.normpath(os.path.join(root, rel)), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.lines = self.raw.split('\n')
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.suppress_line, self.suppress_file = _suppressions(self.raw)
        self.layer, self.role = 'other', 'other'
        if kind in ('dart', 'gradle', 'pbxproj'):
            self.code, self.masked, _iv, _c, _s = lex(self.raw)
            self.braces = match_pairs(self.masked, '{', '}')
            self.parens = match_pairs(self.masked, '(', ')')
            self.opens = sorted(k for k, v in self.braces.items() if v > k)
        else:
            self.code = self.masked = self.raw
            self.braces, self.parens, self.opens = {}, {}, []

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def line_text(self, ln, limit=120):
        t = ' '.join(self.lines[ln - 1].split()) if 0 < ln <= len(self.lines) else ''
        return t if len(t) <= limit else t[:limit - 3] + '...'

    def enclosing_opens(self, pos):
        """Brace opens enclosing pos, innermost first."""
        out = []
        for o in self.opens:
            if o >= pos:
                break
            if self.braces[o] > pos:
                out.append(o)
        return out[::-1]

    def header(self, o):
        """The text before brace o, back to the previous statement boundary."""
        k = o - 1
        while k >= 0 and self.masked[k] not in ';{}':
            k -= 1
        return self.code[k + 1:o]

    def blocks(self, name_re, lo=0, hi=None):
        """[(start, open, close)] for `<name_re> {` blocks within [lo, hi)."""
        hi = len(self.code) if hi is None else hi
        out = []
        for mm in re.finditer(name_re + r'\s*\{', self.code[lo:hi]):
            o = lo + mm.end() - 1
            if self.masked[o] == '{' and o in self.braces:
                out.append((lo + mm.start(), o, self.braces[o]))
        return out


# ---------------------------------------------------------------------------------------- .gitignore


def _gi_regex(pat):
    out, i, n = '', 0, len(pat)
    while i < n:
        c = pat[i]
        if pat.startswith('**/', i):
            out += '(?:.*/)?'
            i += 3
        elif pat.startswith('/**', i) and i + 3 == n:
            out += '/.*'
            i += 3
        elif pat.startswith('**', i):
            out += '.*'
            i += 2
        elif c == '*':
            out += '[^/]*'
            i += 1
        elif c == '?':
            out += '[^/]'
            i += 1
        elif c == '[':
            j = pat.find(']', i + 1)
            if j < 0:
                out += re.escape(c)
                i += 1
            else:
                body = pat[i + 1:j].replace('\\', '\\\\')
                if body.startswith('!'):
                    body = '^' + body[1:]
                out += '[' + body + ']'
                i = j + 1
        elif c == '\\' and i + 1 < n:
            out += re.escape(pat[i + 1])
            i += 2
        else:
            out += re.escape(c)
            i += 1
    return out


class GitIgnore(object):
    """A small .gitignore evaluator (nested files, negation, anchoring, dir-only patterns, **)."""

    def __init__(self):
        self.rules = []   # (base_abs_dir, regex, negate, dir_only), shallow files first

    def add_file(self, path):
        base = os.path.dirname(os.path.abspath(path))
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                lines = fh.read().split('\n')
        except OSError:
            return
        for line in lines:
            line = line.rstrip('\r')
            if not line.strip() or line.startswith('#'):
                continue
            line = re.sub(r'(?<!\\)\s+$', '', line)
            neg = line.startswith('!')
            if neg:
                line = line[1:]
            dir_only = line.endswith('/')
            line = line.rstrip('/')
            if not line:
                continue
            anchored = '/' in line
            line = line.lstrip('/')
            rx = _gi_regex(line)
            if not anchored:
                rx = '(?:.*/)?' + rx
            self.rules.append((base, re.compile('^' + rx + '$'), neg, dir_only))

    def ignored(self, abs_path):
        abs_path = os.path.abspath(abs_path)
        # a path is ignored when it or one of its parent directories is
        parts = []
        p = abs_path
        while True:
            parent = os.path.dirname(p)
            if parent == p:
                break
            parts.append(p)
            p = parent
        for cand in reversed(parts):
            is_dir = cand != abs_path
            state = None
            for base, rx, neg, dir_only in self.rules:
                if not (cand + os.sep).startswith(base + os.sep) or cand == base:
                    continue
                rel = os.path.relpath(cand, base).replace(os.sep, '/')
                if dir_only and not is_dir:
                    continue
                if rx.match(rel):
                    state = not neg
            if state:
                return True
        return False


# ---------------------------------------------------------------------------------------- YAML (subset)

KEY_RE = re.compile(r'''^(?:"((?:[^"\\]|\\.)*)"|'((?:[^']|'')*)'|([^\s'"#\-\[{][^:]*?|-[^\s:][^:]*?))\s*:(?:\s+(.*)|$)''')
BLOCK_IND_RE = re.compile(r'(?:^|:\s+)(?:&\S+\s+)?[|>][-+]?[0-9]?$')


def _strip_yaml_comment(s):
    q = None
    for i, c in enumerate(s):
        if q:
            if c == q:
                q = None
        elif c in '\'"' and (i == 0 or s[i - 1] in ' :[{,-'):
            q = c
        elif c == '#' and (i == 0 or s[i - 1] in ' \t'):
            return s[:i].rstrip()
    return s.rstrip()


def yaml_vlines(raw):
    lines = raw.split('\n')
    out, i, n = [], 0, len(lines)
    while i < n:
        s = lines[i].rstrip()
        st = s.lstrip()
        if not st or st.startswith('#') or st in ('---', '...'):
            i += 1
            continue
        ind = len(s) - len(st)
        content = _strip_yaml_comment(st)
        while content == '-' or content.startswith('- '):
            out.append({'ind': ind, 'text': '-', 'ln': i + 1, 'block': None})
            rest = content[1:]
            ind += 1 + (len(rest) - len(rest.lstrip()))
            content = rest.strip()
            if re.match(r'^&\S+$', content):
                content = ''
        if not content:
            i += 1
            continue
        vl = {'ind': ind, 'text': content, 'ln': i + 1, 'block': None}
        out.append(vl)
        j = i + 1
        if BLOCK_IND_RE.search(content):
            block = []
            while j < n and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > ind):
                block.append((j + 1, lines[j]))
                j += 1
            while block and not block[-1][1].strip():
                block.pop()
            vl['block'] = block
        elif content.count('[') > content.count(']') or content.count('{') > content.count('}'):
            while j < n and (content.count('[') > content.count(']') or content.count('{') > content.count('}')):
                content += ' ' + _strip_yaml_comment(lines[j].strip())
                j += 1
            vl['text'] = content
        i = j
    return out


def _scalar(v, ln, block=None):
    v = v or ''
    v = re.sub(r'^&\S+\s*', '', v)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '\'"':
        v = v[1:-1]
    return {'t': 'scalar', 'v': v, 'ln': ln, 'block': block}


def _parse_node(vls, i):
    if i >= len(vls):
        return None, i
    if vls[i]['text'] == '-':
        return _parse_seq(vls, i, vls[i]['ind'])
    return _parse_map(vls, i, vls[i]['ind'])


def _parse_seq(vls, i, ind):
    node = {'t': 'seq', 'items': [], 'ln': vls[i]['ln']}
    while i < len(vls) and vls[i]['ind'] == ind and vls[i]['text'] == '-':
        ln = vls[i]['ln']
        i += 1
        if i < len(vls) and vls[i]['ind'] > ind:
            child, i = _parse_node(vls, i)
        else:
            child = _scalar('', ln)
        node['items'].append(child)
    return node, i


def _parse_map(vls, i, ind):
    first = vls[i]
    if not KEY_RE.match(first['text']):
        node = _scalar(first['text'], first['ln'], first['block'])
        i += 1
        while i < len(vls) and vls[i]['ind'] > ind and vls[i]['text'] != '-':
            node['v'] += ' ' + vls[i]['text']
            i += 1
        return node, i
    node = {'t': 'map', 'items': [], 'ln': first['ln']}
    while i < len(vls) and vls[i]['ind'] >= ind:
        v = vls[i]
        if v['ind'] > ind or v['text'] == '-':
            i += 1
            continue
        mm = KEY_RE.match(v['text'])
        if not mm:
            i += 1
            continue
        key = next((g for g in mm.groups()[:3] if g is not None), '')
        val = mm.group(4)
        i += 1
        if v['block'] is not None:
            child = _scalar(val, v['ln'], v['block'])
        elif val is not None and val.strip() and not re.match(r'^&\S+$', val.strip()):
            child = _scalar(val.strip(), v['ln'])
        elif i < len(vls) and (vls[i]['ind'] > ind or (vls[i]['ind'] == ind and vls[i]['text'] == '-')):
            child, i = _parse_node(vls, i)
        else:
            child = _scalar('', v['ln'])
        node['items'].append((key, child, v['ln']))
    return node, i


def parse_yaml(raw):
    vls = yaml_vlines(raw)
    if not vls:
        return {'t': 'map', 'items': [], 'ln': 1}
    node, _ = _parse_node(vls, 0)
    return node


def yget(node, key):
    if node and node['t'] == 'map':
        for k, v, _ in node['items']:
            if k == key:
                return v
    return None


def yitems(node):
    if node and node['t'] == 'map':
        return node['items']
    return []


def yseq(node):
    if node and node['t'] == 'seq':
        return node['items']
    return []


def ystr(node):
    if not node:
        return ''
    if node['t'] == 'scalar':
        if node['block'] is not None:
            return '\n'.join(t for _, t in node['block'])
        return node['v']
    if node['t'] == 'seq':
        return ' '.join(ystr(x) for x in node['items'])
    return ' '.join('%s: %s' % (k, ystr(v)) for k, v, _ in node['items'])


def ylines(node):
    """[(line, text)] of a scalar (block scalars line by line)."""
    if not node or node['t'] != 'scalar':
        return []
    if node['block'] is not None:
        return [(ln, t) for ln, t in node['block']]
    return [(node['ln'], node['v'])] if node['v'] else []


def yflow_list(node):
    if not node:
        return []
    if node['t'] == 'seq':
        return [ystr(x).strip() for x in node['items']]
    if node['t'] == 'map':
        return [k for k, _, _ in node['items']]
    v = node['v'].strip()
    if v.startswith('['):
        return [x.strip().strip('\'"') for x in v.strip('[]').split(',') if x.strip()]
    return [v] if v else []


# ---------------------------------------------------------------------------------------- shell helpers

PRINT_CMD_RE = re.compile(r'(?:^|[;&(`]\s*|\|\|\s*|\bthen\s+|\bdo\s+|\belse\s+)'
                          r'(echo|printf|print|puts|Write-Host|Write-Output|Write-Information)\b', re.I)


def print_segment(line, start):
    """(segment, reaches_log) for a print command starting at `start`."""
    q = None
    i, n = start, len(line)
    while i < n:
        c = line[i]
        if q:
            if c == q:
                q = None
            elif c == '\\' and q == '"':
                i += 1
        elif c in '\'"':
            q = c
        elif c == ';' or line.startswith('&&', i):
            return line[start:i], True
        elif line.startswith('||', i):
            return line[start:i], True
        elif c == '|':
            rest = line[i + 1:].lstrip()
            return line[start:i], bool(re.match(r'tee\b', rest))
        elif c == '>':
            if i > 0 and line[i - 1] in '=-':
                i += 1
                continue
            rest = line[i + 1:].lstrip('>').lstrip()
            to_log = bool(re.match(r'&[12]\b|/dev/(stderr|stdout)\b', rest))
            if i > 0 and line[i - 1] == '2' and rest.startswith('&1'):
                i += 1
                continue
            return line[start:i], to_log
        i += 1
    return line[start:], True


def secret_refs(seg, env_names):
    refs = re.findall(r'\$\{\{\s*secrets\.(\w+)\s*\}\}', seg)
    for name in env_names:
        if re.search(r'\$\{?' + re.escape(name) + r'\b|\$env:' + re.escape(name) + r'\b', seg):
            refs.append(name)
    return refs


DECODE_TO_RE = re.compile(r'>{1,2}\s*([\'"]?)([^\s\'";|&<>]+)\1')
OUTSIDE_WS_RE = re.compile(r'^(/|~|\$HOME\b|\$\{HOME\}|\$RUNNER_TEMP\b|\$\{RUNNER_TEMP\}|\$\{\{\s*runner\.temp\s*\}\}|'
                           r'\$TMPDIR\b|\$\{TMPDIR\}|\$CM_TEMP|\$TEMP\b|\$env:RUNNER_TEMP|\$env:TEMP)')


def materialised_key(text):
    """Workspace-relative-or-absolute path of a signing file written by this shell line, or None."""
    if not SIGNING_PATH_RE.search(text):
        return None
    for mm in DECODE_TO_RE.finditer(text):
        p = mm.group(2)
        if SIGNING_PATH_RE.search(p):
            if 'key.properties' in p.lower() and 'base64' not in text and 'storeFile' not in text:
                continue
            return p
    mm = re.search(r'(?:-out|--output|-o)\s+([\'"]?)([^\s\'";|&]+)\1', text)
    if mm and SIGNING_PATH_RE.search(mm.group(2)) and re.search(r'base64|openssl|gpg', text):
        return mm.group(2)
    return None


def ws_path(p, wd):
    p = re.sub(r'^(\$GITHUB_WORKSPACE|\$\{GITHUB_WORKSPACE\}|\$\{\{\s*github\.workspace\s*\}\}|\$\(pwd\)|\$PWD|'
               r'\$CM_BUILD_DIR|\$\{CM_BUILD_DIR\}|\$FCI_BUILD_DIR)/?', '', p)
    if OUTSIDE_WS_RE.match(p):
        return None
    if wd and not OUTSIDE_WS_RE.match(wd):
        wd = re.sub(r'^\$\{\{\s*github\.workspace\s*\}\}/?|^\./', '', wd)
        p = os.path.join(wd, p)
    return os.path.normpath(p).replace(os.sep, '/')


def path_covers(pattern, path):
    q = pattern.strip().strip('\'"')
    if not q or q.startswith('!'):
        return False
    q = re.sub(r'^\$\{\{\s*github\.workspace\s*\}\}/?|^\$GITHUB_WORKSPACE/?|^\$CM_BUILD_DIR/?', '', q)
    q = re.sub(r'^\./', '', q)
    if q in ('', '.', '*', '**', '**/*', '/'):
        return True
    if fnmatch.fnmatch(path, q):
        return True
    base = q.rstrip('/')
    while base.endswith('/**') or base.endswith('/*'):
        base = base.rsplit('/', 1)[0]
    if base and not re.search(r'[*?\[]', base) and path.startswith(base + '/'):
        return True
    return False


# ---------------------------------------------------------------------------------------- checker

ALIASES = {'prod': 'production', 'dev': 'development', 'stg': 'staging', 'stage': 'staging', 'qa': 'qa'}


def alias(name):
    n = name.lower()
    return ALIASES.get(n, n)


class Checker(object):
    def __init__(self, root, package, pubspec, files, profile, clean, di):
        self.root = root
        self.package = package
        self.pubspec = pubspec
        self.files = files
        self.profile = profile
        self.clean = clean
        self.di = di
        self.findings = []
        self.suppressed = []
        self.cache = {}
        self.git_root = self.find_git_root()
        self.gitignore = GitIgnore()
        self.intent = []
        self.android_flavors = {}       # name -> (SrcFile, line)
        self.ios_flavors = {}           # name -> (rel, line)
        self.entrypoints = {}           # name -> rel
        self.app_gradle = None
        self.pbx = None
        self.ci_files = []
        self.stats = {}

    # -- infrastructure
    def src(self, rel, kind):
        if rel not in self.cache:
            try:
                self.cache[rel] = SrcFile(self.root, rel, kind)
            except (OSError, UnicodeError):
                self.cache[rel] = None
        return self.cache[rel]

    def exists(self, rel):
        return os.path.isfile(os.path.join(self.root, rel))

    def find_git_root(self):
        p = self.root
        while True:
            if os.path.exists(os.path.join(p, '.git')):
                return p
            parent = os.path.dirname(p)
            if parent == p:
                return None
            p = parent

    def env_place(self):
        p = ENV_PLACE.get(self.profile, ENV_PLACE['unknown'])
        if 'get_it' in self.di and self.profile not in ('getx',):
            p += ' ' + GETIT_PLACE
        return p

    def add(self, sf, rid, line, evidence, note='', severity=None, env_place=False):
        sev = severity or RULES[rid][1]
        reason = sf.suppress_file.get(rid)
        if reason is None:
            for l in (line, line - 1):
                if rid in sf.suppress_line.get(l, {}):
                    reason = sf.suppress_line[l][rid]
                    break
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': sf.rel, 'line': line, 'reason': reason})
            return
        if env_place:
            note = (note + ' ' if note else '') + self.env_place()
        if rid in STORE_RULES and self.sample and sev != 'info':
            note = 'sample app (%s): graded info, not %s. %s' % (self.sample_reason, sev, note)
            sev = 'info'
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': sf.rel, 'line': line,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note.strip()})

    # -- discovery
    def walk(self, start, max_depth=8):
        base = os.path.join(self.root, start) if start else self.root
        if not os.path.isdir(base):
            return
        for dp, dns, fns in os.walk(base):
            depth = os.path.relpath(dp, self.root).count(os.sep)
            dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not (depth >= max_depth))
            if dp != self.root and os.path.isfile(os.path.join(dp, 'pubspec.yaml')) and dp != base:
                dns[:] = []        # a nested package is its own project
                continue
            for fn in sorted(fns):
                yield os.path.relpath(os.path.join(dp, fn), self.root).replace(os.sep, '/')

    def load_gitignores(self):
        stop = self.git_root or self.root
        anc = []
        p = self.root
        while True:
            parent = os.path.dirname(p)
            if p == stop or parent == p:
                break
            p = parent
            anc.append(p)
        for d in reversed(anc):
            g = os.path.join(d, '.gitignore')
            if os.path.isfile(g):
                self.gitignore.add_file(g)
        for rel in sorted(self.walk(''), key=lambda r: r.count('/')):
            if rel.endswith('.gitignore') and os.path.basename(rel) == '.gitignore':
                self.gitignore.add_file(os.path.join(self.root, rel))

    def discover_ci(self):
        out = []
        wf = os.path.join(self.root, '.github', 'workflows')
        if os.path.isdir(wf):
            out += ['.github/workflows/' + f for f in sorted(os.listdir(wf)) if f.endswith(('.yml', '.yaml'))]
        for f in ('codemagic.yaml', 'codemagic.yml'):
            if self.exists(f):
                out.append(f)
        if self.git_root and self.git_root != self.root:
            relp = os.path.relpath(self.root, self.git_root).replace(os.sep, '/')
            mention = re.compile(r'(?<![\w.-])' + re.escape(relp) + r'(?![\w-])')
            cands = []
            gwf = os.path.join(self.git_root, '.github', 'workflows')
            if os.path.isdir(gwf):
                cands += [os.path.join(gwf, f) for f in sorted(os.listdir(gwf)) if f.endswith(('.yml', '.yaml'))]
            for f in ('codemagic.yaml', 'codemagic.yml'):
                if os.path.isfile(os.path.join(self.git_root, f)):
                    cands.append(os.path.join(self.git_root, f))
            for c in cands:
                try:
                    with open(c, encoding='utf-8', errors='replace') as fh:
                        if mention.search(fh.read()):
                            out.append(os.path.relpath(c, self.root).replace(os.sep, '/'))
                except OSError:
                    pass
        self.ci_files = out
        self.fastlane = [d for d in ('fastlane', 'android/fastlane', 'ios/fastlane')
                         if os.path.isdir(os.path.join(self.root, d))]

    # -- run
    def run(self):
        self.has_android = os.path.isdir(os.path.join(self.root, 'android'))
        self.has_ios = os.path.isdir(os.path.join(self.root, 'ios'))
        self.load_gitignores()
        self.discover_ci()
        self.read_android()
        self.read_ios()
        for df in self.files:
            mm = re.match(r'^main_([A-Za-z0-9_]+)\.dart$', os.path.basename(df.rel))
            if mm and df.rel.startswith('lib/'):
                self.entrypoints[mm.group(1).lower()] = df.rel
        self.compute_intent()
        self.rel_signing()
        self.rel_android_store()
        self.rel_ios_store()
        self.rel_flavors()
        self.rel_usage_descriptions()
        for df in self.files:
            self.rel_build_mode(df)
            self.rel_flavor_reads(df)
            self.rel_debug_switches(df)
        for rel in self.ci_files:
            sf = self.src(rel, 'yaml')
            if not sf:
                continue
            if os.path.basename(rel).startswith('codemagic'):
                self.check_codemagic(sf)
            else:
                self.check_workflow(sf)
        self.stats = {
            'platforms': {'android': self.has_android, 'ios': self.has_ios},
            'platform_rules': 'run' if (self.has_android or self.has_ios) else
                              'skipped (no android/ or ios/ folder: a pure Dart package or a web/desktop-only app)',
            'app_kind': ('package' if not (self.has_android or self.has_ios) else
                         'sample' if self.sample else 'app'),
            'release_intent': self.intent,
            'flavors': {'android': sorted(self.android_flavors), 'ios': sorted(self.ios_flavors),
                        'entrypoints': sorted(self.entrypoints)},
            'build_files': sorted(r for r in self.cache if r.endswith(('.gradle', '.gradle.kts')) and self.cache[r]),
            'ci_files': self.ci_files + self.fastlane,
        }

    # -- Android
    def read_android(self):
        for rel in ('android/app/build.gradle.kts', 'android/app/build.gradle'):
            if self.exists(rel):
                self.app_gradle = self.src(rel, 'gradle')
                break
        g = self.app_gradle
        if not g:
            return
        for s, o, c in g.blocks(r'\bproductFlavors'):
            for mm in re.finditer(r'(?:\b(?:create|register|maybeCreate)\(\s*"(\w+)"\s*\)|(?<![\w.])(\w+))\s*\{',
                                  g.code[o + 1:c]):
                pos = o + 1 + mm.start()
                encl = g.enclosing_opens(pos)
                if not encl or encl[0] != o:
                    continue
                name = mm.group(1) or mm.group(2)
                if name in ('all', 'configureEach', 'if', 'else'):
                    continue
                self.android_flavors.setdefault(name.lower(), (g, g.line_of(pos)))
        self.flavor_block_line = None
        for s, o, c in g.blocks(r'\bproductFlavors'):
            self.flavor_block_line = g.line_of(s)
            break

    def gradle_value(self, key):
        """(value, line) of `key "x"` / `key = "x"`, preferring defaultConfig."""
        g = self.app_gradle
        rx = re.compile(r'\b' + key + r'\s*(?:=\s*|\(\s*|\s+)["\']([^"\']+)["\']')
        dc = g.blocks(r'\bdefaultConfig')
        for lo, hi in ([(dc[0][1], dc[0][2])] if dc else []) + [(0, len(g.code))]:
            mm = rx.search(g.code, lo, hi)
            if mm:
                return mm.group(1), g.line_of(mm.start())
        return None, None

    def rel_android_store(self):
        g = self.app_gradle
        if not g:
            return
        appid, ln = self.gradle_value('applicationId')
        if not appid:
            appid, ln = self.gradle_value('namespace')
        if appid and (appid == 'com.example' or appid.startswith('com.example.')):
            self.add(g, 'REL-003', ln, g.line_text(ln),
                     'Android applicationId %s. Use a reverse domain you own (com.yourcompany.app); Play keys the '
                     'listing, upgrades and Play App Signing to it forever. Change namespace too only if you want; '
                     'it is the code namespace, not the store id.' % appid)
        for mm in re.finditer(r'\btargetSdk(?:Version)?\s*(?:=\s*|\(\s*|\s+)(\d+)\b', g.code):
            v = int(mm.group(1))
            if v < PLAY_MIN_TARGET_SDK:
                ln = g.line_of(mm.start())
                self.add(g, 'REL-008', ln, g.line_text(ln),
                         'targetSdk %d; Google Play has required %d for new apps and updates since %s. Prefer '
                         'targetSdk = flutter.targetSdkVersion, which the Flutter tool keeps current.'
                         % (v, PLAY_MIN_TARGET_SDK, PLAY_MIN_TARGET_SDK_SINCE))
        # REL-001
        for _s, bo, bc in g.blocks(r'\bbuildTypes'):
            for rs, ro, rc in g.blocks(r'(?:(?<![\w.])release|getByName\(\s*"release"\s*\)|named\(\s*"release"\s*\))',
                                       bo + 1, bc):
                for mm in re.finditer(r'signingConfigs\s*(?:\.\s*debug\b|\.\s*getByName\(\s*["\']debug["\']\s*\)|'
                                      r'\[\s*["\']debug["\']\s*\]|\.\s*named\(\s*["\']debug["\']\s*\))',
                                      g.code[ro + 1:rc]):
                    pos = ro + 1 + mm.start()
                    ln = g.line_of(pos)
                    text = g.lines[ln - 1]
                    if 'signingConfig' not in text.replace('signingConfigs', ''):
                        continue
                    encl = g.enclosing_opens(pos)
                    conditional = bool(re.search(r'\?|\bif\b|\belse\b', text))
                    for o in encl:
                        if o == ro:
                            break
                        if re.search(r'\bif\b|\belse\b', g.header(o)):
                            conditional = True
                    if conditional:
                        self.add(g, 'REL-001', ln, g.line_text(ln),
                                 'falls back to the debug key when the release keystore is missing. Prefer failing '
                                 'the release build (throw GradleException("key.properties missing")) so a '
                                 'debug-signed release cannot be produced and shipped by accident.', severity='info')
                    else:
                        self.add(g, 'REL-001', ln, g.line_text(ln),
                                 'Create an upload keystore (keytool -genkey ... -alias upload), keep it and '
                                 'key.properties outside git, load them into signingConfigs.release (CI: decode the '
                                 'keystore from a secret into $RUNNER_TEMP), and enrol in Play App Signing so a lost '
                                 'upload key can be reset.')

    def rel_signing(self):
        # files on disk
        for rel in self.walk(''):
            base = os.path.basename(rel)
            if not SIGNING_FILE_RE.search(base) or base.lower() == 'debug.keystore':
                continue
            if self.gitignore.ignored(os.path.join(self.root, rel)):
                continue
            sf = self.src(rel, 'other')
            if not sf:
                continue
            self.add(sf, 'REL-002', 1, base,
                     '%s is not covered by any .gitignore, so `git add .` commits it. Add **/*.jks, **/*.keystore, '
                     'key.properties, *.p12, *.p8 and *.mobileprovision to .gitignore, remove it from history '
                     '(git rm --cached, then rewrite history if it was pushed), and rotate the key (Play: request an '
                     'upload key reset).' % rel)
        # .gitignore lacks the patterns although signing is configured
        g = self.app_gradle
        if g:
            mm = re.search(r'key\.properties', g.code)
            if mm:
                probes = ['android/key.properties', 'android/app/upload-keystore.jks']
                missing = [p for p in probes if not self.gitignore.ignored(os.path.join(self.root, p))]
                if missing:
                    ln = g.line_of(mm.start())
                    self.add(g, 'REL-002', ln, g.line_text(ln),
                             'signing reads key.properties, but no .gitignore covers %s. Add key.properties, '
                             '**/*.jks and **/*.keystore to android/.gitignore (flutter create adds them) before '
                             'anyone copies the keystore in.' % ', '.join(missing), severity='low')

    # -- iOS
    def read_ios(self):
        rel = 'ios/Runner.xcodeproj/project.pbxproj'
        self.pbx = self.src(rel, 'pbxproj') if self.exists(rel) else None
        targets = set()
        if self.pbx:
            for mm in re.finditer(r'isa\s*=\s*PBXNativeTarget\s*;', self.pbx.code):
                encl = self.pbx.enclosing_opens(mm.start())
                if encl:
                    o = encl[0]
                    nm = re.search(r'\bname\s*=\s*"?([^";]+)"?\s*;', self.pbx.code[o:self.pbx.braces[o]])
                    if nm:
                        targets.add(nm.group(1).strip().lower())
        sdir = os.path.join(self.root, 'ios', 'Runner.xcodeproj', 'xcshareddata', 'xcschemes')
        if os.path.isdir(sdir):
            for f in sorted(os.listdir(sdir)):
                if not f.endswith('.xcscheme'):
                    continue
                name = f[:-len('.xcscheme')]
                low = name.lower()
                if low.startswith('runner') or low in targets or low.endswith('tests'):
                    continue
                self.ios_flavors.setdefault(low, ('ios/Runner.xcodeproj/xcshareddata/xcschemes/' + f, 1))
        elif self.pbx:
            for mm in re.finditer(r'\bname\s*=\s*"?(?:Debug|Release|Profile)-([A-Za-z0-9_]+)"?\s*;', self.pbx.code):
                self.ios_flavors.setdefault(mm.group(1).lower(), (self.pbx.rel, self.pbx.line_of(mm.start())))

    def ios_bundle_ids(self):
        """[(value, SrcFile, line)] for the Runner app target."""
        out = []
        p = self.pbx
        if not p:
            return out
        xc = {}
        for rel in self.walk('ios', 4):
            if rel.endswith('.xcconfig'):
                sf = self.src(rel, 'other')
                if sf:
                    for ln, t in enumerate(sf.lines, 1):
                        mm = re.match(r'^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(\S+)', t)
                        if mm:
                            xc.setdefault(mm.group(1), (mm.group(2), sf, ln))
        for mm in re.finditer(r'buildSettings\s*=\s*\{', p.code):
            o = mm.end() - 1
            c = p.braces.get(o)
            if c is None:
                continue
            body = p.code[o:c]
            bm = re.search(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*"?([^";]+)"?\s*;', body)
            if not bm:
                continue
            info = re.search(r'INFOPLIST_FILE\s*=\s*"?([^";]+)"?\s*;', body)
            val = bm.group(1).strip()
            if (info and 'Runner/Info.plist' not in info.group(1)) or re.search(r'Tests$', val):
                continue
            ref = re.match(r'^\$[({](\w+)[)}]', val)
            if ref and ref.group(1) in xc:
                v2, sf, ln = xc[ref.group(1)]
                out.append((v2, sf, ln))
            else:
                out.append((val, p, p.line_of(o + bm.start())))
        return out

    def rel_ios_store(self):
        for val, sf, ln in self.ios_bundle_ids():
            if val == 'com.example' or val.startswith('com.example.'):
                self.add(sf, 'REL-003', ln, sf.line_text(ln),
                         'iOS bundle identifier %s. Register your own id (com.yourcompany.app) in the Apple Developer '
                         'portal and set it in Xcode (Runner target, Signing & Capabilities) for every build '
                         'configuration.' % val)
                return

    # -- intent
    def compute_intent(self):
        sig = []
        if self.app_gradle:
            appid, _ = self.gradle_value('applicationId')
            if appid and not appid.startswith('com.example'):
                sig.append('applicationId %s' % appid)
            if self.app_gradle.blocks(r'\bsigningConfigs') and re.search(
                    r'(?<![\w.])release\s*\{|create\(\s*"release"\s*\)|register\(\s*"release"\s*\)',
                    self.app_gradle.code):
                sig.append('release signingConfig')
        ids = [v for v, _, _ in self.ios_bundle_ids()]
        if ids and not any(v.startswith('com.example') for v in ids) and not any(s.startswith('applicationId') for s in sig):
            sig.append('bundle id %s' % ids[0])
        if self.android_flavors or self.ios_flavors:
            sig.append('flavors')
        if self.fastlane:
            sig.append('fastlane')
        for rel in self.ci_files:
            sf = self.src(rel, 'yaml')
            if not sf:
                continue
            if os.path.basename(rel).startswith('codemagic'):
                sig.append('codemagic')
            else:
                code = '\n'.join(_strip_yaml_comment(l) for l in sf.lines)
                if RELEASE_CI_RE.search(code):
                    sig.append('release workflow %s' % os.path.basename(rel))
        self.intent = sig
        relp = os.path.relpath(self.root, self.git_root) if self.git_root else \
            os.sep.join(self.root.split(os.sep)[-2:])
        segs = [s.lower() for s in relp.replace(os.sep, '/').split('/')]
        in_examples = any(s in EXAMPLE_SEGS for s in segs)
        strong = [s for s in sig if not s.startswith(('applicationId', 'bundle id'))]
        if in_examples:
            self.sample, self.sample_reason = True, 'inside an examples/samples folder'
        elif not sig:
            self.sample, self.sample_reason = True, 'no release intent'
        elif not strong:
            self.sample, self.sample_reason = True, 'no store metadata: no release signing config, flavors, ' \
                                                    'fastlane, codemagic or release workflow'
        else:
            self.sample, self.sample_reason = False, ''

    # -- flavors
    def rel_flavors(self):
        A, I = self.android_flavors, self.ios_flavors
        if A and self.has_ios and self.pbx:
            for name in sorted(A):
                if name not in I:
                    g, ln = A[name]
                    self.add(g, 'REL-004', ln, g.line_text(ln),
                             'Android flavor "%s" has no iOS scheme (iOS flavors: %s), so `flutter run --flavor %s` '
                             'fails on iOS. Duplicate the Runner scheme as "%s" with Debug-%s/Release-%s/Profile-%s '
                             'build configurations (docs.flutter.dev flavors guide).'
                             % (name, ', '.join(sorted(I)) or 'none', name, name, name, name, name))
        if I and self.app_gradle:
            for name in sorted(I):
                if name not in A:
                    rel, ln = I[name]
                    sf = self.src(rel, 'other')
                    if sf:
                        self.add(sf, 'REL-004', ln, os.path.basename(rel),
                                 'iOS flavor "%s" has no Android productFlavor (Android flavors: %s), so '
                                 '`flutter run --flavor %s` fails on Android. Add it under productFlavors with the '
                                 'same name.' % (name, ', '.join(sorted(A)) or 'none', name))
        known = set(alias(x) for x in list(A) + list(I))
        if known:
            for name, rel in sorted(self.entrypoints.items()):
                if alias(name) not in known:
                    df = self.src(rel, 'dart')
                    if df:
                        self.add(df, 'REL-004', 1, os.path.basename(rel),
                                 'entrypoint main_%s.dart matches no flavor (%s). Rename it to the flavor it serves, '
                                 'or delete it if no build uses it.' % (name, ', '.join(sorted(set(A) | set(I)))),
                                 severity='low')

    # -- Info.plist
    def rel_usage_descriptions(self):
        plist = os.path.join(self.root, 'ios', 'Runner', 'Info.plist')
        if not os.path.isfile(plist):
            return
        keys = set()
        try:
            with open(plist, 'rb') as fh:
                data = plistlib.load(fh)
            if isinstance(data, dict):
                keys = set(data)
        except Exception:  # noqa: BLE001 - fall back to a text scan
            with open(plist, encoding='utf-8', errors='replace') as fh:
                keys = set(re.findall(r'<key>\s*([^<\s]+)\s*</key>', fh.read()))
        pub = self.src('pubspec.yaml', 'yaml')
        section = None
        for ln, line in enumerate(pub.lines, 1):
            if re.match(r'^\S', line):
                section = line.split(':')[0].strip()
                continue
            mm = re.match(r'^  ([A-Za-z_]\w*)\s*:', line)
            if not mm or section != 'dependencies' or mm.group(1) not in USAGE_KEYS:
                continue
            missing = [alt.split('|')[0] for alt in USAGE_KEYS[mm.group(1)]
                       if not any(k in keys for k in alt.split('|'))]
            if missing:
                self.add(pub, 'REL-009', ln, pub.line_text(ln),
                         '%s needs %s in ios/Runner/Info.plist. Add a sentence saying why the app asks '
                         '(localise it in InfoPlist.strings); never leave it empty.'
                         % (mm.group(1), ' and '.join(missing)))

    # -- Dart rules
    @staticmethod
    def envish(text):
        t = text.strip()
        t = re.sub(r'^\(+|\)+$', '', t).strip()
        if not t or t in ("''", '""', 'null') or re.match(r'''^r?(['"])\1$''', t):
            return False
        if URL_LIT_RE.match(t):
            return True
        if re.match(r'''^r?['"]''', t):
            return bool(re.match(r'''^r?['"](prod|production|staging|stage|dev|development|sandbox|live|qa)['"]$''', t, re.I))
        idents = re.findall(r'[A-Za-z_]\w*', t)
        if not idents:
            return False
        if URLISH_NAME_RE.search(idents[-1]) or any(URLISH_NAME_RE.search(x) for x in idents[-2:]):
            return True
        return any(re.match(r'(?i)^(prod|production|staging|stage|dev|development|sandbox|live|qa)$', x)
                   or re.match(r'^(prod|staging|dev|development|production|sandbox)[A-Z]', x) for x in idents)

    def rel_build_mode(self, df):
        m, code = df.masked, df.code
        seen = set()
        for mm in BUILD_MODE_RE.finditer(code):
            p = mm.start()
            if m[p] == ' ':
                continue      # inside a string
            # ternary after the token
            i, depth, q = mm.end(), 0, None
            while i < len(m):
                c = m[i]
                if c in '([{':
                    depth += 1
                elif c in ')]}':
                    if depth == 0:
                        break
                    depth -= 1
                elif c in ';,' and depth == 0:
                    break
                elif c == '?' and depth == 0 and m[i + 1:i + 2] not in ('.', '?', '[') and m[i - 1] != '?':
                    q = i
                    break
                i += 1
            ln = df.line_of(p)
            if q is not None:
                j, depth, nest = q + 1, 0, 0
                colon = None
                while j < len(m):
                    c = m[j]
                    if c in '([{':
                        depth += 1
                    elif c in ')]}':
                        if depth == 0:
                            break
                        depth -= 1
                    elif depth == 0 and c == '?' and m[j + 1:j + 2] not in ('.', '?', '['):
                        nest += 1
                    elif depth == 0 and c == ':':
                        if nest == 0:
                            colon = j
                            break
                        nest -= 1
                    elif depth == 0 and c in ';,':
                        break
                    j += 1
                if colon is None:
                    continue
                end = expr_end(m, colon + 1)
                a, b = code[q + 1:colon], code[colon + 1:end]
                if self.envish(a) and self.envish(b) and ln not in seen:
                    seen.add(ln)
                    self.add(df, 'REL-005', ln, df.line_text(ln),
                             'picks %s / %s by build mode.' % (' '.join(a.split())[:40], ' '.join(b.split())[:40]),
                             env_place=True)
                continue
            # if (kReleaseMode) { url = ... }
            encl_paren = None
            for o, c in df.parens.items():
                if o < p < c and (encl_paren is None or o > encl_paren):
                    encl_paren = o
            if encl_paren is None or not re.search(r'\bif\s*$', code[max(0, encl_paren - 6):encl_paren]):
                continue
            close = df.parens[encl_paren]
            k = close + 1
            while k < len(m) and m[k].isspace():
                k += 1
            if k < len(m) and m[k] == '{' and k in df.braces:
                body = code[k:df.braces[k]]
            else:
                body = code[k:expr_end(m, k) + 1]
            if re.search(r'\b\w*(?i:url|uri|host|endpoint|server|domain)\w*\s*=(?!=)\s*\S|'
                         r'''=\s*r?['"](?:https?|wss?)://|return\s+r?['"](?:https?|wss?)://''', body) and ln not in seen:
                seen.add(ln)
                self.add(df, 'REL-005', ln, df.line_text(ln), 'sets the endpoint inside a build-mode branch.',
                         env_place=True)

    def rel_flavor_reads(self, df):
        rel = df.rel
        segs = rel.split('/')
        base = segs[-1]
        if re.match(r'^lib/main[^/]*\.dart$', rel) or (len(segs) > 2 and segs[1] in ('app', 'di', 'injection', 'bootstrap')):
            return
        if any(s in ('config', 'configs', 'env', 'environment', 'environments', 'flavor', 'flavors', 'di',
                     'injection') for s in segs[1:-1]):
            return
        if re.match(r'^(flavors?|env|environment|app_config|config|app_env|bootstrap|injection|locator|'
                    r'service_locator|di)\.dart$', base) or 'main' in base:
            return
        if df.role in ('di', 'app', 'barrel') or df.layer in ('app', 'core', 'other'):
            return
        if df.layer == 'data' and df.role not in ('source', 'repository-impl', 'repository', 'service'):
            return
        for mm in FLAVOR_READ_RE.finditer(df.code):
            ln = df.line_of(mm.start())
            if re.search(r'\b(final|const|static|var)\s+[\w<>?]*\s*' + re.escape(mm.group(0)) + r'\s*[=;]', df.code[
                    df.line_starts[ln - 1]:df.line_starts[ln] if ln < len(df.line_starts) else len(df.code)]):
                continue
            self.add(df, 'REL-006', ln, df.line_text(ln),
                     '%s (%s %s) reads `%s`. Inject the value it needs (a base URL, a feature flag) from the '
                     'composition root instead. %s' % (rel, df.layer, df.role, mm.group(0), ARCH_CITE), env_place=True)
            return

    def rel_debug_switches(self, df):
        for rx, sev, what in DEBUG_SWITCHES:
            for mm in rx.finditer(df.code):
                if df.masked[mm.start()] == ' ':
                    continue
                guarded = False
                for o in df.enclosing_opens(mm.start()):
                    h = df.header(o)
                    if re.search(r'\bkDebugMode\b|\bassert\s*\(', h):
                        guarded = True
                        break
                if guarded:
                    continue
                ln = df.line_of(mm.start())
                self.add(df, 'REL-007', ln, df.line_text(ln),
                         '%s: %s. Delete it, or drive it from a dev-only setting guarded by kDebugMode '
                         '(showPerformanceOverlay: kDebugMode && devSettings.showPerf).' % (mm.group(1) if mm.groups() else
                                                                  mm.group(0).split(':')[0].strip(), what),
                         severity=sev)

    # -- CI
    def check_workflow(self, sf):
        try:
            tree = parse_yaml(sf.raw)
        except Exception:  # noqa: BLE001 - unparseable YAML is not our finding
            return
        on = yget(tree, 'on') or yget(tree, 'true')
        triggers = set(yflow_list(on))
        wf_env = dict((k, ystr(v)) for k, v, _ in yitems(yget(tree, 'env')))
        for job_id, job, jln in yitems(yget(tree, 'jobs')):
            job_env = dict(wf_env)
            job_env.update((k, ystr(v)) for k, v, _ in yitems(yget(job, 'env')))
            runs_on = ystr(yget(job, 'runs-on')).strip()
            labels = yflow_list(yget(job, 'runs-on'))
            if yget(job, 'runs-on') and yget(job, 'runs-on')['t'] == 'map':
                labels = yflow_list(yget(yget(job, 'runs-on'), 'labels')) or [runs_on]
            persistent = bool(labels) and (any(l == 'self-hosted' for l in labels) or
                                            not any(HOSTED_RUNNER_RE.match(l) for l in labels))
            wd_default = ystr(yget(yget(yget(job, 'defaults'), 'run'), 'working-directory')).strip()
            steps = yseq(yget(job, 'steps'))
            pr_checkout = None
            keys = []          # (ws_path, line, step index)
            removed = []
            for si, step in enumerate(steps):
                uses = ystr(yget(step, 'uses')).strip()
                with_ = yget(step, 'with')
                run = yget(step, 'run')
                env = dict(job_env)
                env.update((k, ystr(v)) for k, v, _ in yitems(yget(step, 'env')))
                secret_env = [k for k, v in env.items() if 'secrets.' in v]
                wd = ystr(yget(step, 'working-directory')).strip() or wd_default
                # REL-010
                if 'pull_request_target' in triggers:
                    ref = yget(with_, 'ref')
                    if uses.startswith('actions/checkout') and ref and re.search(
                            r'github\.event\.pull_request\.head|github\.head_ref|refs/pull/|pull_request\.number|'
                            r'github\.event\.number', ystr(ref)):
                        pr_checkout = ref['ln']
                    elif run and re.search(r'\bgh\s+pr\s+checkout\b', ystr(run)):
                        pr_checkout = run['ln']
                    elif pr_checkout and (run or uses.startswith('./')):
                        has_secrets = 'secrets.' in ystr(job) or 'secrets.' in ystr(yget(tree, 'env'))
                        self.add(sf, 'REL-010', pr_checkout, sf.line_text(pr_checkout),
                                 'job "%s" checks out the PR head and then runs %s (line %d)%s. Move the build to '
                                 'an on: pull_request workflow (no secrets, read-only token); if a privileged step '
                                 'must follow, pass results as artifacts to a separate workflow_run job that never '
                                 'executes PR code.' % (job_id, 'a script' if run else 'a local action',
                                                         (run or step)['ln'],
                                                         ', with secrets referenced in the job' if has_secrets else
                                                         ', with a write GITHUB_TOKEN'))
                        pr_checkout = None
                # REL-011 and REL-012
                for ln, text in ylines(run):
                    t = text.strip()
                    if t.startswith('#'):
                        continue
                    self.ci_print(sf, ln, text, secret_env)
                    kp = materialised_key(text)
                    if kp:
                        wp = ws_path(kp, wd)
                        if wp:
                            keys.append((wp, ln, si))
                    if re.search(r'\b(rm|shred|Remove-Item|del)\b', text):
                        removed.append((si, text))
                if uses.startswith('actions/upload-artifact'):
                    pnode = yget(with_, 'path')
                    plines = ylines(pnode) or []
                    for wp, kln, ksi in keys:
                        if ksi >= si:
                            continue
                        hit = None
                        for pln, ptxt in plines:
                            for part in ptxt.split():
                                if path_covers(part, wp):
                                    hit = (pln, part)
                                    break
                            if hit:
                                break
                        if hit:
                            self.add(sf, 'REL-012', hit[0], sf.line_text(hit[0]),
                                     'uploads %s, which includes the signing file %s written at line %d. '
                                     'Upload only build outputs (build/app/outputs/bundle/release/*.aab, '
                                     'the .ipa) and decode keys into $RUNNER_TEMP.' % (hit[1], wp, kln))
            if persistent:
                for wp, kln, ksi in keys:
                    bn = os.path.basename(wp)
                    if any(si > ksi and bn in t for si, t in removed):
                        continue
                    self.add(sf, 'REL-012', kln, sf.line_text(kln),
                             'job "%s" runs on "%s", which is not a GitHub-hosted image; if it is a persistent '
                             'self-hosted runner, %s stays on its disk after the job. Decode it into $RUNNER_TEMP '
                             'and delete it in a final `if: always()` step.' % (job_id, runs_on, wp),
                             severity='low')

    def ci_print(self, sf, ln, text, env_names):
        if '::add-mask::' in text:
            return
        text = text.strip()
        if text.startswith('- '):
            text = text[2:].lstrip()
        if text.startswith('run:'):
            text = text[4:].lstrip()
        for mm in PRINT_CMD_RE.finditer(text):
            seg, to_log = print_segment(text, mm.start(1))
            if not to_log:
                continue
            refs = secret_refs(seg, env_names)
            if refs:
                self.add(sf, 'REL-011', ln, sf.line_text(ln),
                         'prints %s to the log. GitHub/Codemagic mask exact values only: a multi-line secret (a '
                         'JSON key, a PEM), a base64 or partial copy is shown in clear. Pipe it to a file or a '
                         'command instead (`echo "$KEY" | base64 -d > "$RUNNER_TEMP/upload.jks"`).'
                         % ', '.join(sorted(set(refs))))
                return

    def check_codemagic(self, sf):
        try:
            tree = parse_yaml(sf.raw)
        except Exception:  # noqa: BLE001
            return
        for wname, wf, wln in yitems(yget(tree, 'workflows')):
            wd = ystr(yget(wf, 'working_directory')).strip()
            keys = []
            env_vars = [k for k, _, _ in yitems(yget(yget(wf, 'environment'), 'vars'))]
            names = set(n for n in env_vars if STRONG_SECRET_NAME_RE.search(n))
            for script in yseq(yget(wf, 'scripts')):
                node = yget(script, 'script') if script['t'] == 'map' else script
                for ln, text in ylines(node):
                    if text.strip().startswith('#'):
                        continue
                    refs = set(re.findall(r'\$\{?([A-Z][A-Z0-9_]*)\}?', text))
                    self.ci_print(sf, ln, text, sorted(names | set(r for r in refs if STRONG_SECRET_NAME_RE.search(r))))
                    kp = materialised_key(text)
                    if kp:
                        wp = ws_path(kp, wd)
                        if wp:
                            keys.append((wp, ln))
            for art in yseq(yget(wf, 'artifacts')):
                for pln, ptxt in ylines(art):
                    for wp, kln in keys:
                        if path_covers(ptxt, wp):
                            self.add(sf, 'REL-012', pln, sf.line_text(pln),
                                     'artifact pattern %s includes the signing file %s written at line %d. Keep '
                                     'artifacts to build outputs and use Codemagic code signing identities or '
                                     '$CM_TEMP-style paths outside the build dir.' % (ptxt.strip(), wp, kln))


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
        return 'app', 'di'
    if len(segs) > 2 and segs[1] in ('app', 'bootstrap'):
        return 'app', 'other'
    if any(s in ('core', 'config', 'utils', 'common', 'shared') for s in segs[1:-1]):
        return 'core', 'other'
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
    if any(s in ('sources', 'datasources', 'data_sources', 'remote', 'api', 'services') for s in segs) or \
            re.search(r'_(source|api|client|service)\.dart$', base):
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
        p = os.path.relpath(it, root) if os.path.isabs(it) else it
        p = os.path.normpath(p).replace(os.sep, '/')
        out.add(p[2:] if p.startswith('./') else p)
    return out


def usage(msg):
    sys.stderr.write('check_release.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_release.py <project-root> [--json] [--files <list>] '
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
    deps = pubspec_deps(pubspec)

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

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(deps, rels), 'fallback detection from pubspec and folders'
    clean = bool(arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('clean_architecture'))
    di = set((arch.get('profile') or {}).get('di') or []) if arch else set()
    if not arch and 'get_it' in deps:
        di.add('get_it')

    ck = Checker(root, package, pubspec, [], profile, clean, di)
    skipped = {'generated': 0, 'barrel': 0}
    for rel in rels:
        if use_arch and rel not in arch_files:
            skipped['generated'] += 1      # arch_check decides what is generated (CONTRACTS §18)
            continue
        df = ck.src(rel, 'dart')
        if df is None:
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
        ck.files.append(df)

    stats = {'files': len(ck.files)}
    if rels:
        ck.run()
        stats.update(ck.stats)
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))
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

    if rels:
        plat = [p for p in ('android', 'ios') if stats['platforms'][p]]
        fl = stats['flavors']
        flv = sorted(set(fl['android']) | set(fl['ios']))
        kind = stats['app_kind']
        if kind == 'package':
            kind_txt = stats['platform_rules']
        elif kind == 'sample':
            kind_txt = 'sample app (%s): store-readiness rules graded info' % ck.sample_reason
        else:
            kind_txt = 'release intent: %s' % ', '.join(stats['release_intent'])
        scanned = '%d Dart files; platforms: %s; %d CI files; flavors: %s; %s' % (
            len(ck.files), ', '.join(plat) or 'none', len(stats['ci_files']), ', '.join(flv) or 'none', kind_txt)
    else:
        scanned = '0 Dart files (no lib/)'
    out = ['== RELEASE',
           '  profile: %s%s (%s)' % (profile, ' + clean' if clean else '', psource),
           '  classification: %s' % classification,
           '  scanned: %s' % scanned]
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no release findings')
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
