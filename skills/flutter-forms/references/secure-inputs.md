# Secure inputs and accessible fields

Write these defaults into every field the first time. They cost one line each,
and adding them later means re-reviewing every screen. Deep audits (RASP,
screenshot blocking, pinning) live in `flutter-security-audit`. Write-time
security defaults outside forms (token storage, logging policy, HTTPS) live in
`flutter-secure-defaults`. This file covers what happens inside a form.

## Contents

1. Secret fields: password, PIN, CVV, API key
2. Autofill: AutofillGroup, hints, finishAutofillContext
3. One-time codes (OTP)
4. Never log or report field values
5. Clipboard and paste
6. Client validation is UX; the server decides
7. Keyboard types and actions
8. Accessibility: labels, errors, focus order, text scale
9. A secure field template

## 1. Secret fields

| Setting | Why |
|---|---|
| `obscureText: true` (or a toggle that starts `true`) | Hides the value from shoulder-surfers and casual screen recordings. Obscured text also can't be copied or cut from the field (FORM-001) |
| `enableSuggestions: false` and `autocorrect: false` | While the field is obscured, the platforms already treat it as a password: Android adds the no-suggestions and password input-type flags, iOS uses secure text entry. The moment a "show password" toggle makes it visible, those protections go away, and the keyboard shows suggestions and can **learn the secret into its dictionary**. Set both whenever `obscureText` can become `false` (FORM-002) |
| `enableIMEPersonalizedLearning: false` | Android: asks the keyboard not to store what's typed (incognito mode). Worth adding to secret and payment fields |
| `keyboardType: TextInputType.visiblePassword` | For a password toggled visible: Android keyboards treat it as a password variation (no suggestions) |
| `maxLength` | Passwords ≤128, PIN/CVV their exact length. It matches the server and stops absurd pastes |
| no `onChanged` logging, no analytics | §4 |
| no `initialValue` from storage | never pre-fill a password from your own storage; let the OS password manager fill it |
| `readOnly` display | showing an API key once for copying is a deliberate exception. Mark it `readOnly: true` (the checker then skips it) |

Severity in the checker: an unobscured password, PIN or CVV is Medium. An
unobscured API key or token is Low, because admin screens often show keys on
purpose. Suggest a toggle anyway.

Don't obscure **one-time codes**. They're short-lived, and users need to see
them while copying them from another screen. Don't obscure usernames or emails
either. A show/hide toggle on passwords is good practice: NIST SP 800-63B
recommends letting users see the secret while they type it. That's why
FORM-002 exists, not a reason to drop the toggle.

## 2. Autofill

Password managers (iOS Keychain, Google Password Manager, 1Password and others)
need three things:

```dart
AutofillGroup(                                   // 1. group the fields of one credential
  child: Column(children: [
    TextFormField(
      controller: _email,
      keyboardType: TextInputType.emailAddress,
      autofillHints: const [AutofillHints.username, AutofillHints.email], // 2. hints
      textInputAction: TextInputAction.next,
    ),
    TextFormField(
      controller: _password,
      obscureText: true,
      autofillHints: const [AutofillHints.password],   // sign-up / change: AutofillHints.newPassword
      textInputAction: TextInputAction.done,
      onFieldSubmitted: (_) => _submit(),
    ),
  ]),
)

// 3. after a successful sign-in or sign-up, tell the OS to offer "save password"
TextInput.finishAutofillContext();               // shouldSave defaults to true
// on cancel or failure: TextInput.finishAutofillContext(shouldSave: false)
```

- Use `newPassword` on sign-up, change-password and the confirmation field.
  It triggers strong-password suggestions on iOS, and users with generated
  passwords choose better ones.
- Don't put account hints on **third-party** credentials (SMTP passwords, Wi-Fi
  keys, a customer's portal password typed by an admin). The manager would
  offer, or save over, the user's own login. The checker skips fields whose
  context names a third party (`smtp`, `gateway`, `contact`, `client`, `wifi`
  and similar).
- Other useful hints: `oneTimeCode`, `telephoneNumber`, `postalCode`,
  `streetAddressLine1`, `creditCardNumber`, `creditCardExpirationDate`,
  `creditCardSecurityCode`, `name`, `givenName`, `familyName`.
