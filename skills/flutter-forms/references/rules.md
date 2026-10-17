# FORM rules: what the checker reports, and why

`scripts/check_forms.py` is static and read-only. It needs only the Python
standard library and no `pub get`. Every hit is a candidate: read the code
before you call a finding `confirmed`. Each rule below lists the false
positives it knows about. These were calibrated on immich (mobile),
Invoice Ninja (admin-portal), the bloclibrary examples (`flutter_login`,
`flutter_firebase_login`, `flutter_form_validation`), flutter/samples
(`compass_app`, `form_app`, `navigation_and_routing`, `platform_design`),
flutter_ui_challenges and flutter_twitter_clone.

## Contents

1. How fields are recognised
2. FORM-001 … FORM-008
3. Reading-level findings (FORM-<slug>)
4. What this skill deliberately doesn't check (and who does)

## 1. How fields are recognised

**Fields** are calls to `TextField`, `TextFormField`, `CupertinoTextField`,
`CupertinoTextFormFieldRow`, `FormBuilderTextField` and `ReactiveTextField`.
**Wrappers** count too: a project widget (or its `State`) that builds one of
those and declares an `obscureText` or `keyboardType` parameter. A rule only
applies to a wrapper call when the wrapper exposes the parameter the rule needs.
For example, FORM-003 is skipped for a wrapper without `autofillHints`, since
the fix then belongs inside the wrapper. The text report lists the wrappers it
found.

A field's **kind** comes from the first source that decides it, in this
order: `autofillHints`, a plain `keyboardType` value, the controller's name,
the label/hint/placeholder text (including l10n keys such as
`l10n.passwordLabel`), `key`/`name`/`formControlName`, the validator, the
callbacks, and finally the name of a `…Field`/`…Input` widget or helper that
encloses it.

| Kind | Tokens |
|---|---|
| otp | otp, totp, mfa, 2fa, "one time", "verification code", "sms code", "security code"; a `pin` field in an `otp`/`verification` screen |
| password | password, passwd, pwd, passphrase, pass |
| pin | pin, pincode, passcode, mpin |
| cvv | cvv, cvc, cvn, csc |
| secret | secret, mnemonic, "api key", "private key", "access token", "seed/recovery phrase" |
| email / phone | email, mail / phone, mobile, telephone, tel, msisdn, unless the same source also says user/name/server/code/template/… |

Sources with words like *hint, length, policy, strength, expiry, minimum,
question, search, filter, template, show, visible* stop the search: "Password
hint" and "Password minimum length" aren't secret fields.

## 2. Rules

### FORM-001 secret-field-not-obscured

**Medium** (Low for `secret` kind: API keys, tokens) · all profiles

**Detects:** a password/PIN/CVV/secret field with no `obscureText`, or with
`obscureText: false`. A variable or toggle (`obscureText: _hidden`) counts as
obscured. `readOnly: true` / `enabled: false` fields are skipped.
**Why:** the value is readable over the shoulder, in screen recordings and in
screenshots, and it can be copied out of the field.
**Fix:** `obscureText: true`, or a toggle that starts hidden (`secure-inputs.md` §1).
**False positives:** a deliberately visible "set a link password" field
(immich's shared-link editor: suppress it with a reason, or add a toggle); an
API key shown in clear text in an admin console (that's why it's only Low).

### FORM-002 secret-field-keyboard-learning

**Low** · all profiles

**Detects:** a secret field whose `obscureText` isn't the literal `true` (so it
can become visible) and that lacks `enableSuggestions: false` or
`autocorrect: false`. Skipped for number, phone and `visiblePassword`
keyboards, which don't learn words.
**Why:** obscured fields get password treatment from the platform. A visible
one is ordinary text: suggestions appear, and the keyboard may learn the
secret.
**Fix:** add `enableSuggestions: false, autocorrect: false` (and
`enableIMEPersonalizedLearning: false`).
**False positives:** none known. Fields whose `obscureText` is always `true`
aren't flagged, because the platform already disables suggestions.

### FORM-003 credential-field-missing-autofill

**Low** · all profiles

