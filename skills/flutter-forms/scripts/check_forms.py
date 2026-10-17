#!/usr/bin/env python3
"""check_forms.py: find insecure or buggy form code in a Flutter project (read-only).

Usage:
  python3 -I check_forms.py <project-root> [--json] [--files <list>] [--profile <p>] [--max n]

  --files    a file listing relative paths (one per line), or a comma-separated list.
             The whole project is still analysed (wrapper widgets are found across
             files); only findings in the listed files are reported.
  --profile  auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate (default auto).
  --max      example locations per rule in text mode (default 5).

Rules (details, false positives and fixes: references/rules.md):
  FORM-001 secret-field-not-obscured        FORM-005 submit-without-busy-guard
  FORM-002 secret-field-keyboard-learning   FORM-006 form-never-validated
  FORM-003 credential-field-missing-autofill FORM-007 input-type-mismatch
  FORM-004 field-value-logged               FORM-008 controller-created-inline

Fields are TextField, TextFormField, CupertinoTextField, CupertinoTextFormFieldRow,
FormBuilderTextField, ReactiveTextField, plus project widgets that wrap one of them
and expose an `obscureText` or `keyboardType` parameter. A field's kind (password,
pin, cvv, secret, otp, email, phone) is inferred from, in order: autofillHints,
keyboardType, controller name, label/hint text, key/name, validator and callbacks.

Profile and per-file roles come from ../flutter-architecture/scripts/arch_check.py
--json when that sibling skill is installed; otherwise a path-based fallback is used
and the output says so.

Suppression (in the analysed code):
  // form-ignore: FORM-001 <reason>        on the reported line, the line above, or inside the call
  // form-ignore-file: FORM-001 <reason>   anywhere in the file

Exit codes: 0 report produced (findings never fail the run), 2 usage/environment error.
Stdlib only, Python >= 3.8. Never writes to the project.
"""
import bisect
import json
import os
import re
import subprocess
import sys

SCHEMA = 'flutter-pro-skills/forms@1'
PROFILES = ('auto', 'mvn', 'mvvm', 'bloc', 'mvc', 'getx', 'provider', 'riverpod', 'setstate')
SEV_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}
SEV_DOWN = {'high': 'medium', 'medium': 'low', 'low': 'low', 'info': 'info'}

RULES = {
    'FORM-001': ('secret-field-not-obscured', 'medium',
                 'A password/PIN/CVV/secret field shows its value in clear text: set obscureText (a toggle is fine).'),
    'FORM-002': ('secret-field-keyboard-learning', 'low',
                 'A secret field with a show/hide toggle keeps keyboard suggestions on: while visible, the keyboard '
                 'shows and learns the secret. Add enableSuggestions: false and autocorrect: false.'),
    'FORM-003': ('credential-field-missing-autofill', 'low',
                 'A password or one-time-code field has no autofillHints, so password managers and SMS code '
                 'autofill cannot help (and users pick weaker passwords).'),
    'FORM-004': ('field-value-logged', 'medium',
                 'A field value (controller.text, an onChanged value, form state values) is sent to print/log/'
                 'analytics/crash reporting. Log the event, never the input.'),
    'FORM-005': ('submit-without-busy-guard', 'medium',
                 'An async submit runs from a button that stays enabled while it is in flight, so a double tap '
                 'submits twice. Disable the button (onPressed: null) or ignore taps while busy.'),
    'FORM-006': ('form-never-validated', 'medium',
                 'A Form has a GlobalKey<FormState> but nothing calls validate() on it, so its validators never '
                 'gate the submit.'),
    'FORM-007': ('input-type-mismatch', 'low',
                 'An email or phone field uses the default text keyboard. Set keyboardType '
                 '(TextInputType.emailAddress / TextInputType.phone).'),
    'FORM-008': ('controller-created-inline', 'high',
                 'A TextEditingController/FocusNode is created inline as a widget argument: every rebuild makes a '
                 'new one (the text and cursor reset, focus is lost) and none is ever disposed.'),
}

FIX_BY_PROFILE = {
    'FORM-005': {
        'mvn': 'MVN: let the notifier expose a sealed XSubmitting state and pass onPressed: state is XSubmitting ? null : submit',
        'riverpod': 'Riverpod: watch the AsyncValue and pass onPressed: state.isLoading ? null : submit',
        'mvvm': 'MVVM: run the submit through a Command and pass onPressed: command.running ? null : command.execute',
        'bloc': 'Bloc: disable while state.status.isInProgress, and/or use the droppable() transformer on the submit event',
        'provider': 'Provider: expose an isSubmitting flag (or a status enum) on the model and pass onPressed: model.isSubmitting ? null : submit',
        'getx': 'GetX: wrap the button in Obx and pass onPressed: controller.isSubmitting.value ? null : controller.submit',
        'mvc': 'MVC: expose a busy flag on the controller and pass onPressed: busy ? null : submit',
        'setstate': 'setState: keep a _submitting flag, return early when set, and pass onPressed: _submitting ? null : _submit',
    },
}

GENERATED_RE = re.compile(r'(\.g|\.freezed|\.gr|\.mocks|\.config|\.chopper|\.pb\w*)\.dart$|'
                          r'(^|/)app_localizations[^/]*\.dart$|(^|/)messages_[^/]*\.dart$')
SUPPRESS_RE = re.compile(r'form-ignore(-file)?\s*:\s*((?:FORM-\d{3})(?:\s*,\s*FORM-\d{3})*)\s*(.*)')

BUILTIN_FIELDS = ('TextFormField', 'TextField', 'CupertinoTextField', 'CupertinoTextFormFieldRow',
                  'FormBuilderTextField', 'ReactiveTextField')
FIELD_PARAMS = ('obscureText', 'keyboardType', 'autofillHints', 'enableSuggestions', 'autocorrect')

# ---------------------------------------------------------------------------------------- lexing


def lex(text):
    """Return (code, masked, comments).

    code:    comments blanked (newlines kept), strings intact.
    masked:  comments and string *contents* blanked (quotes kept); safe for bracket matching.
    """
    n = len(text)
    code = list(text)
    masked = list(text)
    comments = []

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
            i = j
        else:
            i += 1
    return ''.join(code), ''.join(masked), comments


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


