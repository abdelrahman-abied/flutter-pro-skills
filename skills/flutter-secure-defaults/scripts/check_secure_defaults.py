#!/usr/bin/env python3
"""check_secure_defaults.py: find code that is not secure by default in a Flutter/Dart project (read-only).

Usage:
  python3 -I check_secure_defaults.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed; only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Scope: code-level write-time defaults (where tokens live, auth headers, cleartext URLs, logging,
TLS callbacks, WebView navigation guards, secrets in source and build config, release flags).
Deep hardening (pinning, RASP, manifests, plists, attestation, screen protection) is the
separate flutter-security-audit skill and its scan.sh; this checker does not repeat those checks.

Secret values are never printed: a detected secret is shown masked, e.g. AIza…(39 chars).

Layers and roles come from ../flutter-architecture/scripts/arch_check.py --json ("files" array)
when that sibling skill is installed; otherwise a path-based fallback is used and the output says so.

Suppression (in the analysed code or config):
  // sec-ignore: SEC-001 <reason>        on the reported line or the line above (`#` works in YAML/shell)
  // sec-ignore-file: SEC-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import base64
import bisect
import json
import math
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/flutter-secure-defaults@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
AUDIT_URL = 'https://github.com/abdelrahman-abied/flutter-security-audit'

RULES = {
    'SEC-001': ('token-in-plain-storage', 'high',
                "A token, password or secret is written to SharedPreferences, GetStorage or an unencrypted Hive box. "
                "Those are plain files on disk (and in backups). Use flutter_secure_storage behind a data-layer source."),
    'SEC-002': ('auth-header-outside-data-layer', 'medium',
                "An Authorization/API-key header is built in a widget, logic, state or domain file. Inject it in the "
                "HTTP client with an interceptor in the data layer, so the token never passes through UI code."),
    'SEC-003': ('cleartext-http-url', 'medium',
                "A non-local http:// URL in Dart code. Requests and tokens travel in clear text and can be read or "
                "changed on the network. Use https:// (localhost, emulator and LAN addresses are not reported)."),
    'SEC-004': ('secret-in-log', 'medium',
                "A token, password, secret or Authorization value is passed to print/debugPrint/a logger, or to an "
                "analytics or crash-reporting call. Logs and analytics leave the device; log a redacted marker instead."),
    'SEC-005': ('http-logger-in-release', 'medium',
                "An HTTP logging interceptor is installed without a debug-only guard. Dio's LogInterceptor logs request "
                "headers (Authorization) by default; body loggers print login responses. Add it only in kDebugMode."),
    'SEC-006': ('accept-any-certificate', 'high',
                "A TLS certificate callback returns true, so any certificate (any proxy, any attacker on the network) "
                "is accepted and HTTPS gives no protection. Remove it; fix the server's certificate or pin keys."),
    'SEC-007': ('webview-js-without-navigation-guard', 'medium',
                "A WebView runs JavaScript with no navigation guard (no onNavigationRequest / shouldOverrideUrlLoading "
                "allow-list), so any page it reaches runs script inside the app. Turn JS off or restrict navigation."),
    'SEC-008': ('hardcoded-secret', 'high',
                "A credential is hard-coded in Dart source. Every string ships in the binary and is recoverable even "
                "with --obfuscate. Move the secret to your backend; keep only public, restricted client keys."),
    'SEC-009': ('secret-in-build-config', 'low',
                "A secret-named value comes from --dart-define, a bundled .env file or envied. Build-time config is "
                "compiled into the app and is not secret; a bundled .env is a plain file inside the APK/IPA."),
    'SEC-010': ('token-in-global-or-ui-state', 'medium',
                "A token or password is held in a global/static field, a provider, or UI state. It outlives the need, "
                "shows up in observers, DevTools and toString(), and is easy to leak. Keep it in the data layer."),
    'SEC-011': ('body-logged-in-data-layer', 'low',
                "A data-layer source/repository logs a request or response body. Bodies carry tokens, credentials and "
                "personal data. Log the method, path, status and duration only."),
    'SEC-012': ('release-build-unobfuscated', 'low',
                "A release `flutter build` command in CI or a build script has no --obfuscate --split-debug-info. "
                "Obfuscation is friction, not secrecy, but it is the expected release default."),
}

# where the fix goes, per architecture (used in notes for placement rules)
PLACE = {
    'mvn': "MVN: keep the token in data/sources (FlutterSecureStorage), add the header in the Dio provider's interceptor in core/network; notifiers and views never see it.",
    'mvvm': "MVVM: keep the token in a service under data/services, let the AuthRepository own the session and give the ApiClient an auth-header callback; view models only see isAuthenticated.",
    'bloc': "Bloc: keep the token in a token-storage data provider used by AuthenticationRepository; the API client adds the header; AuthenticationBloc holds status and User, not the token.",
    'getx': "GetX: keep the token in an AuthService (GetxService) backed by secure storage; add the header in GetConnect's httpClient.addRequestModifier or a Dio interceptor; controllers never set headers.",
    'provider': "Provider: keep the token in an AuthService in the data layer; the ChangeNotifier exposes isSignedIn/User only; the HTTP client adds the header.",
    'riverpod': "Riverpod: a tokenStorageProvider (secure storage) and a dioProvider with an auth interceptor; UI providers expose the session state, never the raw token.",
    'mvc': "MVC: keep the token in the model/service layer and add the header in the HTTP client; controllers never set headers.",
    'setstate': "Keep the token in a small data-layer class (secure storage) and add the header in one shared HTTP client; widgets never set headers.",
    'unknown': "Keep the token in a data-layer source backed by secure storage and add the header in one shared HTTP client interceptor.",
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')

# --------------------------------------------------------------------------- lexing


def lex(text):
    """Return (code, masked, comments, strings): comments blanked; masked also blanks string contents."""
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
            strings.append((i, j, p + dl, max(p + dl, j - dl), text[i] in 'rR'))
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


SUPPRESS_RE = re.compile(r'sec-ignore(-file)?\s*:\s*((?:SEC-\d{3})(?:\s*,\s*SEC-\d{3})*)\s*(.*)')


class SourceFile(object):
    """A Dart file, or a text file (pubspec / CI) when dart=False."""

    def __init__(self, root, rel, dart=True):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.dart = dart
        if dart:
            self.code, self.masked, self.comments, self.strings = lex(self.raw)
        else:
            self.code = self.masked = self.raw
            self.comments, self.strings = [], []
        self.line_starts = [0] + [m.end() for m in re.finditer('\n', self.raw)]
        self.lines = self.raw.split('\n')
        self.layer, self.role, self.feature = 'other', 'other', None
        self.suppress_line, self.suppress_file = {}, {}
        for ln, text in enumerate(self.lines, 1):
            if 'sec-ignore' not in text:
                continue
            sm = SUPPRESS_RE.search(text)
            if not sm:
                continue
            ids = [x.strip() for x in sm.group(2).split(',')]
            reason = sm.group(3).strip().rstrip('*/').strip() or '(no reason given)'
            for i in ids:
                if sm.group(1):
                    self.suppress_file[i] = reason
                else:
                    self.suppress_line.setdefault(ln, {})[i] = reason
        if dart:
            self.parens = match_pairs(self.masked, '(', ')')
            self.braces = match_pairs(self.masked, '{', '}')
            self.brace_opens = sorted(k for k, v in self.braces.items() if self.masked[k] == '{')
            self.string_starts = [s[0] for s in self.strings]

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def line_text(self, ln):
        return self.lines[ln - 1].strip() if 0 < ln <= len(self.lines) else ''

    def enclosing_braces(self, pos):
        out = []
        k = bisect.bisect_left(self.brace_opens, pos) - 1
        while k >= 0:
            o = self.brace_opens[k]
            if self.braces.get(o, -1) > pos:
                out.append(o)
            k -= 1
        return out  # innermost first

    def depth(self, pos):
        return len(self.enclosing_braces(pos))

    def string_at(self, pos):
        k = bisect.bisect_right(self.string_starts, pos) - 1
        if k >= 0:
            s = self.strings[k]
            if s[0] <= pos < s[1]:
                return s
        return None


# --------------------------------------------------------------------------- classification (fallback)

def classify_fallback(rel):
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
        elif any(s in ('models', 'services', 'repositories', 'api', 'datasources', 'data_sources', 'sources', 'network') for s in dirs):
            layer = 'data'
        elif any(s in ('core', 'shared', 'common', 'utils') for s in dirs):
            layer = 'core'
    stem = base[:-5]
    role = 'other'
    if 'usecases' in dirs or 'use_cases' in dirs or stem.endswith(('_usecase', '_use_case')):
        role = 'usecase'
    elif 'entities' in dirs or stem.endswith('_entity'):
        role = 'entity'
    elif stem.endswith('_repository_impl') or ('repositories' in dirs and layer != 'domain') or (stem.endswith('_repository') and layer == 'data'):
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
                   'cubit', 'cubits', 'controller', 'controllers', 'providers', 'provider') for s in dirs) or \
            stem.endswith(('_notifier', '_view_model', '_viewmodel', '_bloc', '_cubit', '_controller', '_store', '_provider')):
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
                           r'ChangeNotifier|StateNotifier|GetxController|AsyncNotifier|Notifier|ValueNotifier)\b|\bwith\s+ChangeNotifier\b')
WIDGET_CONTENT = re.compile(r'\bextends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget|'
                            r'HookWidget|HookConsumerWidget|State<|ConsumerState<|GetView<|GetWidget<)')
DATA_CONTENT = re.compile(r'\bextends\s+(?:Interceptor|QueuedInterceptor|InterceptorsWrapper|GetConnect|GetxService|BaseClient)\b|'
                          r'\bimplements\s+(?:Interceptor|HttpClient)\b')


def refine_role(sf):
    m = sf.masked
    if sf.layer in ('other', 'core', 'app') and DATA_CONTENT.search(m):
        sf.role, sf.layer = 'service', 'data'
        return
    if sf.role in ('other', 'service', 'widget') and LOGIC_CONTENT.search(m) and sf.layer not in ('domain', 'data'):
        sf.role = 'logic'
    if sf.role == 'other' and WIDGET_CONTENT.search(m) and sf.layer not in ('data', 'domain'):
        sf.role = 'widget'
        if sf.layer in ('other',):
            sf.layer = 'presentation'


# --------------------------------------------------------------------------- names and secrets

NOT_TOKEN_QUAL = {'cancel', 'page', 'next', 'continuation', 'isolate', 'root', 'fcm', 'push', 'device', 'apns',
                  'sync', 'resume', 'notification', 'messaging', 'design', 'color', 'colour', 'theme', 'style',
                  'lexer', 'parse', 'parser', 'syntax', 'text', 'word', 'search', 'pagination', 'cursor', 'nonce',
                  'tokenizer', 'firebase', 'onesignal', 'expo', 'cache', 'etag', 'stream', 'subscription',
                  'binding', 'action', 'cancellation'}
SUFFIX_EXCL = {'key', 'keys', 'name', 'names', 'url', 'uri', 'endpoint', 'path', 'type', 'types', 'expiry', 'expires',
               'expiration', 'exp', 'at', 'in', 'time', 'date', 'timestamp', 'length', 'len', 'count', 'visible',
               'visibility', 'obscure', 'obscured', 'obscuring', 'hint', 'label', 'title', 'error', 'errors',
               'message', 'msg', 'focus', 'node', 'valid', 'validator', 'validation', 'strength', 'policy', 'field',
               'form', 'screen', 'page', 'view', 'route', 'widget', 'button', 'icon', 'changed', 'required',
               'header', 'prefix', 'regex', 'pattern', 'format', 'rule', 'rules', 'listener', 'stream', 'callback',
               'handler', 'manager', 'service', 'repository', 'repo', 'storage', 'store', 'interceptor', 'source',
               'client', 'helper', 'util', 'utils', 'dialog', 'sheet', 'status', 'mode', 'enabled', 'flag', 'id',
               'refresh', 'refreshed', 'refreshing', 'updated', 'saved', 'loaded', 'stored', 'exists', 'present',
               'missing', 'invalid', 'expired', 'notifier', 'controller', 'provider', 'bloc', 'cubit', 'event',
               'state', 'request', 'response', 'dto', 'model', 'entity', 'usecase', 'test', 'mock', 'fake', 'lock',
               'mutex', 'completer', 'future', 'timer', 'min', 'max', 'reset', 'set', 'policy', 'level', 'scope',
               'scopes', 'field', 'char', 'chars', 'input', 'box', 'option', 'options', 'config', 'setting',
               'settings', 'manager', 'kind', 'version', 'hash', 'digest', 'salt'}
PREFIX_EXCL = {'has', 'is', 'should', 'can', 'did', 'will', 'on', 'with', 'without', 'needs', 'need', 'show', 'hide',
               'toggle', 'forgot', 'reset', 'change', 'update', 'validate', 'verify', 'obscure', 'enter', 'clear',
               'delete', 'remove', 'save', 'store', 'persist', 'invalidate', 'revoke', 'num', 'max', 'min',
               'no', 'missing', 'invalid', 'expired', 'last', 'handle', 'set', 'request', 'requires', 'require',
               'use', 'uses', 'allow', 'enable', 'enabled', 'do', 'parse', 'decode', 'encode'}
SINGLE_SECRETS = {'token', 'tokens', 'password', 'passwd', 'passphrase', 'passcode', 'secret', 'secrets', 'jwt',
                  'bearer', 'credential', 'credentials', 'cookie', 'cookies', 'otp', 'cvv', 'ssn', 'authorization'}
PAIR_SECRETS = {('api', 'key'), ('apikey',), ('private', 'key'), ('secret', 'key'), ('access', 'key'),
                ('signing', 'key'), ('encryption', 'key'), ('client', 'secret'), ('session', 'id'), ('session', 'key'),
                ('card', 'number'), ('auth', 'code'), ('pin', 'code'), ('service', 'role'), ('master', 'key')}
WORD_RE = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+')


def words_of(name):
    out = []
    for part in re.split(r'[_\-.\s$:/]+', name):
        out += [w.lower() for w in WORD_RE.findall(part)]
    if len(out) > 1 and out[0] == 'k':
        out = out[1:]
    return out


def is_secret_name(name, mode='value'):
    """mode: value (an expression that holds the secret), storekey (a storage key name: trailing Key is fine),
    holder (a field or variable)."""
    w = words_of(name)
    if not w:
        return False
    if mode == 'storekey':
        while w and w[-1] in ('key', 'keys', 'pref', 'prefs', 'name'):
            if len(w) >= 2 and (w[-2], w[-1]) in PAIR_SECRETS:
                break
            w = w[:-1]
        while w and w[0] in ('pref', 'prefs', 'storage', 'key', 'keys', 'cache', 'box'):
            w = w[1:]
        if not w:
            return False
    if w[0] in PREFIX_EXCL and len(w) > 1:
        return False
    if any(x in NOT_TOKEN_QUAL for x in w) and not any(x in ('access', 'refresh', 'auth', 'bearer', 'jwt', 'id') for x in w):
        if 'token' in w or 'tokens' in w:
            return False
    last = w[-1]
    pair_last = len(w) >= 2 and (w[-2], w[-1]) in PAIR_SECRETS
    if last in SUFFIX_EXCL and not pair_last:
        return False
    for i, x in enumerate(w):
        if x in SINGLE_SECRETS:
            if x == 'authorization' and mode == 'holder':
                continue
            return True
        if i + 1 < len(w) and (x, w[i + 1]) in PAIR_SECRETS:
            return True
        if (x,) in PAIR_SECRETS:
            return True
    return False


VENDOR = [  # (regex, label, severity); the masked form keeps the vendor prefix (see vendor_prefix)
    (re.compile(r'AKIA[0-9A-Z]{16}'), 'AWS access key id', 'high'),
    (re.compile(r'(?:sk|rk)_live_[0-9a-zA-Z]{20,}'), 'Stripe live secret key', 'high'),
    (re.compile(r'sk_test_[0-9a-zA-Z]{20,}'), 'Stripe test secret key', 'medium'),
    (re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{40,}'), 'GitHub token', 'high'),
    (re.compile(r'xox[abposr]-[0-9A-Za-z-]{10,}'), 'Slack token', 'high'),
    (re.compile(r'sk-ant-[0-9A-Za-z_-]{20,}'), 'Anthropic API key', 'high'),
    (re.compile(r'sk-(?:proj-|svcacct-)?[0-9A-Za-z_-]{32,}'), 'OpenAI-style secret key', 'high'),
    (re.compile(r'GOCSPX-[0-9A-Za-z_-]{20,}'), 'Google OAuth client secret', 'high'),
    (re.compile(r'SG\.[0-9A-Za-z_-]{16,}\.[0-9A-Za-z_-]{16,}'), 'SendGrid API key', 'high'),
    (re.compile(r'SK[0-9a-f]{32}'), 'Twilio API key', 'high'),
    (re.compile(r'sk\.eyJ[0-9A-Za-z_-]{20,}'), 'Mapbox secret token', 'high'),
    (re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'), 'private key', 'high'),
    (re.compile(r'eyJ[0-9A-Za-z_-]{8,}\.eyJ[0-9A-Za-z_-]{8,}\.[0-9A-Za-z_-]{8,}'), 'JWT', 'high'),
    (re.compile(r'AIza[0-9A-Za-z_-]{35}'), 'Google API key', 'medium'),
    (re.compile(r'[Bb]earer\s+[0-9A-Za-z._~+/-]{20,}=*'), 'hard-coded bearer token', 'high'),
    (re.compile(r'[a-z][a-z0-9+.-]*://[^/\s:@\'"$]+:[^/\s:@\'"$]{3,}@'), 'credentials in a URL', 'high'),
]
PLACEHOLDER_RE = re.compile(r'your|xxx|changeme|change_me|example|placeholder|replace|dummy|sample|todo|fixme|<|>|\*\*\*|\.\.\.|'
                            r'^test|_test$|insert|secret_here|key_here|lorem', re.I)
IDENT_LIKE_RE = re.compile(r'^[A-Za-z][A-Za-z]*(?:[_.\-:/ ][A-Za-z]+)*$')


def entropy(s):
    if not s:
        return 0.0
    counts = {}
    for c in s:
        counts[c] = counts.get(c, 0) + 1
    return -sum(v / len(s) * math.log(v / len(s), 2) for v in counts.values())


def looks_like_credential(v):
    if len(v) < 8 or re.search(r'\s', v) or '$' in v or PLACEHOLDER_RE.search(v):
        return False
    if not re.match(r'^[\x21-\x7e]+$', v):
        return False  # prose in a non-Latin script, emoji: not a key
    if IDENT_LIKE_RE.match(v):
        return False  # a key name or a word ('access_token', 'Password', 'auth.token')
    if re.match(r'^[a-z]+://', v) or v.startswith('/') or re.match(r'^[\w.-]+\.(?:png|jpg|svg|json|dart|html|ttf)$', v):
        return False
    if re.match(r'^[\d.:-]+$', v) or re.match(r'^#?[0-9a-fA-F]{3,8}$', v):
        return False
    has_digit = bool(re.search(r'\d', v))
    has_alpha = bool(re.search(r'[A-Za-z]', v))
    e = entropy(v)
    return (has_digit and has_alpha and e >= 3.0) or (len(v) >= 20 and e >= 3.5)


def mask_value(v, prefix=None):
    n = len(v)
    k = len(prefix) if prefix else min(4, max(1, n // 4))
    k = min(k, max(1, n // 2))
    return '%s…(%d chars)' % (v[:k], n)


def vendor_prefix(v):
    m = re.match(r'(AKIA|AIza|sk_live_|rk_live_|sk_test_|gh[pousr]_|github_pat_|xox[abposr]-|sk-ant-|sk-|GOCSPX-|SG\.|SK|sk\.|eyJ|-----BEGIN|[Bb]earer )', v)
    return m.group(1) if m else None


def mask_text(text, extra=()):
    """Mask every secret-looking value in an evidence string."""
    for val in sorted(set(x for x in extra if x), key=len, reverse=True):
        if val in text:
            text = text.replace(val, mask_value(val, vendor_prefix(val)))
    for rx, _label, _sev in VENDOR:
        text = rx.sub(lambda m: mask_value(m.group(0), vendor_prefix(m.group(0))) if '…(' not in m.group(0) else m.group(0), text)

    def lit(m):
        q, v = m.group(1), m.group(2)
        if '…(' in v:
            return m.group(0)
        before = text[max(0, m.start() - 40):m.start()]
        nm = re.search(r'([A-Za-z_$][\w$]*)[\'"]?\s*[:=]\s*$', before)
        if (nm and is_secret_name(nm.group(1), 'holder') and looks_like_credential(v)) or \
                (len(v) >= 16 and looks_like_credential(v) and entropy(v) >= 3.5):
            return q + mask_value(v) + q
        return m.group(0)
    return re.sub(r'([\'"])([^\'"\n]{6,})\1', lit, text)


# --------------------------------------------------------------------------- helpers

DEBUG_GUARD = re.compile(r'\bkDebugMode\b|!\s*kReleaseMode\b|\bkProfileMode\b|\bassert\s*\(|\bisDebug\w*|\bdebugMode\b|'
                         r'\bisDev\w*|\bdevMode\b|\benableLog\w*|\blogEnabled\b|\bshowLogs\b|\bFlavor\.dev\b|'
                         r'\bflavor\s*==|!\s*\w*[iI]sProd\w*|!\s*\w*[iI]sRelease\w*|\bkIsDebug\w*|\bisInDebugMode\b|'
                         r'\b\w*[dD]ebug(?:Enabled|Logging|Logs)\b|\bif\s*\(\s*!?\s*\w*(?:[eE]nv|[cC]onfig)\w*\s*\.\s*\w*(?:[dD]ebug|[dD]ev|[lL]og)\w*')


def debug_guarded(sf, pos):
    """True if pos sits in an if/assert block (or a braceless if/ternary) guarded by a debug flag."""
    ln = sf.line_of(pos)
    line_start = sf.line_starts[ln - 1]
    head = sf.masked[max(0, line_start - 200):pos]
    # braceless `if (kDebugMode) print(...)` or `kDebugMode ? X : null` on this statement
    stmt = re.split(r'[;{}]', head)[-1]
    if DEBUG_GUARD.search(stmt):
        return True
    for o in sf.enclosing_braces(pos)[:4]:
        hdr = sf.masked[max(0, o - 200):o]
        hdr = re.split(r'[;}]', hdr)[-1]
        if DEBUG_GUARD.search(hdr):
            return True
        if re.search(r'\bassert\s*\(\s*\(\s*\)\s*$', hdr):
            return True
    return False


def call_args(sf, open_paren):
    close = sf.parens.get(open_paren)
    if close is None:
        return None, None
    return sf.code[open_paren + 1:close], close


def split_top(sf, start, end):
    """Split code[start:end] at top-level commas (using masked for nesting)."""
    parts, depth, last = [], 0, start
    for i in range(start, end):
        c = sf.masked[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append((last, i))
            last = i + 1
    if sf.code[last:end].strip():
        parts.append((last, end))
    return parts


def expr_identifiers(sf, start, end):
    """Identifier chains in code[start:end] outside string text, plus those inside ${...}/$x interpolations,
    plus string subscripts like ['access_token']."""
    seg_m = sf.masked[start:end]
    seg_c = sf.code[start:end]
    chains = [m.group(0) + ('[' if m.group(1) else '') for m in
              re.finditer(r'[A-Za-z_$][\w$]*(?:\s*[?!]?\.\s*[A-Za-z_$][\w$]*)*(?=\s*(\[)?)', seg_m)
              if not re.match(r'\$', m.group(0))]
    interp, keys = [], []
    for s in sf.strings:
        if s[0] < start or s[1] > end:
            continue
        content = sf.raw[s[2]:s[3]]
        if not s[4]:
            interp += re.findall(r'\$\{([^}]*)\}', content)
            interp += re.findall(r'\$([A-Za-z_]\w*)', content)
    for m in re.finditer(r'\[\s*[\'"]([^\'"]+)[\'"]\s*\]', seg_c):
        keys.append(m.group(1))
    for t in interp:
        if re.search(r'[!=]=|\bis!?\s|[<>]=?|\?\?', t):
            continue  # a comparison or a null check prints a bool, not the value
        chains += [m.group(0) + ('[' if m.group(1) else '') for m in
                   re.finditer(r'[A-Za-z_][\w]*(?:\s*[?!]?\.\s*[A-Za-z_][\w]*)*(?=\s*(\[)?)', t)]
        keys += re.findall(r'\[\s*[\'"]([^\'"]+)[\'"]\s*\]', t)
    return chains, keys


NON_VALUE_PROPS = {'isEmpty', 'isNotEmpty', 'length', 'hashCode', 'runtimeType', 'isExpired', 'isValid', 'expiresAt',
                   'expiry', 'expiresIn', 'expiration', 'exp', 'type', 'tokenType', 'scopes', 'scope', 'issuedAt'}
FORM_SEGS = {'form', 'formstate', 'formkey', 'fields', 'field', 'currentstate', 'formdata', 'formvalues', 'formvalue',
             'fieldvalue', 'input', 'inputs'}


def secret_in_chains(chains, keys, mode='value', skip=()):
    """First chain that holds a secret. Form-field values are left to flutter-forms FORM-004:
    controller.text, field-callback parameters (passed in `skip`), and form-state values (formz `password.value`)."""
    for ch in chains:
        subscripted = ch.endswith('[')
        ch = ch.rstrip('[')
        segs = [x.strip(' ?!') for x in re.split(r'\.', ch)]
        segs = [x for x in segs if x]
        if segs and (segs[0] in skip or any(x.lower().lstrip('_') in FORM_SEGS for x in segs)):
            continue
        if segs and segs[-1] in ('text', 'value') and len(segs) >= 2 and (
                segs[-2].lower().endswith(('controller', 'field')) or
                (segs[-1] == 'value' and 'token' not in segs[-2].lower())):
            continue  # controller.text / formz input.value: FORM-004 (flutter-forms)
        for i, s in enumerate(segs):
            if s in ('headers',) and (i == 0 or segs[i - 1] not in ('response', 'res', 'resp', 'r')):
                if subscripted and i == len(segs) - 1:
                    continue  # headers['User-Agent']: the subscript key decides (checked below)
                return ch
            if is_secret_name(s, mode):
                nxt = segs[i + 1] if i + 1 < len(segs) else ''
                if nxt in NON_VALUE_PROPS:
                    break  # token.isNotEmpty / password.length: a property of the secret, not the secret
                return ch
    for k in keys:
        if is_secret_name(k, 'storekey'):
            return "['%s']" % k
    return None


L10N_PATH_RE = re.compile(r'(^|/)(l10n|i18n|intl|translations?|locales?|lang|langs|generated)(/|$)|'
                          r'(^|/)(app_)?(l10n|localizations?|messages|strings|translations?)[\w]*\.dart$|_(strings|l10n|translations?)\.dart$', re.I)
DATA_PATH_RE = re.compile(r'(^|/)(data|network|networking|net|api|apis|http|remote|services?|sources?|datasources?|'
                          r'data_sources?|clients?|repositories|infrastructure|infra|transport|interceptors?)(/|$)|'
                          r'_(client|api|service|source|datasource|interceptor|repository|repository_impl|http)\.dart$', re.I)


def is_l10n(rel):
    return bool(L10N_PATH_RE.search(rel))


FIELD_CB_RE = re.compile(r'\b(?:onChanged|onSaved|onFieldSubmitted|onSubmitted|onEditingComplete|validator|onCompleted)\s*:\s*'
                         r'(?:\(\s*(?:[\w?<>]+\s+)?(\w+)\s*\)|(\w+)\s*=>)')


def field_callback_params(sf, pos):
    """Parameter names of form-field callbacks enclosing pos (their values are FORM-004's)."""
    return {a or b for a, b in FIELD_CB_RE.findall(sf.masked[max(0, pos - 400):pos])}


def snippet(sf, ln):
    return sf.line_text(ln)[:160]


# --------------------------------------------------------------------------- checker

LOG_CALL_RE = re.compile(
    r'(?<![\w.$])(?:print|debugPrint|debugPrintSynchronously|log)\s*\(|'
    r'\b(?:developer|dev)\s*\.\s*log\s*\(|'
    r'\b\w*(?:[lL]ogger|[lL]og|[tT]alker|[fF]imber|[lL]ogging)\s*(?:\(\s*\))?\s*\.\s*'
    r'(?:d|i|w|e|v|t|f|wtf|debug|info|warning|warn|error|verbose|trace|fine|finer|finest|severe|shout|config|log|'
    r'handle|critical|good|logTyped)\s*\(')
ANALYTICS_RE = re.compile(
    r'\.\s*(?:logEvent|setUserProperty|setUserProperties|setCustomKey|setCustomKeys|addBreadcrumb|captureMessage|'
    r'track|trackEvent|identify|capture|setExtra|setExtras|setTag|setContexts|setUserIdentifier|setUserId|'
    r'logCustomEvent|registerSuperProperties)\s*\(|'
    r'(?<![\w.])Breadcrumb\s*\(|[cC]rashlytics\w*(?:\s*\.\s*instance)?\s*\.\s*log\s*\(')
STORE_RE = re.compile(r'\.\s*(setString|setStringList|put|write)\s*\(')
AUTH_HDR_RE = re.compile(r'[\'"](?:Authorization|authorization|AUTHORIZATION|X-Auth-Token|x-auth-token|X-Access-Token|'
                         r'x-access-token|X-Api-Key|x-api-key|X-API-KEY|X-API-Key|Api-Key|api-key|apikey)[\'"]\s*[:\],)]|'
                         r'\bHttpHeaders\s*\.\s*authorizationHeader\b|[\'"]Bearer\s+\$')
HTTP_LOGGERS = ('LogInterceptor', 'PrettyDioLogger', 'TalkerDioLogger', 'AwesomeDioInterceptor',
                'CurlLoggerDioInterceptor', 'ChuckerDioInterceptor', 'AliceDioAdapter', 'DioLoggingInterceptor',
                'RequestsInspectorInterceptor')
HTTP_LOGGER_RE = re.compile(r'(?<![\w.])(?:const\s+|new\s+)?(' + '|'.join(HTTP_LOGGERS) + r')\s*\(|\b(\w*alice\w*)\s*\.\s*getDioInterceptor\s*\(', re.I)
CERT_RE = re.compile(r'\b(badCertificateCallback|onBadCertificate|validateCertificate)\s*[:=]\s*'
                     r'(?:\([^()]*\)|\w+)\s*(?:=>\s*true\b|\{\s*return\s+true\s*;\s*\})')
JS_ON_RE = re.compile(r'\bJava[sS]criptMode\s*\.\s*unrestricted\b|\bjavaScriptEnabled\s*:\s*true\b|(?<![\w.])InAppWebView\s*\(')
JS_OFF_RE = re.compile(r'\bjavaScriptEnabled\s*:\s*false\b')
NAV_GUARD_RE = re.compile(r'\bonNavigationRequest\s*:|\bshouldOverrideUrlLoading\s*:|\bnavigationDelegate\s*:')
NAV_TRIVIAL_RE = re.compile(r'\bonNavigationRequest\s*:\s*\([^()]*\)\s*(?:async\s*)?(?:=>\s*NavigationDecision\s*\.\s*navigate\b|'
                            r'\{\s*return\s+NavigationDecision\s*\.\s*navigate\s*;\s*\})|'
                            r'\bshouldOverrideUrlLoading\s*:\s*\([^()]*\)\s*(?:async\s*)?(?:=>\s*NavigationActionPolicy\s*\.\s*ALLOW\b|'
                            r'\{\s*return\s+NavigationActionPolicy\s*\.\s*ALLOW\s*;\s*\})')
JS_CHANNEL_RE = re.compile(r'\baddJavaScriptChannel\s*\(|\bjavascriptChannels\s*:|\baddJavaScriptHandler\s*\(|\bJavascriptChannel\s*\(')
BODY_RE = re.compile(r'^(?:\w*(?:response|res|resp|result|reply)\w*\s*\.\s*(?:body|data|bodyBytes)|'
                     r'\w*(?:request|req|options|requestOptions)\w*\s*\.\s*(?:data|body|queryParameters)|'
                     r'body|payload|requestBody|responseBody|rawBody|jsonBody)$', re.I)
STRONG_SECRET_RE = re.compile(r'secret|private|passw|service_?role|signing', re.I)
AUTHISH_RE = re.compile(r'auth|login|logon|signin|sign_in|signup|session|token|account|user|profile|payment|card|otp|'
                        r'wallet|credential|password', re.I)
LOCAL_HOST_RE = re.compile(r'^(?:localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|10\.0\.2\.2|10\.0\.3\.2|\[::1\]|'
                           r'10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+|'
                           r'[\w.-]+\.(?:local|localhost|test|example|invalid|internal|lan|home)|'
                           r'(?:[\w-]+\.)*example\.(?:com|org|net))$', re.I)
NAMESPACE_HOST_RE = re.compile(r'^(?:www\.w3\.org|schemas\.android\.com|schemas\.xmlsoap\.org|schemas\.microsoft\.com|'
                               r'ns\.adobe\.com|purl\.org|xmlns\.com|www\.apple\.com|apple\.com|java\.sun\.com|'
                               r'schemas\.openxmlformats\.org|docs\.oasis-open\.org|www\.opengis\.net|'
                               r'json-schema\.org|xml\.org|www\.xml\.org|exslt\.org|ogp\.me|'
                               r'www\.google\.com/kml|earth\.google\.com|iptc\.org|cipa\.jp|ns\.useplus\.org)$', re.I)


class Checker(object):
    def __init__(self, root, files, texts, package, pubspec, profile):
        self.root, self.files, self.texts = root, files, texts
        self.package, self.pubspec, self.profile = package, pubspec, profile
        self.findings, self.suppressed = [], []
        self.seen = set()
        allm = '\n'.join(f.masked for f in files)
        self.hive_cipher = bool(re.search(r'\bencryptionCipher\s*:|\bHiveAesCipher\b', allm))
        self.db_cipher = bool(re.search(r'^\s+(?:sqlcipher_flutter_libs|sqflite_sqlcipher|sqlcipher)\s*:', pubspec, re.M)) or \
            bool(re.search(r"PRAGMA\s+key", '\n'.join(f.code for f in files)))
        self.hydrated = bool(re.search(r'\bextends\s+Hydrated(?:Bloc|Cubit)\b|\bwith\s+HydratedMixin\b', allm))

    def place(self):
        return PLACE.get(self.profile, PLACE['unknown'])

    def add(self, rid, sf, line, sev=None, note='', evidence=None, secrets=()):
        key = (rid, sf.rel, line)
        if key in self.seen:
            return
        self.seen.add(key)
        ev = mask_text(evidence if evidence is not None else snippet(sf, line), secrets)
        f = {'id': rid, 'name': RULES[rid][0], 'severity': sev or RULES[rid][1], 'file': sf.rel, 'line': line,
             'evidence': ev, 'message': RULES[rid][2], 'note': note}
        reason = sf.suppress_file.get(rid)
        if reason is None:
            for ln in (line, line - 1):
                r = sf.suppress_line.get(ln, {}).get(rid)
                if r:
                    reason = r
                    break
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': sf.rel, 'line': line, 'evidence': ev, 'reason': reason})
        else:
            self.findings.append(f)

    def run(self):
        for sf in self.files:
            self.check_storage(sf)
            self.check_auth_header(sf)
            self.check_cleartext(sf)
            log_lines = self.check_logs(sf)
            self.check_http_logger(sf)
            self.check_cert(sf)
            self.check_webview(sf)
            self.check_secrets(sf)
            self.check_build_config_dart(sf)
            self.check_holders(sf)
            self.check_body_logs(sf, log_lines)
        self.check_pubspec_env()
        self.check_ci()

    # SEC-001 ---------------------------------------------------------------
    def check_storage(self, sf):
        for m in STORE_RE.finditer(sf.masked):
            meth = m.group(1)
            op = m.end() - 1
            args, close = call_args(sf, op)
            if args is None:
                continue
            recv = re.search(r'([\w$.()!?\[\]\s]*?)\s*$', sf.masked[max(0, m.start() - 80):m.start()])
            recv = (recv.group(1) if recv else '').strip()
            recv_l = recv.lower()
            if re.search(r'secure|keychain|vault|keystore|encrypted', recv_l):
                continue
            parts = split_top(sf, op + 1, close)
            if not parts:
                continue
            if re.match(r'\s*\w+\s*:', sf.masked[parts[0][0]:parts[0][1]]):
                continue  # named args: flutter_secure_storage.write(key:, value:)
            kind = None
            if meth in ('setString', 'setStringList'):
                kind = 'prefs'
            elif meth == 'put':
                kind = 'hive' if (re.search(r'box|hive', recv_l) or re.search(r"package:hive", sf.code)) else 'kv'
            elif meth == 'write' and (re.search(r'package:get_storage', sf.code) or re.search(r'\bbox\b|getstorage|_storage\b|storage$', recv_l)):
                if not re.search(r'package:get_storage', sf.code) and re.search(r'package:flutter_secure_storage', sf.code):
                    continue
                kind = 'getstorage'
            if not kind or len(parts) < 2:
                continue
            k_s, k_e = parts[0]
            v_s, v_e = parts[1]
            keytxt = sf.code[k_s:k_e].strip()
            hit = None
            lm = re.match(r'^r?[\'"]([^\'"]*)[\'"]$', keytxt)
            if lm:
                if is_secret_name(lm.group(1), 'storekey'):
                    hit = 'key %r' % lm.group(1)
            else:
                last = re.findall(r'[A-Za-z_$][\w$]*', sf.masked[k_s:k_e])
                if last and is_secret_name(last[-1], 'storekey'):
                    hit = 'key %s' % last[-1]
            if not hit and kind == 'kv':
                continue  # an unknown store: only a secret-named key is strong enough evidence
            if not hit:
                chains, keys = expr_identifiers(sf, v_s, v_e)
                ch = secret_in_chains(chains, keys)
                if ch and not re.search(r'expir|time|date|At\b', ch):
                    hit = 'value %s' % ch
            if not hit:
                continue
            line = sf.line_of(m.start())
            if kind == 'hive':
                if self.hive_cipher:
                    self.add('SEC-001', sf, line, 'low', 'Hive box: the project uses an encryptionCipher somewhere; '
                             'confirm this box is opened with it and the key lives in secure storage (%s)' % hit)
                else:
                    self.add('SEC-001', sf, line, 'high', 'Hive box without encryptionCipher (%s). %s' % (hit, self.place()))
            elif kind == 'kv':
                self.add('SEC-001', sf, line, 'medium', 'a key-value store (%s.put, %s): confirm it is encrypted; if it is a '
                         'plain database or file, move the secret to flutter_secure_storage. %s' % (recv.split('.')[0] or 'store', hit, self.place()))
            elif kind == 'prefs':
                self.add('SEC-001', sf, line, 'high', 'SharedPreferences (%s); also scan.sh STO-TOKEN-PREFS. %s' % (hit, self.place()))
            else:
                self.add('SEC-001', sf, line, 'high', 'GetStorage is a plain JSON file (%s). %s' % (hit, self.place()))

        self.check_db_storage(sf)

    def check_db_storage(self, sf):
        """SEC-001 for databases: a secret column written through drift companions or sqflite maps."""
        uses_drift = bool(re.search(r"package:drift|package:moor|Companion\b", sf.code))
        uses_sqflite = bool(re.search(r"package:sqflite", sf.code))
        if not (uses_drift or uses_sqflite) or self.db_cipher:
            return
        hits = []
        if uses_drift:
            for m in re.finditer(r'\b(\w+Companion)(?:\s*\.\s*insert)?\s*\(', sf.masked):
                args, close = call_args(sf, m.end() - 1)
                if args is None:
                    continue
                for a_s, a_e in split_top(sf, m.end(), close):
                    nm = re.match(r'\s*([A-Za-z_]\w*)\s*:', sf.masked[a_s:a_e])
                    if nm and is_secret_name(nm.group(1), 'holder'):
                        hits.append((sf.line_of(a_s + len(sf.masked[a_s:a_e]) - len(sf.masked[a_s:a_e].lstrip())), nm.group(1)))
        if uses_sqflite:
            for m in re.finditer(r'\.\s*(?:insert|update)\s*\(', sf.masked):
                args, close = call_args(sf, m.end() - 1)
                if args is None:
                    continue
                for km in re.finditer(r'[\'"]([\w-]+)[\'"]\s*:', args):
                    if is_secret_name(km.group(1), 'holder'):
                        hits.append((sf.line_of(m.end() + km.start()), km.group(1)))
        if hits:
            line, col = hits[0]
            more = ' (+%d more in this file)' % (len(hits) - 1) if len(hits) > 1 else ''
            self.add('SEC-001', sf, line, 'high', 'column %s is written to an unencrypted %s database%s. Keep the token in '
                     'flutter_secure_storage and store only a reference, or encrypt the database (SQLCipher)' % (
                         col, 'drift' if uses_drift else 'sqflite', more))

    # SEC-002 ---------------------------------------------------------------
    def check_auth_header(self, sf):
        ui_roles = ('view', 'widget', 'logic', 'state', 'event', 'usecase', 'entity')
        if not (sf.layer in ('presentation', 'domain') or sf.role in ui_roles):
            return
        if sf.role in ('source', 'service', 'repository-impl', 'dto') or DATA_PATH_RE.search(sf.rel):
            return
        for m in AUTH_HDR_RE.finditer(sf.code):
            line = sf.line_of(m.start())
            where = '%s/%s' % (sf.layer, sf.role)
            self.add('SEC-002', sf, line, None, 'set in a %s file. %s' % (where, self.place()))

    # SEC-003 ---------------------------------------------------------------
    def check_cleartext(self, sf):
        if is_l10n(sf.rel):
            return
        low_path = bool(re.search(r'(^|/)(mock|mocks|fake|fakes|stub|stubs|demo|example|examples|sample|samples|debug|dev)(/|_|\.)', sf.rel.lower()))
        for s in sf.strings:
            content = sf.raw[s[2]:s[3]]
            for m in re.finditer(r'http://([^\s\'"/?#:]*)', content):
                host = m.group(1)
                if not host or host.startswith(('$', '{')):
                    continue
                if LOCAL_HOST_RE.match(host) or NAMESPACE_HOST_RE.match(host):
                    continue
                if '.' not in host and not re.match(r'^\d', host):
                    continue  # an intranet name or a placeholder ('http://local-ip', '[name](http://address)')
                rest = content[m.end():m.end() + 40]
                if NAMESPACE_HOST_RE.match(host + rest.split('"')[0].split("'")[0][:20]):
                    continue
                line = sf.line_of(s[0])
                text = sf.line_text(line)
                ctx = sf.masked[max(0, s[0] - 160):s[0]]
                if low_path or re.search(r'kDebugMode|debug|staging|\bdev\b|local|emulator|test|mock', ctx.split(';')[-1] + text, re.I):
                    self.add('SEC-003', sf, line, 'low', 'debug/dev-only context: %s' % host)
                elif not (sf.layer in ('data', 'core') or DATA_PATH_RE.search(sf.rel) or
                          re.search(r'baseUrl|base_url|endpoint|\bapi\b|Dio\s*\(|http\s*\.\s*(?:get|post|put|patch|delete)|'
                                    r'WebSocket|connect|BaseOptions|ApiClient', ctx.split(';')[-1] + text, re.I)):
                    self.add('SEC-003', sf, line, 'low', 'host %s, used as a link (no API call nearby): browsers usually upgrade it, '
                             'but write https://' % host)
                else:
                    self.add('SEC-003', sf, line, None, 'host %s. Android blocks cleartext by default (API 28+) and iOS ATS '
                             'blocks it for native stacks; Dart sockets are not bound by either' % host)
                break

    # SEC-004 ---------------------------------------------------------------
    def check_logs(self, sf):
        lines = set()
        dev_import = bool(re.search(r"import\s+'dart:developer'(?!\s+as)", sf.code))
        for rx, kind in ((LOG_CALL_RE, 'log'), (ANALYTICS_RE, 'analytics')):
            for m in rx.finditer(sf.masked):
                op = m.end() - 1
                args, close = call_args(sf, op)
                if args is None:
                    continue
                pre = sf.masked[max(0, m.start() - 12):m.start()]
                if re.search(r'\b(?:void|Future<\w*>|String|static)\s+$', pre):
                    continue  # a declaration, not a call
                chains, keys = expr_identifiers(sf, op + 1, close)
                ch = secret_in_chains(chains, keys, skip=field_callback_params(sf, m.start()))
                hdr_lit = None
                for s in sf.strings:
                    if not (op < s[0] < close):
                        continue
                    hm = re.search(r'\b(?:Authorization|Bearer|Cookie)\b\s*[:=]?\s*\$(?:\{([^}]*)\}|(\w+))', sf.raw[s[2]:s[3]], re.I)
                    if hm:
                        expr = (hm.group(1) or hm.group(2) or '').strip()
                        if not re.search(r'[!=]=|[<>]|\?\?|\bis\b', expr) and expr.split('.')[-1] not in NON_VALUE_PROPS:
                            hdr_lit = sf.raw[s[2]:s[3]][:40]
                if not ch and not hdr_lit:
                    continue
                line = sf.line_of(m.start())
                lines.add(line)
                what = ch or 'interpolated %r' % hdr_lit
                push = re.search(r'\b(?:fcm|push|apns|device|firebase|messaging|notification)\s*_?token', sf.code[m.start():close + 1], re.I)
                if push and kind == 'log':
                    self.add('SEC-004', sf, line, 'low', 'a push/device token (%s): less sensitive than a session token, '
                             'but it lets anyone with the server key target this device' % what)
                    continue
                if kind == 'log' and ch and ch.split('.')[-1].strip() == 'headers' and not AUTH_HDR_RE.search(sf.code):
                    self.add('SEC-004', sf, line, 'low', 'logs all of %s: they carry Authorization/Cookie whenever the request is '
                             'authenticated (none is set in this file)' % ch)
                    continue
                if kind == 'analytics':
                    self.add('SEC-004', sf, line, 'high', 'analytics/crash call sends %s off the device; also scan.sh PRV-LOG-LEAK' % what)
                elif debug_guarded(sf, m.start()):
                    self.add('SEC-004', sf, line, 'low', 'debug-only (guarded), but %s still reaches the console and any log forwarder' % what)
                elif (dev_import and re.match(r'log\s*\(', sf.masked[m.start():m.end()])) or 'developer' in m.group(0):
                    self.add('SEC-004', sf, line, 'low', "dart:developer log() is silent in release builds; %s is still visible to anyone debugging" % what)
                else:
                    self.add('SEC-004', sf, line, None, 'logs %s; print/debugPrint also run in release builds; also scan.sh PRV-LOG-LEAK' % what)
        return lines

    # SEC-005 ---------------------------------------------------------------
    def check_http_logger(self, sf):
        for m in HTTP_LOGGER_RE.finditer(sf.masked):
            pre = sf.masked[max(0, m.start() - 30):m.start()]
            if re.search(r'\b(?:class|extends|implements|with|import)\s+\w*\s*$', pre):
                continue
            name = m.group(1) or 'alice'
            if debug_guarded(sf, m.start()):
                continue
            op = m.end() - 1
            args, close = call_args(sf, op)
            args = re.sub(r'\s+', '', sf.masked[op + 1:close] if close else '')
            sev, note = 'medium', ''
            nl = name.lower()
            if nl == 'loginterceptor':
                hdr = 'requestHeader:false' not in args
                body = 'requestBody:true' in args or 'responseBody:true' in args
                custom = 'logPrint:' in args
                if not hdr and not body:
                    sev, note = 'low', 'headers and bodies off; URLs (and any query tokens) are still logged'
                else:
                    note = 'logs %s' % ', '.join(x for x, on in (('request headers incl. Authorization (default on)', hdr),
                                                                 ('bodies', body)) if on)
                    if custom:
                        sev, note = 'low', note + '; logPrint is custom: confirm that sink is silent in release'
            elif nl == 'prettydiologger':
                on = [x for x in ('requestHeader', 'requestBody', 'responseHeader') if x + ':true' in args]
                if 'responseBody:false' not in args:
                    on.append('responseBody (default on: login responses carry tokens)')
                if not on:
                    sev, note = 'low', 'headers and bodies off'
                else:
                    note = 'logs ' + ', '.join(on)
            elif nl in ('chuckerdiointerceptor', 'alicedioadapter', 'alice', 'requestsinspectorinterceptor'):
                note = 'an in-app HTTP inspector stores and shows full requests (headers, tokens, bodies) to whoever holds the phone'
            else:
                note = '%s: check which headers and bodies it prints' % name
            self.add('SEC-005', sf, sf.line_of(m.start()), sev, note + '. Wrap it in `if (kDebugMode)`')

    # SEC-006 ---------------------------------------------------------------
    def check_cert(self, sf):
        for m in CERT_RE.finditer(sf.masked):
            line = sf.line_of(m.start())
            if debug_guarded(sf, m.start()):
                self.add('SEC-006', sf, line, 'low', 'debug-only guard; prefer trusting a dev CA on the emulator. scan.sh: NET-ACCEPT-ALL')
            else:
                self.add('SEC-006', sf, line, None, '%s returns true. Overlaps scan.sh NET-ACCEPT-ALL (arrow form only); '
                         'this also matches block bodies, onBadCertificate and Dio validateCertificate' % m.group(1))

    # SEC-007 ---------------------------------------------------------------
    def check_webview(self, sf):
        m = JS_ON_RE.search(sf.masked)
        if not m:
            return
        inapp = 'InAppWebView' in m.group(0)
        if inapp and JS_OFF_RE.search(sf.masked):
            return
        guard = NAV_GUARD_RE.search(sf.masked)
        trivial = NAV_TRIVIAL_RE.search(sf.masked)
        channel = JS_CHANNEL_RE.search(sf.masked)
        if guard and not trivial:
            if inapp and 'shouldOverrideUrlLoading' in sf.masked and not re.search(r'useShouldOverrideUrlLoading\s*:\s*true', sf.masked):
                self.add('SEC-007', sf, sf.line_of(m.start()), 'medium',
                         'shouldOverrideUrlLoading is set but useShouldOverrideUrlLoading: true is not, so it never fires')
            return
        sev = 'high' if channel else 'medium'
        why = 'JavaScript is on (%s)%s and %s' % (
            'InAppWebView default' if inapp else 'JavaScriptMode.unrestricted',
            ' with a JS bridge (scan.sh WEB-JS-CHANNEL)' if channel else '',
            'navigation allows everything' if trivial else 'there is no navigation guard in this file')
        self.add('SEC-007', sf, sf.line_of(m.start()), sev,
                 why + '. Also validate URLs before loadRequest(): the delegate does not see programmatic loads on Android')

    # SEC-008 ---------------------------------------------------------------
    def check_secrets(self, sf):
        is_fb_opts = sf.rel.endswith('firebase_options.dart') or bool(re.search(r'\bFirebaseOptions\s*\(', sf.masked))
        info_done = False
        for s in sf.strings:
            content = sf.raw[s[2]:s[3]]
            if len(content) < 8:
                continue
            line = sf.line_of(s[0])
            hit = False
            for rx, label, sev in VENDOR:
                vm = rx.search(content)
                if not vm:
                    continue
                val = vm.group(0)
                if label == 'Google API key' and is_fb_opts:
                    if not info_done:
                        info_done = True
                        self.add('SEC-008', sf, line, 'info', 'Firebase apiKey: a public identifier by design, not a secret. '
                                 'Restrict it in Google Cloud and enable App Check (scan.sh SEC-CLOUDKEY reports it as Critical)', secrets=[val])
                    hit = True
                    break
                if label == 'JWT':
                    role = jwt_role(val)
                    if role in ('anon', 'anonymous', 'public'):
                        self.add('SEC-008', sf, line, 'info', 'a JWT with role "%s" (e.g. a Supabase anon key): public by design; '
                                 'protect data with row-level security' % role, secrets=[val])
                        hit = True
                        break
                    if role:
                        label = 'JWT with role "%s"' % role
                if label == 'credentials in a URL':
                    pw = re.search(r'://[^/\s:@]+:([^/\s:@]+)@', val)
                    secrets = [pw.group(1)] if pw else [val]
                else:
                    secrets = [val]
                self.add('SEC-008', sf, line, sev, '%s; also scan.sh SEC-HARDCODED/SEC-CLOUDKEY (which print the value unmasked)' % label,
                         secrets=secrets)
                hit = True
                break
            if hit or '$' in content and not s[4]:
                continue
            before = sf.code[max(0, s[0] - 80):s[0]]
            nm = re.search(r'([A-Za-z_$][\w$]*)[\'"]?\s*(?:[:=]|=>|\?\?)\s*$', before)
            if not nm or not is_secret_name(nm.group(1), 'holder') or is_l10n(sf.rel):
                continue
            if not looks_like_credential(content):
                continue
            if re.search(r'fromEnvironment\s*\([^)]*$', before):
                continue  # SEC-009 reports defaultValue literals
            self.add('SEC-008', sf, line, 'medium', '%s is assigned a literal credential (can\'t tell prod from test: '
                     'confirm, rotate if real)' % nm.group(1), secrets=[content])

    # SEC-009 (Dart side) ---------------------------------------------------
    def check_build_config_dart(self, sf):
        for m in re.finditer(r'\bString\s*\.\s*fromEnvironment\s*\(', sf.masked):
            op = m.end() - 1
            args, close = call_args(sf, op)
            if args is None:
                continue
            nm = re.match(r'\s*r?[\'"]([^\'"]+)[\'"]', args)
            if not nm or not is_secret_name(nm.group(1), 'holder'):
                continue
            dv = re.search(r'defaultValue\s*:\s*r?[\'"]([^\'"]+)[\'"]', args)
            line = sf.line_of(m.start())
            if dv and looks_like_credential(dv.group(1)):
                self.add('SEC-009', sf, line, 'medium', '--dart-define %s has a literal defaultValue: the secret is in source '
                         'control and in every build that omits the define' % nm.group(1), secrets=[dv.group(1)])
            elif STRONG_SECRET_RE.search(nm.group(1)):
                self.add('SEC-009', sf, line, 'medium', '--dart-define %s names a real secret, and it is compiled into the binary '
                         'as a plain string: move the operation that needs it to your backend' % nm.group(1))
            else:
                self.add('SEC-009', sf, line, 'low', '--dart-define %s is compiled into the binary as a plain string: '
                         'config, not a secret store' % nm.group(1))
        for m in re.finditer(r'\bdotenv\s*\.\s*(?:env\s*\[|get\s*\(|maybeGet\s*\(|getOrElse\s*\()\s*r?[\'"]([^\'"]+)[\'"]', sf.code):
            if sf.masked[m.start()] == ' ' or not is_secret_name(m.group(1), 'holder'):
                continue
            self.add('SEC-009', sf, sf.line_of(m.start()), 'medium' if STRONG_SECRET_RE.search(m.group(1)) else 'low', '.env value %s: flutter_dotenv ships the .env file as a '
                     'plain asset (see pubspec)' % m.group(1))
        for m in re.finditer(r'@EnviedField\s*\(([^)]*)\)\s*(?:static\s+)?(?:final\s+|const\s+)?(?:[\w?<>]+\s+)?([A-Za-z_$][\w$]*)', sf.masked):
            vn = re.search(r'varName\s*:\s*[\'"]', m.group(1))
            name = m.group(2)
            if vn:
                raw_args = sf.code[m.start():m.end()]
                vm = re.search(r'varName\s*:\s*[\'"]([^\'"]+)', raw_args)
                if vm:
                    name = vm.group(1) if is_secret_name(vm.group(1), 'holder') else name
            if not is_secret_name(name, 'holder'):
                continue
            obf = 'obfuscate:true' in re.sub(r'\s', '', m.group(1))
            self.add('SEC-009', sf, sf.line_of(m.start()), 'medium' if STRONG_SECRET_RE.search(name) else 'low', 'envied field %s%s: still recoverable from the binary' % (
                name, ' (obfuscate: true only raises the cost)' if obf else ''))

    # SEC-010 ---------------------------------------------------------------
    def check_holders(self, sf):
        m = sf.masked
        if re.search(r'@Envied\b', m):
            return  # envied classes are SEC-009
        decl = re.compile(r'(?m)^[ \t]*(?:@\w+[ \t]+)?(static[ \t]+)?(late[ \t]+)?(final[ \t]+|var[ \t]+|const[ \t]+)?'
                          r'(?:([A-Za-z_$][\w$]*(?:<[^;=(){}]*>)?\??)[ \t]+)?([A-Za-z_$][\w$]*)[ \t]*(=[^=>]|;)')
        state_like = sf.role in ('state', 'logic') or bool(re.search(r'\bextends\s+(?:Equatable|\w*State)\b', m))
        for dm in decl.finditer(m):
            static, late, kw, typ, name, end = dm.groups()
            if typ in ('return', 'import', 'export', 'part', 'library', 'typedef', 'else', 'await', 'yield', 'throw', 'case', 'show', 'hide', 'as'):
                continue
            if not typ and not kw:
                continue
            pos = dm.start(5)
            depth = sf.depth(pos)
            top = depth == 0
            if not (top or static or (state_like and depth == 1)):
                continue
            if not is_secret_name(name, 'holder'):
                continue
            if typ and re.search(r'^Object\??$|^dynamic$|CancelToken|IsolateToken|Key\b|Controller|FocusNode|Notifier|Stream|Completer|'
                                 r'Regex|RegExp|Widget|Duration|bool|int|double|DateTime|Timer|Function|Callback', typ):
                continue
            rhs = m[dm.end(6) - 1:m.find(';', dm.end(6) - 1) if m.find(';', dm.end(6) - 1) > 0 else dm.end(6)]
            rhs_code = sf.code[dm.end(6) - 1:dm.end(6) - 1 + len(rhs)]
            lit = re.match(r'^=?\s*r?[\'"]([^\'"]*)[\'"]\s*$', rhs_code.strip())
            if (kw or '').strip() == 'const' or lit:
                continue  # constants: key names, or SEC-008 if the value is a credential
            words = words_of(name)
            line = sf.line_of(dm.start(5))
            is_provider = bool(re.search(r'Provider\b|Provider\s*<|StateProvider|\.obs\b|Rx\w*<|ValueNotifier', rhs + (typ or '')))
            if top or static:
                mutable = not (kw or '').strip() in ('final', 'const')
                if is_provider:
                    self.add('SEC-010', sf, line, 'low', 'a global provider/observable holding %s: any widget can read it. %s' % (name, self.place()))
                elif mutable and name.startswith('_'):
                    self.add('SEC-010', sf, line, 'low', 'private %s %s is mutable and lives for the app lifetime (also ARCH-105); '
                             'fine as a cache of a secure-storage read, but clear it on logout' % ('static field' if static else 'global', name))
                elif mutable:
                    self.add('SEC-010', sf, line, 'medium', '%s %s is mutable and reachable from anywhere (also ARCH-105). %s' % (
                        'static field' if static else 'top-level variable', name, self.place()))
                else:
                    self.add('SEC-010', sf, line, 'low', '%s %s holds a secret for the app lifetime. %s' % (
                        'static final' if static else 'top-level final', name, self.place()))
            elif state_like and depth == 1 and ('token' in words or 'tokens' in words or 'jwt' in words or 'secret' in words):
                if self.hydrated and re.search(r'Hydrated|toJson|fromJson', m):
                    self.add('SEC-010', sf, line, 'medium', '%s is in UI state that HydratedBloc persists to disk (unencrypted unless '
                             'HydratedAesCipher)' % name)
                else:
                    self.add('SEC-010', sf, line, 'low', '%s in %s state/logic: observers, DevTools and toString() expose it; '
                             'expose isAuthenticated/User instead. %s' % (name, self.profile, self.place()))

    # SEC-011 ---------------------------------------------------------------
    def check_body_logs(self, sf, log_lines):
        if not (sf.layer == 'data' or sf.role in ('source', 'service', 'repository-impl')):
            return
        authish = bool(AUTHISH_RE.search(sf.rel.split('/')[-1])) or bool(re.search(r'class\s+\w*(?:Auth|Login|Session|Token|Account|User|Payment)\w*', sf.masked))
        for m in LOG_CALL_RE.finditer(sf.masked):
            line = sf.line_of(m.start())
            if line in log_lines:
                continue
            op = m.end() - 1
            args, close = call_args(sf, op)
            if args is None:
                continue
            pre = sf.masked[max(0, m.start() - 12):m.start()]
            if re.search(r'\b(?:void|Future<\w*>|String|static)\s+$', pre):
                continue
            chains, _keys = expr_identifiers(sf, op + 1, close)
            hit = None
            for ch in chains:
                c = re.sub(r'\s|[?!]', '', ch)
                parts = c.split('.')
                for i in range(len(parts)):
                    cand = '.'.join(parts[max(0, i - 1):i + 1])
                    if (i > 0 and BODY_RE.match(cand)) or (len(parts) == 1 and BODY_RE.match(parts[0])):
                        hit = c
                        break
                if hit:
                    break
            if not hit and re.search(r'\bjsonEncode\s*\(|\.toJson\s*\(\s*\)', sf.masked[op:close]):
                hit = 'jsonEncode/toJson'
            if not hit or debug_guarded(sf, m.start()):
                continue
            sev = 'medium' if authish else 'low'
            self.add('SEC-011', sf, line, sev, 'logs %s%s' % (hit, ' in an auth/user/payment data file' if authish else ''))

    # SEC-009 (pubspec) -----------------------------------------------------
    def check_pubspec_env(self):
        pf = self.texts.get('pubspec.yaml')
        if not pf:
            return
        in_assets, indent = False, 0
        for ln, text in enumerate(pf.lines, 1):
            stripped = text.split('#')[0].rstrip()
            if not stripped.strip():
                continue
            lead = len(stripped) - len(stripped.lstrip())
            if re.match(r'^\s*assets\s*:\s*$', stripped):
                in_assets, indent = True, lead
                continue
            if in_assets and lead <= indent and not stripped.lstrip().startswith('-'):
                in_assets = False
            if not in_assets:
                continue
            am = re.match(r'^\s*-\s*(?:path\s*:\s*)?[\'"]?([^\'"]+?)[\'"]?\s*$', stripped)
            if not am:
                continue
            asset = am.group(1)
            base = asset.rstrip('/').split('/')[-1]
            hit = None
            if re.match(r'^\.env(?:\.[\w-]+)?$|^[\w-]+\.env$', base):
                hit = asset
            elif asset.endswith('/'):
                d = os.path.join(self.root, asset)
                if os.path.isdir(d):
                    envs = [f for f in os.listdir(d) if re.match(r'^\.env(?:\.[\w-]+)?$', f)]
                    if envs:
                        hit = asset + envs[0]
            if hit:
                self.add('SEC-009', pf, ln, 'medium', '%s is bundled as a plain asset: anyone can unzip it from the APK/IPA '
                         '(assets/flutter_assets/). Keep secrets on the backend' % hit)

    # SEC-012 ---------------------------------------------------------------
    def check_ci(self):
        for rel, tf in sorted(self.texts.items()):
            if rel == 'pubspec.yaml':
                continue
            lines = tf.lines
            for i, text in enumerate(lines):
                code = re.sub(r'(^|\s)#.*$', '', text)
                bm = re.search(r'\bflutter\s+build\s+(apk|appbundle|aab|ipa|ios|macos)\b', code)
                if not bm:
                    continue
                joined = code
                j = i
                while joined.rstrip().endswith('\\') and j + 1 < len(lines):
                    j += 1
                    joined += ' ' + lines[j]
                for k in range(j + 1, min(j + 4, len(lines))):
                    nxt = lines[k].strip()
                    if nxt.startswith('--') or nxt.startswith('- --'):
                        joined += ' ' + nxt
                if re.search(r'--debug\b|--profile\b|--simulator\b|--config-only\b', joined):
                    continue
                if '--obfuscate' in joined:
                    continue
                self.add('SEC-012', tf, i + 1, None, 'flutter build %s without --obfuscate --split-debug-info=<dir>; keep the '
                         'symbols as a private CI artifact. Depth: flutter-security-audit L1.1/L7.2' % bm.group(1))


def jwt_role(tok):
    try:
        payload = tok.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode('ascii')).decode('utf-8', 'replace'))
        role = data.get('role') if isinstance(data, dict) else None
        return role if isinstance(role, str) else None
    except Exception:  # noqa: BLE001 - not a decodable JWT
        return None