**Detects:** an obscured password field, or a one-time-code field, with no
`autofillHints` argument. One report per screen for split code boxes. Boxes
with `maxLength: 1` are skipped.
**Why:** without hints, password managers and iOS's SMS code autofill can't
help, and users pick weaker passwords.
**Fix:** `autofillHints: const [AutofillHints.password]` (`newPassword` on
sign-up, change and confirm fields; `oneTimeCode` for OTP) inside an
`AutofillGroup`, plus `TextInput.finishAutofillContext()` after success.
**False positives:** third-party credentials. Calibration found SMTP passwords
and payment-gateway secrets in Invoice Ninja, and a customer's portal password
set by an admin. The rule now skips fields whose call, file path or enclosing
class mentions `smtp, imap, gateway, contact, client, vendor, wifi, proxy,
database, certificate, share, link` and similar. If a third-party credential
is still flagged, suppress it with a reason. It also skips unobscured password
fields: FORM-001 already covers those, and a visible "password" is usually not
the user's own login.

### FORM-004 field-value-logged

**High** for secrets and one-time codes, **Medium** otherwise, one level lower
inside `if (kDebugMode)` / `if (!kReleaseMode)` / `assert(() {…}())` · all profiles

**Detects:** `print`, `debugPrint`, `log`, `developer.log`, logger methods
(`logger.i`, `log.info`, `talker.debug`…) and analytics or crash-reporting
calls (`logEvent`, `track`, `setUserProperty`, `setCustomKey`,
`addBreadcrumb`, `captureMessage`, `recordError`) whose arguments contain:
- `<controller>.text`, where the receiver is a declared `TextEditingController`
  or is named `*Controller`/`*Ctrl`. `.text.length`, `.isEmpty` and
  `.isNotEmpty` are allowed;
- the parameter of a field's own `onChanged`/`onSaved`/`onSubmitted`/
  `onFieldSubmitted`/`validator` callback;
- `formKey.currentState!.value` / `.instantValue` (flutter_form_builder) or
  `form.value` / `form.control(…).value` (reactive_forms).

**Why:** see `secure-inputs.md` §4. Release builds on Android print `print`
and `debugPrint` to logcat, and analytics and crash data leave the device.
**Fix:** log the event, not the value.
**False positives:** a QA-only console that echoes input on purpose. Suppress
the whole file with a reason.

### FORM-005 submit-without-busy-guard