class DartFile(object):
    def __init__(self, root, rel):
        self.rel = rel
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            self.raw = fh.read().replace('\r\n', '\n')
        self.code, self.masked, self.comments = lex(self.raw)
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
        self.role, self.layer = 'other', 'other'
        self.classes = []          # (name, open, close, header)
        self.funcs = []            # (name, header_start, body_open, body_close, is_async)
        self.suppress_line = {}    # line -> {id: reason}
        self.suppress_file = {}    # id -> reason
        self._parse()

    def line_of(self, pos):
        return bisect.bisect_right(self.line_starts, pos)

    def snippet(self, s, e, limit=110):
        t = ' '.join(self.raw[s:e].split())
        return t if len(t) <= limit else t[:limit - 3] + '...'

    def _parse(self):
        m = self.masked
        for mm in CLASS_RE.finditer(m):
            o = mm.end() - 1
            c = self.braces.get(o)
            if c is not None:
                self.classes.append((mm.group(2) or '', o, c, mm.group(0)))
        for mm in FUNC_RE.finditer(m):
            name = mm.group(1)
            if name in KEYWORDS:
                continue
            po = mm.end() - 1
            pc = self.parens.get(po)
            if pc is None:
                continue
            k = pc + 1
            tail = re.match(r'\s*(async\s*\*?|sync\s*\*)?\s*(\{|=>)', m[k:k + 40])
            if not tail:
                continue
            is_async = bool(tail.group(1) and tail.group(1).startswith('async'))
            bo = k + tail.start(2)
            if tail.group(2) == '{':
                bc = self.braces.get(bo)
                if bc is None:
                    continue
            else:
                bc = expr_end(m, bo + 2)
            self.funcs.append((name, mm.start(1), bo, bc, is_async))
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

    def enclosing_func(self, pos):
        best = None
        for f in self.funcs:
            if f[2] <= pos <= f[3] and (best is None or f[2] > best[2]):
                best = f
        return best

    def enclosing_class(self, pos):
        best = None
        for c in self.classes:
            if c[1] < pos < c[2] and (best is None or c[1] > best[1]):
                best = c
        return best

    def func_named(self, name, cls=None):
        for f in self.funcs:
            if f[0] == name and (cls is None or cls[1] < f[2] < cls[2]):
                return f
        return None


CLASS_RE = re.compile(r'\b(?:(?:abstract|sealed|final|base|interface|mixin)\s+)*(class|mixin|extension)\s+'
                      r'([A-Za-z_]\w*)?[^{;]*?\{')
FUNC_RE = re.compile(r'(?<![\w.$])([A-Za-z_$][\w$]*)[ \t]*(?:<[^<>(){};]*(?:<[^<>(){};]*>[^<>(){};]*)*>[ \t]*)?\(')
KEYWORDS = {'if', 'for', 'while', 'switch', 'catch', 'on', 'return', 'assert', 'super', 'this', 'new', 'await',
            'throw', 'when', 'with', 'yield', 'print', 'sizeOf', 'typeOf', 'const', 'else', 'do', 'try', 'in', 'is',
            'as', 'case', 'late', 'final', 'var'}


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