- iOS also needs Associated Domains (`webcredentials:`) for the app to share
  credentials with its website. That's platform setup, outside the form.

## 3. One-time codes (OTP)

```dart
TextFormField(
  controller: _code,
  keyboardType: TextInputType.number,
  autofillHints: const [AutofillHints.oneTimeCode],    // iOS: suggests the code from SMS/Mail
  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
  enableSuggestions: false,
  autocorrect: false,
  textInputAction: TextInputAction.done,
  onChanged: (v) { if (v.length == 6) _verify(); },   // auto-submit, guarded against double submit
  decoration: InputDecoration(labelText: l10n.verificationCode),
)
```

- **Prefer one field over six boxes.** iOS autofill and paste fill a single
  field. Split boxes need hand-written paste handling and focus juggling, and
  they confuse screen readers. If the design insists on boxes, draw them over
  one hidden field, or use a maintained package.
- Android SMS autofill needs the SMS Retriever or User Consent API (a plugin
  such as `smart_auth`). The OTP message has to carry the app hash for the
  Retriever.
- Expire codes and rate-limit attempts **on the server**. A client-side
  attempt counter is UX, not protection.
- Never log the code or send it to analytics. Not even "debug" logs.
- Auto-submit at full length once, then disable the field and button while
  verifying.

## 4. Never log or report field values

What the user types is personal data at best and a credential at worst.
`print` and `debugPrint` both reach the device log in release builds on
Android (`adb logcat`), and analytics and crash reports leave the device.

| Don't | Do |
|---|---|
| `print('login ${_password.text}')` | `log('login submitted')`, the event without the value |
| `analytics.logEvent(name: 'search', parameters: {'q': query})` | log a category or a length bucket, or nothing |
| `onChanged: (v) => debugPrint(v)` | delete it before committing |
| `FirebaseCrashlytics.instance.setCustomKey('email', email)` | a pseudonymous user ID set at sign-in |
| `Sentry.addBreadcrumb(Breadcrumb(message: 'typed $value'))` | breadcrumb the action (`'tapped submit'`) |
| `throw FormatException('bad input: $input')` | `FormatException('bad input')`, so the value doesn't end up in a crash report |
| logging `formKey.currentState!.value` (flutter_form_builder) or `form.value` (reactive_forms) | log which fields failed validation, not their values |

The checker reports these as FORM-004: High for secrets and one-time codes,
Medium for other fields, one level lower inside `if (kDebugMode)`, which is
still a leak on a developer device and in screen recordings of bug reports.
Logging policy for tokens and other non-form data belongs to
`flutter-secure-defaults`.

## 5. Clipboard and paste