**Medium** · all profiles (the note carries the profile's fix)

**Detects:** a `…Button` or `FloatingActionButton` whose `onPressed`/`onTap`
is an `async` closure, an async method tear-off, or `() => _method(args)`
calling an async method in the same class, where:
- the handler awaits real work (not only `Navigator`/`go_router` pushes and
  pops, dialogs, sheets, `launchUrl`, pickers, share, animations), and
- it looks like a submit (`validate()`/`save()` on a form, or a handler or
  awaited callee named submit/save/login/sign-in/sign-up/send/pay/confirm/
  create/update/…), and
- nothing guards it: `onPressed` isn't conditional; the handler doesn't return
  early on a busy flag (`if (_loading) return;`, `state is XSubmitting`,
  `.running`); no busy flag the handler sets is read in a condition outside
  the button; and the enclosing build has no busy condition (`isLoading ?`,
  `if (state is XLoading)`, `IgnorePointer(ignoring: busy)`, a spinner
  swapped in for the button). Buttons with a busy-style parameter
  (`AppButton(isLoading: …)`) are trusted.

A handler that first awaits a dialog (`await showDialog(...)`) is skipped: the
modal covers the button, and a second album or order then needs a second
deliberate pass through the dialog.
**Why:** a double tap submits twice. The second `pop()` can also remove the
screen underneath.
**Fix:** `multi-step-and-dirty-state.md` §1, per pattern.
**Not detected (by design):** synchronous dispatch to logic, such as
`() => bloc.add(Submitted())`, `ref.read(p.notifier).submit()` or
`command.execute()`. There the guard belongs in the logic
(`FORM-double-submit-logic`, a reading-level finding).

### FORM-006 form-never-validated

**Medium** · all profiles

**Detects:** a `GlobalKey<FormState>` (or `FormBuilderState`) used as a
`Form(key:)` in a file that has `validator:` arguments, where no
`<key>.currentState…validate()` / `saveAndValidate()` call exists, the
key's `currentState` isn't aliased, and the key isn't passed to another
widget or constructor.
**Why:** the validators only show errors; the submit goes ahead with invalid
input. Calibration: immich's login form declares URL and email validators that
never gate the submit.
**Fix:** `if (!_formKey.currentState!.validate()) return;` first in the submit.
**False positives:** validation done through `Form.of(context)` in a child
widget defined in another file. Suppress it, or pass the key explicitly.

### FORM-007 input-type-mismatch

**Low** · all profiles

**Detects:** an email or phone field with no `keyboardType`, or with
`TextInputType.text`/`.name`/`.multiline`. Skipped when `keyboardType` is a
conditional expression, for multi-line fields, and for fields whose label
also says user/name/server/template/custom/style/… (calibration:
"Email style (custom)" and "SMTP username" aren't email-address fields).
**Fix:** `TextInputType.emailAddress` / `TextInputType.phone`, plus the
matching `autofillHints`.

### FORM-008 controller-created-inline

**High** · all profiles

**Detects:** `controller: TextEditingController(…)` or `focusNode: FocusNode()`
written inline as an argument, inside any function except `initState`,
`didChangeDependencies`, a constructor or a `create:`/`init:` callback.
**Why:** each rebuild (keyboard opening, theme change, parent `setState`)
creates a new controller. The text resets to the initial value, the cursor
jumps, focus is lost, and nothing is ever disposed.
**Fix:** create it once in `initState` and dispose it in `dispose`, or use
`useTextEditingController()` / `useFocusNode()` with flutter_hooks, or use
`initialValue:` when you only need a starting value.
**Not duplicated:** an undisposed `_c = TextEditingController()` *field* is the
`undisposed-resource` heuristic (`dart-flutter-review`) and `UI-lifecycle`
(`flutter-ui-practices`). A controller held in a provider or notifier is
ARCH-109. FORM-008 only reports the inline-argument form, which neither of
those sees.

## 3. Reading-level findings

| ID | Severity | Look for |
|---|---|---|
| `FORM-validation-in-widget` | Medium | business rules (uniqueness, account limits, rules across entities) inside `validator:` closures or `onPressed`, instead of the logic layer. Simple format checks in `validator:` are fine |
| `FORM-client-only-validation` | High | a security or business decision enforced only on the client (amount limits, role fields, hidden or disabled fields trusted by the API) |
| `FORM-double-submit-logic` | Medium | a notifier, bloc or view-model submit with no busy guard (no `droppable()`, no `state is Submitting` check, no Command) when the UI can call it more than once |
| `FORM-pii-in-error` | Medium | error text that echoes the entered value or a raw server message (compare ERR-008) |
| `FORM-enumeration` | Medium | login or reset messages that reveal whether an account exists |
| `FORM-secret-persisted` | High | passwords, PINs, CVVs or OTPs in `restorationId` fields, HydratedBloc `toJson`, drafts or `shared_preferences` |
| `FORM-untrimmed-input` | Low | values sent without `trim()` or without lower-casing emails (but never trim passwords) |
| `FORM-unbounded-input` | Low | free-text fields that reach the server with no `maxLength` or `LengthLimitingTextInputFormatter` |
| `FORM-paste-blocked` | Low | paste disabled on password fields (`enableInteractiveSelection: false`, a context menu without Paste) |
| `FORM-missing-label` | Medium | fields with only a `hintText`, or icon-only suffix buttons without a tooltip |
| `FORM-focus-order` | Low | no `textInputAction`/`onFieldSubmitted` chain; focus order that differs from the visual order; the first invalid field not focused after submit |
| `FORM-autovalidate-always` | Low | `AutovalidateMode.always` showing errors before any input |
| `FORM-silent-disabled-submit` | Low | a submit button disabled while the form is invalid, with no explanation |
| `FORM-text-scale` | Low | fixed heights or widths around fields that clip at 200 % text scale |
| `FORM-lost-input-on-step` | Medium | multi-step flows that recreate controllers per step, so going back loses input |
| `FORM-unsaved-changes-unguarded` | Low | an editable form with a dirty state and no `PopScope` / route `onExit` guard; or a guard that fires when nothing changed |
| `FORM-split-otp-boxes` | Low | one-character OTP boxes without paste support (prefer one field with `oneTimeCode`) |

## 4. Not checked here (cross-references)

| Concern | Owner |
|---|---|
| undisposed `TextEditingController`/`FocusNode` fields | `flutter-ui-practices` (`UI-lifecycle`), `dart-flutter-review` heuristic `undisposed-resource` |
| controllers or form state in a provider/notifier | `flutter-architecture` ARCH-109 |
| `context` used after `await` in a submit handler | `use_build_context_synchronously` lint, `UI-context-after-await` |
| navigation from a notifier/bloc after submit | ARCH-102, `AP-navigation-in-logic` |
| `isLoading` + `error` + `data` flags that contradict each other | `AP-boolean-soup-state` |
| raw `e.toString()` shown to the user | ERR-008 (`flutter-error-handling`) |
| secrets copied to the clipboard | STO-CLIPBOARD (`flutter-security-audit`) |
| tokens and credentials in storage and logs (outside form fields) | `flutter-secure-defaults` (SEC-) |
| localized error messages, RTL fields | `flutter-i18n` |