def split_args(df, po):
    """Named and positional args of the call whose '(' is at po: list of (name, vstart, vend)."""
    pc = df.parens.get(po)
    if pc is None:
        return [], po
    m = df.masked
    out, depth, start = [], 0, po + 1
    i = po + 1
    while i <= pc:
        c = m[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0 or i == pc:
                if i == pc:
                    seg = (start, i)
                    _add_arg(m, seg, out)
                    break
            depth -= 1
        elif c == ',' and depth == 0:
            _add_arg(m, (start, i), out)
            start = i + 1
        i += 1
    return out, pc


def _add_arg(m, seg, out):
    s, e = seg
    txt = m[s:e]
    if not txt.strip():
        return
    nm = re.match(r'\s*([A-Za-z_]\w*)\s*:(?!:)', txt)
    if nm:
        out.append((nm.group(1), s + nm.end(), e))
    else:
        out.append((None, s, e))


def arg_map(df, po):
    args, pc = split_args(df, po)
    d = {}
    for name, s, e in args:
        if name:
            d[name] = (s, e)
    return d, pc


# ---------------------------------------------------------------------------------------- field kinds

def toks_of(text):
    out = []
    for w in re.findall(r'[A-Za-z0-9]+', text):
        out += [p.lower() for p in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+', w)]
    return out


OTP_T = {'otp', 'totp', 'hotp', 'mfa', 'twofa', 'onetimecode'}
OTP_P = ('one time', 'verification code', 'verify code', 'sms code', 'auth code', 'authentication code',
         'two factor', '2 fa', 'confirmation code', 'security code', 'activation code', 'reset code')
PASSWORD_T = {'password', 'passwords', 'passwd', 'pwd', 'passphrase', 'pass', 'newpassword'}
PIN_T = {'pin', 'pincode', 'passcode', 'mpin'}
CVV_T = {'cvv', 'cvc', 'cvn', 'csc', 'cvv2'}
SECRET_T = {'secret', 'mnemonic'}
SECRET_P = ('api key', 'private key', 'access token', 'seed phrase', 'recovery phrase', 'secret key')
EMAIL_T = {'email', 'mail', 'emails'}
PHONE_T = {'phone', 'telephone', 'tel', 'mobile', 'msisdn', 'cellphone', 'phonenumber'}
GLOBAL_EXCLUDE = {'hint', 'hints', 'length', 'policy', 'strength', 'rule', 'rules', 'requirement', 'requirements',
                  'expiry', 'expire', 'expires', 'expiration', 'days', 'timeout', 'min', 'max', 'minimum', 'maximum',
                  'count', 'attempts', 'retries', 'question', 'search', 'filter', 'subject', 'body', 'template',
                  'signature', 'forgot', 'show', 'visible', 'visibility', 'toggle', 'enabled', 'enable', 'meter',
                  'generator', 'generate', 'protected', 'pinned', 'spin'}
CONTACT_EXCLUDE = {'user', 'username', 'name', 'login', 'or', 'host', 'server', 'smtp', 'imap', 'pop', 'port', 'url',
                   'domain', 'sender', 'from', 'reply', 'cc', 'bcc', 'code', 'country', 'prefix', 'extension',
                   'ext', 'type', 'verified', 'verification', 'status', 'template', 'settings', 'provider',
                   'notification', 'notifications', 'app', 'style', 'custom', 'css', 'html', 'content', 'design',
                   'footer', 'header'}
THIRD_PARTY = {'smtp', 'imap', 'pop3', 'gateway', 'contact', 'contacts', 'client', 'clients', 'vendor', 'vendors',
               'wifi', 'proxy', 'database', 'db', 'certificate', 'ftp', 'sftp', 'ssh', 'mqtt', 'vpn', 'shared',
               'share', 'link', 'album', 'archive', 'zip', 'pdf', 'webhook', 'integration'}
NEUTRAL_T = {'name', 'first', 'last', 'address', 'street', 'city', 'zip', 'postal', 'url', 'website', 'link',
             'amount', 'price', 'quantity', 'title', 'description', 'note', 'notes', 'comment', 'message', 'query',
             'username', 'server', 'host', 'port', 'date', 'number', 'iban', 'company'}
SECRET_KINDS = ('password', 'pin', 'cvv', 'secret')


def classify(text):
    t = toks_of(text)
    if not t:
        return None
    s = set(t)
    joined = ' ' + ' '.join(t) + ' '
    if s & GLOBAL_EXCLUDE:
        return 'other'
    if s & OTP_T or any(' %s ' % p in joined for p in OTP_P):
        return 'otp'
    if s & PASSWORD_T:
        return 'password'
    if s & PIN_T:
        return 'pin'
    if s & CVV_T:
        return 'cvv'
    if s & SECRET_T or any(' %s ' % p in joined for p in SECRET_P):
        return 'secret'
    if s & EMAIL_T or ' e mail ' in joined:
        return 'other' if s & CONTACT_EXCLUDE else 'email'
    if s & PHONE_T:
        return 'other' if s & CONTACT_EXCLUDE else 'phone'
    if s & NEUTRAL_T:
        return 'other'
    return None


SIMPLE_KBD = re.compile(r'^(?:const\s+)?(?:TextInputType\s*)?\.\s*\w+(?:\s*\([^()]*\))?$')
LABEL_ARGS = ('labelText', 'hintText', 'label', 'placeholder', 'hint', 'title', 'helperText')


def identifiers_only(df, s, e):
    """Identifier text of a span with string *contents* removed (keeps l10n keys like l10n.password)."""
    return df.masked[s:e]


def kind_sources(df, args, wrapper_label_args=()):
    """Yield (source, text) in priority order."""
    code = df.code
    if 'autofillHints' in args:
        s, e = args['autofillHints']
        v = code[s:e]
        if re.search(r'\b(?:newPassword|password)\b', v):
            yield 'autofillHints', 'password'
        elif re.search(r'\boneTimeCode\b', v):
            yield 'autofillHints', 'otp'
        elif re.search(r'\bemail\b', v):
            yield 'autofillHints', 'email'
        elif re.search(r'\btelephoneNumber\w*\b', v):
            yield 'autofillHints', 'phone'
        elif re.search(r'AutofillHints\.\w+', v):
            yield 'autofillHints', 'name'
    if 'keyboardType' in args and SIMPLE_KBD.match(code[args['keyboardType'][0]:args['keyboardType'][1]].strip()):
        s, e = args['keyboardType']
        v = code[s:e]
        if 'visiblePassword' in v:
            yield 'keyboardType', 'password'
        elif 'emailAddress' in v:
            yield 'keyboardType', 'email'
        elif re.search(r'\bphone\b', v):
            yield 'keyboardType', 'phone'
    if 'controller' in args:
        s, e = args['controller']
        yield 'controller', code[s:e]
    labels = []
    if 'decoration' in args:
        s, e = args['decoration']
        po = df.masked.find('(', s, e)
        if po >= 0:
            dargs, _ = arg_map(df, po)
            for k in LABEL_ARGS:
                if k in dargs:
                    labels.append(code[dargs[k][0]:dargs[k][1]])
    for k in LABEL_ARGS + tuple(wrapper_label_args):
        if k in args and k != 'decoration':
            labels.append(code[args[k][0]:args[k][1]])
    for lab in labels:
        yield 'label', lab
    for k in ('name', 'formControlName', 'key', 'restorationId'):
        if k in args:
            yield k, code[args[k][0]:args[k][1]]
    if 'validator' in args:
        s, e = args['validator']
        yield 'validator', code[s:e]
    for k in ('onChanged', 'onSaved', 'onFieldSubmitted', 'onSubmitted'):
        if k in args:
            s, e = args[k]
            yield k, identifiers_only(df, s, e)


def field_kind(df, args, pos, wrapper_label_args=()):
    for src, text in kind_sources(df, args, wrapper_label_args):
        if src in ('autofillHints', 'keyboardType'):
            if text == 'name':
                return 'other', src
            return text, src
        k = classify(text)
        if k:
            return k, src
    # a widget or helper named like a field: PasswordField, _buildPinInput()
    f = df.enclosing_func(pos)
    cands = []
    if f and f[0] != 'build':
        cands.append(f[0])
    c = df.enclosing_class(pos)
    if c:
        cands.append(re.sub(r'State$', '', c[0]))
    for nm in cands:
        t = toks_of(nm)
        if t and t[-1] in ('field', 'input', 'textfield', 'formfield', 'box', 'entry'):
            k = classify(nm)
            if k:
                return k, 'name of %s' % nm
    return 'other', None


# ---------------------------------------------------------------------------------------- checker

BARE_LOG = re.compile(r'(?<![\w$.])(print|debugPrint|log|dPrint|printLog|logPrint)\s*\(')
LOG_METHODS = ('log', 'logEvent', 'track', 'trackEvent', 'logCustomEvent', 'setUserProperty', 'setUserProperties',
               'setCustomKey', 'addBreadcrumb', 'captureMessage', 'captureException', 'recordError', 'logInfo',
               'logDebug', 'logError', 'd', 'i', 'w', 'e', 'v', 't', 'f', 'debug', 'info', 'warning', 'warn', 'error',
               'fine', 'finer', 'finest', 'severe', 'shout', 'verbose', 'trace', 'wtf', 'fatal')
ALWAYS_LOG_METHODS = set(LOG_METHODS[:13])
METHOD_LOG = re.compile(r'\.[ \t\n]*(' + '|'.join(LOG_METHODS) + r')\b[ \t]*\(')
RECV_RE = re.compile(r'([A-Za-z_$][\w$]*)[ \t\n]*(?:\([^()]*\))?[ \t\n]*[?!]?[ \t\n]*\.?$')
LOGGER_RECV = re.compile(r'(?i)(log|logger|analytics|crashlytics|sentry|mixpanel|amplitude|segment|tracker|'
                         r'telemetry|posthog|datadog|bugsnag|firebase|talker|developer)')


def iter_log_calls(m, lo=0, hi=None):
    # Yield (start, open_paren) for print/log/analytics/crash-reporting calls in m[lo:hi].
    hi = len(m) if hi is None else hi
    for bm in BARE_LOG.finditer(m, lo, hi):
        yield bm.start(), bm.end() - 1
    for mm in METHOD_LOG.finditer(m, lo, hi):
        rv = RECV_RE.search(m[max(0, mm.start() - 60):mm.start()])
        start = mm.start() - len(rv.group(0)) if rv else mm.start()
        if mm.group(1) in ALWAYS_LOG_METHODS or (rv and LOGGER_RECV.search(rv.group(1))):
            yield start, mm.end() - 1


CONTROLLER_TEXT = re.compile(r'(?<![\w$])((?:widget\s*\.\s*)?[A-Za-z_$][\w$]*)[!?]?\s*\.\s*text\b(?!\s*\.\s*'
                             r'(?:length|isEmpty|isNotEmpty|characters))')
FORM_VALUES = re.compile(r'\.\s*currentState\s*[!?]?\s*\.\s*(?:value|instantValue|fields)\b|'
                         r'\b(?:form|formGroup|_form)\s*\.\s*(?:value|rawValue)\b|\.\s*control\s*\([^)]*\)\s*\.\s*value\b')
BUTTON_RE = re.compile(r'(?<![\w$.])(?:const\s+)?([A-Z]\w*Button(?:\.\w+)?|FloatingActionButton(?:\.\w+)?)\s*\(')
BUSY = r'[\w$.]*(?:[Ll]oading|[Bb]usy|[Ss]ubmitting|[Ss]aving|[Ss]ending|[Ii]nProgress|[Rr]unning|[Pp]rocessing|' \
       r'[Pp]ending|[Ww]aiting|[Ss]igningIn|[Ll]oggingIn|[Ii]sSubmitting|[Pp]osting|[Uu]ploading|[Ss]pinner)[\w$]*'
BUSY_RE = re.compile(r'(?<![\w$])' + BUSY)
BUSY_IS = re.compile(r'\bis\s+\w*(?:Loading|InProgress|Submitting|Busy|Pending|Saving)\b|\.\s*running\b|'
                     r'\b(?:isInProgress|isInProgressOrSuccess|isSubmitting|isLoading|isBusy)\b')


def busy_cond(text):
    return bool(BUSY_IS.search(text) or BUSY_RE.search(text))


def if_conditions(df, lo, hi):
    # Yield (condition_text, text_after) for every if (...) in masked[lo:hi].
    m = df.masked
    for im in re.finditer(r'\bif\s*\(', m[lo:hi]):
        po = lo + im.end() - 1
        pc = df.parens.get(po)
        if pc is None:
            continue
        yield m[po + 1:pc], m[pc + 1:pc + 30]
SUBMIT_VERB = re.compile(r'(?i)(submit|save|login|logIn|signIn|signUp|register|send|pay|checkout|confirm|create|'
                         r'update|post|place|order|book|reserve|transfer|apply|redeem|purchase|buy|upload|verify|'
                         r'authenticate|reset|change|add|invite|join|subscribe|withdraw|deposit|request|validate)')
MODAL_AWAIT = re.compile(r'await\s+(?:Navigator\b|show\w*\s*[<(]|[\w$.()?!\s]*?\.\s*(?:push\w*|show\w*)\s*[<(])')
UI_AWAIT = re.compile(r'await\s+(?:Navigator\b|show\w*\s*[<(]|launch\w*\s*\(|'
                      r'[\w$.()?!\s]*?\.\s*(?:maybePop|pop\w*|push\w*|go|goNamed|replace\w*|navigate\w*|'
                      r'back|maybePopTop|show\w*)\s*[<(]|'
                      r'Future\s*\.\s*delayed|[\w.]*\.(?:push\w*|pop\w*|animateTo|jumpTo|nextPage|previousPage)\s*\(|'
                      r'Clipboard|HapticFeedback|SystemSound|SystemChrome|[\w.]*\.forward\s*\(|[\w.]*\.reverse\s*\(|'
                      r'[\w.]*ImagePicker|[\w.]*pick\w*\s*\(|[\w.]*share\w*\s*\(|Share\b)')


class Checker(object):
    def __init__(self, files, profile):
        self.files = files
        self.profile = profile
        self.findings = []
        self.suppressed = []
        self.stats = {'fields': 0, 'secret_fields': 0, 'otp_fields': 0, 'contact_fields': 0, 'forms': 0,
                      'submit_buttons': 0, 'wrappers': []}
        self.wrappers = {}
        self._otp_seen = set()
        self._logged = set()

    # -- reporting
    def add(self, df, rid, pos, evidence, note='', severity=None, span=None):
        ln = df.line_of(pos)
        sev = severity or RULES[rid][1]
        reason = None
        if rid in df.suppress_file:
            reason = df.suppress_file[rid]
        else:
            lines = [ln, ln - 1]
            if span:
                lines += list(range(df.line_of(span[0]), df.line_of(span[1]) + 1))
            for l in lines:
                if rid in df.suppress_line.get(l, {}):
                    reason = df.suppress_line[l][rid]
                    break
        if reason is not None:
            self.suppressed.append({'id': rid, 'file': df.rel, 'line': ln, 'reason': reason})
            return
        if not note and rid in FIX_BY_PROFILE:
            note = FIX_BY_PROFILE[rid].get(self.profile, '')
        self.findings.append({'id': rid, 'name': RULES[rid][0], 'severity': sev, 'file': df.rel, 'line': ln,
                              'evidence': evidence, 'message': RULES[rid][2], 'note': note})

    # -- wrappers: project widgets that build a field and expose its parameters
    def find_wrappers(self):
        names = '|'.join(BUILTIN_FIELDS)
        call = re.compile(r'(?<![\w$.])(?:' + names + r')\s*\(')
        for df in self.files:
            state_of = {}
            for name, o, c, header in df.classes:
                sm = re.search(r'\bextends\s+(?:State|ConsumerState)\s*<\s*(\w+)\s*>', header)
                if sm:
                    state_of[sm.group(1)] = (o, c)
            for name, o, c, header in df.classes:
                if not re.search(r'\bextends\s+\w*(?:Widget|StatelessWidget|StatefulWidget)\b', header):
                    continue
                if name in BUILTIN_FIELDS:
                    continue
                body = df.masked[o:c]
                spans = [(o, c)] + ([state_of[name]] if name in state_of else [])
                if not any(call.search(df.masked[s:e]) for s, e in spans):
                    continue
                params = set(p for p in FIELD_PARAMS
                             if re.search(r'\bfinal\s+[\w<>?,\s]+?\b%s\s*;' % p, body)
                             or re.search(r'\bthis\s*\.\s*%s\b' % p, body))
                if params & {'obscureText', 'keyboardType'}:
                    labels = set(re.findall(r'\bfinal\s+(?:String|Widget|Text)\??\s+(\w*(?:[Ll]abel|[Hh]int|'
                                            r'[Pp]laceholder|[Tt]itle)\w*)\s*;', body))
                    self.wrappers[name] = {'params': params, 'labels': labels, 'file': df.rel}
        self.stats['wrappers'] = sorted(self.wrappers)

    def run(self):
        self.find_wrappers()
        names = list(BUILTIN_FIELDS) + sorted(self.wrappers)
        self.field_re = re.compile(r'(?<![\w$.])(?:const\s+|new\s+)?(' + '|'.join(re.escape(n) for n in names) +
                                   r')[ \t]*(?:<[^()]*?>[ \t]*)?\(')
        for df in self.files:
            self.check_fields(df)
            self.check_logging(df)
            self.check_buttons(df)
            self.check_form_keys(df)
            self.check_inline_controllers(df)

    # -- FORM-001/002/003/007 and per-field FORM-004
    def check_fields(self, df):
        m, code = df.masked, df.code
        for mm in self.field_re.finditer(m):
            name = mm.group(1)
            po = mm.end() - 1
            args, pc = arg_map(df, po)
            if pc == po:
                continue
            argtxt = m[po:pc]
            if re.search(r'(?<![\w$])(?:this|super)\s*\.', argtxt):
                continue                            # a constructor declaration, not a call
            before = m[max(0, mm.start() - 12):mm.start()]
            if re.search(r'\b(?:class|extends|implements|with)\s*$', before):
                continue
            wrapper = self.wrappers.get(name)
            if wrapper and df.enclosing_class(mm.start()) and df.enclosing_class(mm.start())[0] == name:
                continue
            exposed = wrapper['params'] if wrapper else set(FIELD_PARAMS)
            self.stats['fields'] += 1
            kind, src = field_kind(df, args, mm.start(), wrapper['labels'] if wrapper else ())
            context = set(toks_of(df.rel) + toks_of((df.enclosing_class(mm.start()) or ('',))[0]))
            if kind == 'pin' and context & {'otp', 'verification', 'verify', 'sms', 'twofa', 'mfa', 'totp'}:
                kind, src = 'otp', '%s, in a one-time-code screen' % src
            box = bool(re.search(r'\bmaxLength\s*:\s*1\b|LengthLimitingTextInputFormatter\s*\(\s*1\s*\)',
                                 code[po:pc]))
            span = (mm.start(), pc)
            val = lambda k: code[args[k][0]:args[k][1]].strip() if k in args else None
            ev_head = '%s(%s)' % (name, self._short_args(df, args))
            if kind in SECRET_KINDS:
                self.stats['secret_fields'] += 1
            elif kind == 'otp':
                self.stats['otp_fields'] += 1
            elif kind in ('email', 'phone'):
                self.stats['contact_fields'] += 1
            readonly = val('readOnly') == 'true' or val('enabled') == 'false'
            obscure = val('obscureText')
            kbd = val('keyboardType') or ''
            numeric = bool(re.search(r'\b(?:number|phone|numberWithOptions|visiblePassword)\b', kbd))
            if kind in SECRET_KINDS and 'obscureText' in exposed and not readonly:
                if obscure is None or obscure == 'false':
                    self.add(df, 'FORM-001', mm.start(), ev_head,
                             note='%s field (from %s); obscureText %s' %
                                  (kind, src, 'is false' if obscure == 'false' else 'not set'), span=span,
                             severity='low' if kind == 'secret' else None)
                elif obscure != 'true' and not numeric:
                    missing = [p for p in ('enableSuggestions', 'autocorrect')
                               if p in exposed and val(p) != 'false']
                    if missing:
                        self.add(df, 'FORM-002', mm.start(), ev_head,
                                 note='obscureText: %s (a toggle); missing %s' %
                                      (obscure, ', '.join('%s: false' % p for p in missing)), span=span)
            obscured = obscure is not None and obscure != 'false'
            context |= set(toks_of(code[po:pc]))
            if ((kind == 'password' and obscured and not context & THIRD_PARTY) or (kind == 'otp' and not box)) \
                    and 'autofillHints' in exposed and 'autofillHints' not in args and not readonly:
                hint = 'AutofillHints.oneTimeCode' if kind == 'otp' else (
                    'AutofillHints.newPassword' if re.search(r'(?i)\b(?:new|confirm|repeat|retype|signup|register)',
                                                             ' '.join(toks_of(code[po:pc]))) else
                    'AutofillHints.password')
                if not (kind == 'otp' and df.rel in self._otp_seen):     # split code boxes: once per screen
                    if kind == 'otp':
                        self._otp_seen.add(df.rel)
                    self.add(df, 'FORM-003', mm.start(), ev_head,
                             note='%s field (from %s); add autofillHints: const [%s]' % (kind, src, hint), span=span)
            if kind in ('email', 'phone') and 'keyboardType' in exposed and not readonly and \
                    (not kbd or SIMPLE_KBD.match(kbd)) and \
                    'multiline' not in kbd and not re.search(r'\bmaxLines\s*:\s*(?:null|[2-9])', code[po:pc]):
                want = 'emailAddress' if kind == 'email' else 'phone'
                bad = False
                if not kbd:
                    bad = True
                elif kind == 'email' and re.search(r'TextInputType\s*\.\s*(?:text|name|multiline)\b|^\.(?:text|name)$', kbd):
                    bad = True
                elif kind == 'phone' and re.search(r'TextInputType\s*\.\s*(?:text|name|multiline)\b|^\.(?:text|name)$', kbd):
                    bad = True
                if bad:
                    self.add(df, 'FORM-007', mm.start(), ev_head,
                             note='%s field (from %s); keyboardType %s, want TextInputType.%s' %
                                  (kind, src, kbd or 'not set', want), span=span)
            # values of this field flowing to logs through its own callbacks
            for k in ('onChanged', 'onSaved', 'onFieldSubmitted', 'onSubmitted', 'validator'):
                if k not in args:
                    continue
                s, e = args[k]
                pm = re.match(r'\s*\(\s*(?:[\w<>?]+\s+)?([A-Za-z_$][\w$]*)\s*\)\s*(?:async\s*)?(?:\{|=>)', m[s:e])
                if not pm:
                    continue
                pname = pm.group(1)
                for ls, lpo in iter_log_calls(m, s, e):
                    lpc = df.parens.get(lpo, lpo)
                    seg = code[lpo:lpc]
                    if re.search(r'(?<![\w$.])\$?\{?\s*%s\b(?!\s*\.\s*(?:length|isEmpty|isNotEmpty))' %
                                 re.escape(pname), seg):
                        self._log_finding(df, ls, lpc, kind, '%s value `%s`' % (k, pname))

    def _short_args(self, df, args):
        keep = []
        for k in ('controller', 'obscureText', 'keyboardType', 'autofillHints', 'labelText', 'label', 'name',
                  'enableSuggestions', 'autocorrect'):
            if k in args:
                keep.append('%s: %s' % (k, ' '.join(df.code[args[k][0]:args[k][1]].split())[:40]))
        if 'decoration' in args and len(keep) < 3:
            keep.append('decoration: ...')
        return ', '.join(keep[:4]) + (', ...' if len(args) > len(keep[:4]) else '')

    def _log_finding(self, df, pos, end, kind, what):
        sev = 'high' if kind in SECRET_KINDS + ('otp',) else 'medium'
        note = '%s (%s field)' % (what, kind)
        if self._debug_guarded(df, pos):
            sev = SEV_DOWN[sev]
            note += '; only in debug builds'
        key = (df.rel, df.line_of(pos))
        if key in self._logged:
            return
        self._logged.add(key)
        self.add(df, 'FORM-004', pos, df.snippet(pos, end + 1), note=note, severity=sev)

    def _debug_guarded(self, df, pos):
        o = None
        k = bisect.bisect_left(df.brace_opens, pos) - 1
        if k >= 0:
            o = df.brace_opens[k]
            while o is not None and not (o < pos < df.braces.get(o, -1)):
                o = df.parent.get(o)
        while o is not None:
            head = df.masked[max(0, o - 60):o]
            if re.search(r'\bif\s*\(\s*(?:kDebugMode|!\s*kReleaseMode|kProfileMode)\b[^)]*\)\s*$', head) or \
                    re.search(r'\bassert\s*\(\s*\(\s*\)\s*$', head):
                return True
            o = df.parent.get(o)
        return False

    # -- FORM-004: controller.text / form values logged anywhere
    def check_logging(self, df):
        m, code = df.masked, df.code
        if not hasattr(self, '_logged'):
            self._logged = set()
        ctrl_vars = set(re.findall(r'\b([A-Za-z_$][\w$]*)\s*=\s*(?:new\s+)?TextEditingController\b', m))
        ctrl_vars |= set(re.findall(r'\bTextEditingController\??\s+([A-Za-z_$][\w$]*)', m))
        ctrl_vars |= set(re.findall(r'\b([A-Za-z_$][\w$]*)\s*=\s*useTextEditingController\b', m))
        for ls, lpo in iter_log_calls(m):
            lpc = df.parens.get(lpo)
            if lpc is None:
                continue
            seg = code[lpo:lpc]
            hit = None
            for cm in CONTROLLER_TEXT.finditer(seg):
                v = re.sub(r'\s+', '', cm.group(1))
                bare = v.split('.')[-1]
                st = cm.start()
                if st > 0 and seg[st - 1] == '$':
                    continue                            # "$name.text" interpolates only `name`
                if bare in ctrl_vars or re.search(r'(?i)(controller|ctrl|textcontroller|editingcontroller)$', bare):
                    hit = v
                    break
            if hit:
                kind = classify(hit) or 'other'
                self._log_finding(df, ls, lpc, kind, '`%s.text`' % hit)
                continue
            if FORM_VALUES.search(seg):
                kind = 'password' if re.search(r'(?i)password|pin|otp|cvv|secret', seg) else 'other'
                self._log_finding(df, ls, lpc, kind, 'form state values')

    # -- FORM-005 double submit
    def check_buttons(self, df):
        m, code = df.masked, df.code
        for bm in BUTTON_RE.finditer(m):
            po = bm.end() - 1
            args, pc = arg_map(df, po)
            if pc == po:
                continue
            argtxt = m[po:pc]
            if re.search(r'(?<![\w$])(?:this|super)\s*\.', argtxt):
                continue
            hk = 'onPressed' if 'onPressed' in args else ('onTap' if 'onTap' in args else None)
            if not hk:
                continue
            hs, he = args[hk]
            hv = m[hs:he].strip()
            # busy-aware custom buttons: AppButton(isLoading: ..., onPressed: ...)
            if any(re.search(r'(?i)(loading|busy|progress|submitting|running|spinner|pending)', k) for k in args):
                continue
            if '?' in hv or re.search(r'\bnull\b', hv) or '&&' in hv or '||' in hv:
                continue
            body, hname, hfunc = None, None, None
            cm = re.match(r'\(\s*\)\s*(async)?\s*(\{|=>)', hv)
            cls = df.enclosing_class(bm.start())
            if cm:
                if not cm.group(1):
                    # () => _submit()  /  () { _submit(); }: follow one call into this class
                    inner = re.match(r'\(\s*\)\s*(?:=>\s*|\{\s*)(?:await\s+)?([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*;?\s*\}?\s*$',
                                     hv)
                    if inner:
                        hname = inner.group(1)
                        hfunc = df.func_named(hname, cls) or df.func_named(hname)
                    if not hfunc:
                        continue
                else:
                    body = (hs, he)
            elif re.match(r'^[A-Za-z_$][\w$]*$', hv):
                hname = hv
                hfunc = df.func_named(hname, cls) or df.func_named(hname)
                if not hfunc:
                    continue
            else:
                continue
            if hfunc:
                if not hfunc[4]:
                    continue
                body = (hfunc[2], hfunc[3])
            btxt = m[body[0]:body[1]]
            awaits = [a for a in re.finditer(r'\bawait\b', btxt)]
            real = [a for a in awaits if not UI_AWAIT.match(btxt, a.start())]
            if not real:
                continue
            first_await = real[0].start()
            if any(MODAL_AWAIT.match(btxt, a.start()) for a in awaits if a.start() < first_await):
                continue                                # a dialog/route covers the button before the work starts
            submitish = bool(re.search(r'\bcurrentState\s*[!?]?\s*\.\s*(?:validate|save|saveAndValidate)\s*\(|'
                                       r'\.\s*validate\s*\(\s*\)', btxt)) or \
                bool(hname and SUBMIT_VERB.search(hname))
            if not submitish:
                for a in real:
                    callee = re.match(r'await\s+([\w$.?!()\s]*?)\s*\(', btxt[a.start():a.start() + 160])
                    if callee and SUBMIT_VERB.search(callee.group(1).split('.')[-1] if '.' in callee.group(1)
                                                     else callee.group(1)):
                        submitish = True
                        break
            if not submitish:
                continue
            self.stats['submit_buttons'] += 1
            # guard inside the handler before its first real await
            pre = btxt[:first_await]
            if any(busy_cond(c) and re.match(r'\s*(?:\{\s*)?return\b', after)
                   for c, after in if_conditions(df, body[0], body[0] + first_await)):
                continue
            # a busy flag set by the handler and read in a condition outside this button
            flags = set(re.findall(r'(?<![\w$.])(_?[A-Za-z$][\w$]*)\s*(?:\.value)?\s*=\s*true\b', pre))
            flags |= set(re.findall(r'(?<![\w$.])(_?[A-Za-z$][\w$]*)\s*\(\s*true\s*\)', pre))
            if self._flag_read_outside(df, flags, (bm.start(), pc)):
                continue
            # the enclosing build swaps or blocks the button while busy
            if self._busy_condition_around(df, bm.start(), pc):
                continue
            where = hname or 'inline async closure'
            self.add(df, 'FORM-005', bm.start(), '%s(%s: %s)' % (bm.group(1), hk, ' '.join(code[hs:he].split())[:60]),
                     note=FIX_BY_PROFILE['FORM-005'].get(self.profile, '') +
                     ('' if self.profile in FIX_BY_PROFILE['FORM-005'] else
                      'disable the button while %s is running' % where), span=(bm.start(), pc))

    def _flag_read_outside(self, df, flags, span):
        if not flags:
            return False
        m = df.masked
        for f in flags:
            for um in re.finditer(r'(?<![\w$])%s\b' % re.escape(f), m):
                if span[0] <= um.start() <= span[1]:
                    continue
                after = m[um.end():um.end() + 30]
                before = m[max(0, um.start() - 40):um.start()]
                if re.match(r'\s*(?:\.value\s*)?(?:\?(?!\?|\.)|\|\||&&|\))', after) and \
                        not re.match(r'\s*(?:\.value\s*)?=(?!=)', after):
                    if re.search(r'(?:\bif\s*\(|\?|:|\(|!|&&|\|\||return|=>|ignoring\s*:|absorbing\s*:)\s*!?\s*$',
                                 before) or re.match(r'\s*(?:\.value\s*)?\?', after):
                        return True
        return False

    def _busy_condition_around(self, df, start, end):
        f = df.enclosing_func(start)
        lo = f[2] if f else max(0, start - 1500)
        hi = f[3] if f else min(len(df.masked), end + 300)
        m = df.masked
        for c, _ in if_conditions(df, lo, hi):
            if busy_cond(c):
                return True
        for rng in ((lo, start), (end, hi)):
            for q in re.finditer(r'\?(?![?.\[])', m[rng[0]:rng[1]]):
                qpos = rng[0] + q.start()
                k = qpos
                while k > rng[0] and m[k - 1] not in ',;{}()[]:=>\n':
                    k -= 1
                if busy_cond(m[k:qpos]):
                    return True
            for am in re.finditer(r'\b(?:ignoring|absorbing)\s*:', m[rng[0]:rng[1]]):
                v0 = rng[0] + am.end()
                if busy_cond(m[v0:expr_end(m, v0)]):
                    return True
        return False

    # -- FORM-006 GlobalKey<FormState> never validated
    def check_form_keys(self, df):
        m = df.masked
        self.stats['forms'] += len(re.findall(r'(?<![\w$.])(?:Form|FormBuilder|ReactiveForm)\s*\(', m))
        for km in re.finditer(r'(?<![\w$])([A-Za-z_$][\w$]*)\s*=\s*(?:new\s+)?GlobalKey\s*<\s*(?:FormState|'
                              r'FormBuilderState)\s*>\s*\(', m):
            key = km.group(1)
            uses = list(re.finditer(r'(?<![\w$])%s\b' % re.escape(key), m))
            if not re.search(r'(?<![\w$.])(?:Form|FormBuilder)\s*\([^;]*?\bkey\s*:\s*%s\b' % re.escape(key), m, re.S):
                continue
            if not re.search(r'\bvalidator\s*:', m):
                continue                                # no validators: the key is unused, not a gap
            if re.search(r'(?<![\w$])%s\s*\.\s*currentState\s*[!?]?\s*\.\s*(?:validate|saveAndValidate)\s*\(' %
                         re.escape(key), m):
                continue
            if re.search(r'(?<![\w$])%s\s*\.\s*currentState\b\s*[!?]?\s*;' % re.escape(key), m) or \
                    re.search(r'=\s*%s\s*\.\s*currentState\b' % re.escape(key), m):
                continue                                # aliased: final form = _key.currentState; form.validate()
            passed = False
            for u in uses:
                before = m[max(0, u.start() - 40):u.start()]
                if re.search(r'(?<!\bkey)(?<![\w$])(?:[A-Za-z_$][\w$]*\s*:|\(|,)\s*$', before) and \
                        not re.search(r'\bkey\s*:\s*$', before):
                    passed = True                       # handed to another widget/notifier that may validate
                    break
            if passed:
                continue
            self.add(df, 'FORM-006', km.start(), df.snippet(km.start(), m.find(')', km.end()) + 1),
                     note='no %s.currentState!.validate() in this file' % key)

    # -- FORM-008 controller/focus node created inline
    def check_inline_controllers(self, df):
        m = df.masked
        for cm in re.finditer(r'\b(controller|focusNode)\s*:\s*(?:new\s+)?(TextEditingController|FocusNode)\s*'
                              r'(?:\.\s*\w+)?\s*\(', m):
            f = df.enclosing_func(cm.start())
            if f is None:
                continue                                 # field initializer
            if f[0] in ('initState', 'didChangeDependencies') or re.match(r'^[A-Z]', f[0]):
                continue
            if self._inside_create_callback(df, cm.start(), f):
                continue
            po = m.find('(', cm.end() - 1)
            pc = df.parens.get(cm.end() - 1, cm.end())
            self.add(df, 'FORM-008', cm.start(), df.snippet(cm.start(), pc + 1),
                     note='inside %s(); create it once in initState (or %s) and dispose it' %
                     (f[0], 'useFocusNode' if cm.group(2) == 'FocusNode' else 'useTextEditingController'))

    @staticmethod
    def _inside_create_callback(df, pos, f):
        head = df.masked[max(0, f[1] - 40):f[1]]
        return bool(re.search(r'\b(?:create|init)\s*:\s*$', head))


# ---------------------------------------------------------------------------------------- classification

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
    if any(s in ('notifier', 'notifiers', 'view_model', 'view_models', 'viewmodel', 'viewmodels', 'bloc', 'blocs',
                 'cubit', 'cubits', 'controller', 'controllers') for s in segs) or \
            re.search(r'_(notifier|view_model|viewmodel|bloc|cubit|controller|store)\.dart$', base):
        return 'presentation', 'logic'
    if any(s in ('view', 'views', 'screens', 'pages', 'ui') for s in segs) or \
            re.search(r'_(screen|page|view)\.dart$', base):
        return 'presentation', 'view'
    if any(s in ('widget', 'widgets', 'presentation', 'forms') for s in segs):
        return 'presentation', 'widget'
    if 'domain' in segs:
        return 'domain', 'other'
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
    sys.stderr.write('check_forms.py: %s\n' % msg)
    sys.stderr.write('usage: python3 -I check_forms.py <project-root> [--json] [--files <list>] '
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
            df = DartFile(root, rel)
        except OSError:
            continue
        if re.search(r'GENERATED CODE - DO NOT MODIFY', df.raw[:400]):
            continue
        a = arch_files.get(rel)
        if a:
            df.layer, df.role = a.get('layer') or 'other', a.get('role') or 'other'
        else:
            df.layer, df.role = classify_fallback(rel)
        files.append(df)

    if opts['profile'] != 'auto':
        profile, psource = opts['profile'], 'declared (--profile)'
    elif arch and isinstance(arch.get('profile'), dict) and arch['profile'].get('presentation'):
        profile = arch['profile']['presentation']
        psource = 'arch_check, confidence %s' % arch['profile'].get('confidence', '?')
    else:
        profile, psource = detect_profile_fallback(pubspec, rels), 'fallback detection from pubspec and folders'

    ck = Checker(files, profile)
    ck._logged = set()
    if files:
        ck.run()
    findings, suppressed = ck.findings, ck.suppressed
    if only is not None:
        findings = [f for f in findings if f['file'] in only]
        suppressed = [s for s in suppressed if s['file'] in only]
    findings.sort(key=lambda f: (f['id'], SEV_ORDER.get(f['severity'], 9), f['file'], f['line']))

    stats = dict(ck.stats)
    stats['files'] = len(files)
    stats['reported_scope'] = 'files list (%d)' % len(only) if only is not None else 'all'
    report = {
        'schema': SCHEMA, 'root': root, 'package': package,
        'profile': {'presentation': profile, 'source': psource},
        'classification': classification,
        'stats': stats,
        'findings': findings,
        'suppressed': suppressed,
    }
    if opts['json']:
        sys.stdout.write(json.dumps(report, indent=2) + '\n')
        return 0
    out = ['== FORMS',
           '  profile: %s (%s)' % (profile, psource),
           '  classification: %s' % classification,
           '  scanned: %d files, %d fields (%d secret, %d one-time-code, %d email/phone), %d forms, '
           '%d async submit buttons' % (len(files), stats['fields'], stats['secret_fields'], stats['otp_fields'],
                                        stats['contact_fields'], stats['forms'], stats['submit_buttons'])]
    if stats['wrappers']:
        out.append('  field wrappers: %s' % ', '.join(stats['wrappers'][:8]) +
                   (' ... %d more' % (len(stats['wrappers']) - 8) if len(stats['wrappers']) > 8 else ''))
    groups, index = [], {}
    for f in findings:
        k = (f['id'], f['severity'])
        if k not in index:
            index[k] = len(groups)
            groups.append((k, []))
        groups[index[k]][1].append(f)
    groups.sort(key=lambda g: (SEV_ORDER.get(g[0][1], 9), g[0][0]))
    if not groups:
        out.append('  no form findings')
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