- **Don't block paste into password fields** (`enableInteractiveSelection:
  false` or a custom `contextMenuBuilder` that removes Paste). It breaks
  password managers and pushes users to weaker passwords. NIST SP 800-63B says
  verifiers SHOULD allow paste (`FORM-paste-blocked`).
- Copying *out* of an obscured field is already impossible.
- Avoid "copy" buttons for secrets. Flutter's `Clipboard.setData` can't mark
  content as sensitive (flutter#105677), so Android 13+ shows it in the
  clipboard preview and other apps can read it. If a copy button is a product
  requirement (recovery codes, API keys), clear the clipboard after a timeout
  and say so in the UI. The `flutter-security-audit` skill reports this as
  STO-CLIPBOARD; don't duplicate it.

## 6. Client validation is UX; the server decides

- Every rule the client checks (length, format, ranges, "amount ≤ balance",
  required fields), the server checks again. Hidden or disabled fields can be
  edited by anyone with a proxy (`FORM-client-only-validation` if a security
  decision depends only on the client).
- Don't send fields the user can't edit (role, price, user ID) and trust them
  on the server. Derive them server-side.
- For payments and other non-idempotent submits, send an idempotency key
  generated once per form instance. Then a double submit that slips past the
  UI guard is still harmless.
- Rate-limit login, OTP, password-reset and availability checks on the server.
  The client's disabled button isn't a rate limit.

## 7. Keyboard types and actions

| Field | `keyboardType` | `autofillHints` | Other |
|---|---|---|---|
| email | `TextInputType.emailAddress` | `email` (+`username` on login) | `autocorrect: false`, `textCapitalization: none` |
| phone | `TextInputType.phone` | `telephoneNumber` | |
| integer code / PIN | `TextInputType.number` | `oneTimeCode` for OTP | `digitsOnly` |
| decimal amount | `TextInputType.numberWithOptions(decimal: true)` | | locale-aware parsing |
| URL | `TextInputType.url` | `url` | `autocorrect: false` |
| name | `TextInputType.name` | `name` / `givenName` / `familyName` | `textCapitalization: TextCapitalization.words` |
| multi-line | `TextInputType.multiline` | | `maxLines: null`, `textInputAction: TextInputAction.newline` |

The wrong keyboard is a UX bug, not a security bug (FORM-007, Low), but it's
the most visible sign of a form nobody tested on a phone.

Give every field a `textInputAction`: `next` on all but the last field, which
moves focus in traversal order, and `done` (or `go` / `send`) on the last one,
with `onFieldSubmitted` calling the same guarded submit as the button.

## 8. Accessibility

- **Every field has a visible label** (`labelText` or `label`), not just a
  `hintText`. The hint disappears when the user types, and screen readers
  announce the label as the field's name (`FORM-missing-label`).
- **Icon-only suffixes need a tooltip or semantic label**: the show-password
  toggle gets `tooltip: _hidden ? l10n.showPassword : l10n.hidePassword`.
- **Errors are announced.** `errorText` joins the field's semantics, so it's
  read when focused. After a failed submit, focus the first invalid field
  (`validation-patterns.md` §2). For a form-level error banner, wrap it in
  `Semantics(liveRegion: true, child: …)` so it's announced when it appears.
- **Focus order follows the visual order.** Use a `Column` in reading order,
  `FocusTraversalGroup` around logical sections, and `OrderedTraversalPolicy`
  with `FocusTraversalOrder` only when the layout really differs from the
  reading order (two-column forms on tablets).
- **Text scale.** Fields must survive a 200 % text scale: no fixed-height
  `SizedBox` or `Container` around a `TextField`, no fixed-width rows of
  fields. Use `Wrap` or `LayoutBuilder` for side-by-side fields. Test with
  `MediaQuery(data: …copyWith(textScaler: TextScaler.linear(2)))` in a widget
  test.
- **Tap targets** ≥48×48 dp, including the visibility toggle and checkboxes.
- **Required fields:** mark them in the label text ("Email (required)"), not
  by colour alone.
- Don't disable the submit button **silently** while the form is invalid.
  Users (and screen readers) can't tell why. Prefer an enabled button that
  validates and focuses the first error. Disabling *while submitting* is
  different: show a progress indicator with a semantic label.

## 9. A secure field template

```dart
class NewPasswordField extends StatefulWidget {
  const NewPasswordField({super.key, required this.controller, this.onSubmitted});

  final TextEditingController controller;          // owned by the parent State; not disposed here
  final ValueChanged<String>? onSubmitted;

  @override
  State<NewPasswordField> createState() => _NewPasswordFieldState();
}

class _NewPasswordFieldState extends State<NewPasswordField> {
  bool _hidden = true;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return TextFormField(
      controller: widget.controller,
      obscureText: _hidden,
      enableSuggestions: false,
      autocorrect: false,
      enableIMEPersonalizedLearning: false,
      keyboardType: _hidden ? TextInputType.text : TextInputType.visiblePassword,
      autofillHints: const [AutofillHints.newPassword],
      maxLength: 128,
      textInputAction: TextInputAction.done,
      onFieldSubmitted: widget.onSubmitted,
      validator: (v) => passwordMessage(validateNewPassword(v ?? ''), l10n),   // never echo the value
      decoration: InputDecoration(
        labelText: l10n.newPassword,
        counterText: '',
        suffixIcon: IconButton(
          tooltip: _hidden ? l10n.showPassword : l10n.hidePassword,
          icon: Icon(_hidden ? Icons.visibility : Icons.visibility_off),
          onPressed: () => setState(() => _hidden = !_hidden),
        ),
      ),
    );
  }
}
```