# --------------------------------------------------------------------------- environment

def find_arch_check():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.normpath(os.path.join(here, '..', '..', 'flutter-architecture', 'scripts', 'arch_check.py'))
    return p if os.path.isfile(p) else None


def find_audit():
    env = os.environ.get('FLUTTER_SECURITY_AUDIT_DIR')
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [env] if env else [os.path.normpath(os.path.join(here, '..', '..', 'flutter-security-audit'))]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, 'scan.sh')):
            return os.path.join(c, 'scan.sh')
    return None


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


CI_GLOBS = ('codemagic.yaml', 'codemagic.yml', 'bitrise.yml', '.gitlab-ci.yml', 'azure-pipelines.yml', 'Makefile',
            'justfile', 'melos.yaml', 'fastlane/Fastfile', 'android/fastlane/Fastfile', 'ios/fastlane/Fastfile',
            '.circleci/config.yml', 'Jenkinsfile', 'appveyor.yml', '.travis.yml')


def ci_files(root):
    out = [p for p in CI_GLOBS if os.path.isfile(os.path.join(root, p))]
    for d in ('.github/workflows', 'scripts', 'tool', 'ci', '.'):
        full = os.path.join(root, d)
        if not os.path.isdir(full):
            continue
        for fn in sorted(os.listdir(full)):
            p = os.path.normpath(os.path.join(d, fn)).replace(os.sep, '/')
            if not os.path.isfile(os.path.join(root, p)):
                continue
            if d == '.github/workflows' and fn.endswith(('.yml', '.yaml')):
                out.append(p)
            elif fn.endswith(('.sh', '.bash')):
                out.append(p)
    return sorted(set(out))


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
    sys.stderr.write('check_secure_defaults.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_secure_defaults.py <project-root> [--json] [--files <list>] '
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
    for rel in rels:
        try:
            sf = SourceFile(root, rel)
        except OSError:
            continue
        if re.search(r'GENERATED CODE - DO NOT MODIFY', sf.raw[:400]):
            continue
        a = arch_files.get(rel)
        if a:
            sf.layer, sf.role, sf.feature = a.get('layer') or 'other', a.get('role') or 'other', a.get('feature')
        else:
            sf.layer, sf.role, sf.feature = classify_fallback(rel)
        if sf.layer in ('ui', 'view'):
            sf.layer = 'presentation'
        refine_role(sf)
        files.append(sf)

    texts = {}
    for rel in ['pubspec.yaml'] + ci_files(root):
        try:
            texts[rel] = SourceFile(root, rel, dart=False)
        except OSError:
            pass

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(pubspec, rels), 'fallback detection from pubspec and folders'

    ck = Checker(root, files, texts, package, pubspec, profile)
    ck.run()
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (SEV_ORDER.get(f['severity'], 9), f['id'], f['file'], f['line']))

    deps = set(re.findall(r'^\s{2,4}([\w]+)\s*:', pubspec, re.M))
    secure_storage = sorted(deps & {'flutter_secure_storage', 'biometric_storage', 'flutter_keychain', 'secure_storage'})
    http_clients = sorted(deps & {'dio', 'http', 'chopper', 'retrofit', 'graphql', 'graphql_flutter', 'get', 'ferry'})
    audit = find_audit()
    deep = ({'installed': True, 'scan': audit, 'command': 'bash %s %s' % (audit, root)} if audit else
            {'installed': False, 'install': 'git clone %s <your skills folder>/flutter-security-audit' % AUDIT_URL})
    report = {
        'schema': SCHEMA, 'root': root, 'package': package,
        'profile': {'presentation': profile, 'source': psource},
        'classification': classification,
        'stats': {'files': len(files), 'config_files': sorted(texts), 'secure_storage': secure_storage,
                  'http_clients': http_clients,
                  'reported_scope': 'files list (%d)' % len(only) if only is not None else 'all'},
        'deep_audit': deep,
        'findings': findings,
        'suppressed': suppressed,
    }
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        return 0
    out = ['== SECURITY DEFAULTS',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  scanned: %d Dart files, %d config files (%s)' % (len(files), len(texts), ', '.join(sorted(texts)) or 'none'),
           '  secure storage: %s; http: %s' % (', '.join(secure_storage) or 'no secure-storage dependency',
                                               ', '.join(http_clients) or 'none detected')]
    if audit:
        out.append('  deep audit: flutter-security-audit installed; run `bash %s %s`' % (audit, root))
    else:
        out.append('  deep audit: flutter-security-audit not installed (pinning, RASP, manifests, attestation not checked); '
                   'install from %s' % AUDIT_URL)
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    if not groups:
        out.append('  no security-default findings')
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
