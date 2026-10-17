---
name: flutter-forms
description: Write and review Flutter forms that are clean and secure by default, placed by the app's own architecture. Covers Form/TextFormField, validators (sync, async with debounce, cross-field, server errors mapped to fields), controllers and FocusNodes, focus traversal, input formatters and masks, double-submit guards, multi-step forms, unsaved-changes guards, and form state in MVN, MVVM, Bloc/Cubit, Provider and GetX. Also secures inputs with obscureText, autofill for passwords and one-time codes, length limits, trimming, no field values in logs or analytics, and server-side validation. Use it whenever you build, fix or review a login, sign-up, OTP, checkout or settings form or any TextField, when a password or field value shows up in logs, or someone says "validation", "validator", "form", "double submit" or "unsaved changes", even if they never say "forms". Load it before editing the form.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.4.0"
  suite: flutter-pro-skills
---

# Flutter forms

Forms are where users hand the app their passwords, card numbers and personal
details, and where most "it submitted twice", "my text disappeared" and "the
error never showed" bugs live. This skill writes forms that are correct for
the architecture the project already uses, and safe without a later
hardening pass.

The core split holds in every pattern:

- **Field plumbing stays in the widget.** `TextEditingController`,
  `FocusNode`, `GlobalKey<FormState>` and the show-password toggle are
  ephemeral UI state. riverpod.dev says to avoid providers for form state and
  anything with a controller (ARCH-109).
- **Rules are pure functions or value objects.** The widget's `validator:`
  calls them for format checks. The logic layer calls them for cross-field,
  async and submit-time checks.
- **Submission goes in the logic holder**: the notifier, view model, bloc or
  controller, which calls the use case or repository.
- **Form status is one value**: a sealed state, a status enum or a `Command`,
  never `isLoading` plus `error` booleans.
- **The server validates again.** Client validation is UX, not security.

## Workflow

### 1. Detect the architecture and the form style

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern or form package (`formz`, `flutter_form_builder`,
`reactive_forms`). A declared convention wins. Then run the checker. It is
read-only, uses only the Python standard library, and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_forms.py <project-root>                   # text report
python3 -I <skill-dir>/scripts/check_forms.py <project-root> --json            # schema flutter-pro-skills/forms@1
python3 -I <skill-dir>/scripts/check_forms.py <project-root> --files changed.txt   # diff review
python3 -I <skill-dir>/scripts/check_forms.py <project-root> --profile bloc    # declared pattern wins
```

The CLI is `check_forms.py <project-root> [--json] [--files <list-file-or-comma-list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
It exits `0` whenever a report is produced and `2` on a usage error. It reads
the profile and file roles from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`). If that sibling is
missing, it falls back to path-based detection and says so on the
`classification:` line.

```text
== FORMS
  profile: mvn (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 142 files, 31 fields (6 secret, 1 one-time-code, 7 email/phone), 9 forms, 4 async submit buttons
  field wrappers: AppTextField
  [FORM-004] field-value-logged (high) x1 — A field value (...) is sent to print/log/analytics/crash reporting. ...
      lib/features/auth/presentation/view/login_view.dart:26  print('login with ${_passwordController.text}')   [`_passwordController.text` (password field)]
```

### 2. Place each piece by the pattern

| Piece | MVN | MVVM + Command | Bloc / Cubit | Provider | GetX |
|---|---|---|---|---|---|
| controllers, focus nodes, form key | `ConsumerStatefulWidget` state (or hooks) | view `State` | view `State`, or none with formz inputs | view `State` | the `GetxController` (dispose in `onClose`) |
| draft values | passed to `notifier.submit(draft)` or held in the sealed state | view-model fields / command argument | bloc state (`FormzInput`s) or the submit event | model fields | controller fields |
| cross-field and async rules | notifier (debounced, use case) | view model | bloc handlers / `Formz.validate` | model | controller |
| submission | notifier → use case | `Command1.execute` → repository | `on<Submitted>(…, transformer: droppable())` | model method | controller method |
| form status | sealed `XEditing / XSubmitting / XDone / XFailed` | `command.running / error / completed` | `FormzSubmissionStatus` / status enum | status enum | `Rx<FormStatus>` / `RxBool` |
| one-time effects | `ref.listen` | command listener | `BlocListener` | listener on the model | `ever()` / worker |

Read `references/placement-by-architecture.md` for complete code per pattern
(and setState). Read `references/validation-patterns.md` for validators,
async checks and server errors. Read `references/secure-inputs.md` before
writing any credential, payment or OTP field. Read
`references/multi-step-and-dirty-state.md` for wizards, submit sequencing and
unsaved-changes guards.

### 3. Write with the checklist below, then run the checker

Read the code behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and its known false
positives. Suppress a deliberate case in the code, with a reason:
`// form-ignore: FORM-001 the owner must read the share-link password back`
(on the reported line, the line above, or anywhere inside the field's call)
or `// form-ignore-file: FORM-004 <reason>`.

## WRITE checklist

**Structure**
1. Create controllers and focus nodes in `initState` (or with
   `useTextEditingController` / `useFocusNode`), dispose them in `dispose`,
   and never construct them inline in `build` (FORM-008). Disposal itself is
   covered by `flutter-ui-practices` §1.
2. Keep the rules out of the widget: pure validator functions or value
   objects returning **typed errors**. The view maps them to localized text.
3. Run submission in the logic holder. The widget validates, then forwards a
   draft: `if (!_formKey.currentState!.validate()) return;` (FORM-006).
4. Model status as one sealed state, status enum or command.
5. Guard submit twice: disable the button while busy (FORM-005), and return
   early in the logic while busy (`droppable()`, `state is XSubmitting`,
   `Command`).
6. Map server field errors to fields: the repository turns a 422 into
   `ValidationFailure(fieldErrors)`, the field shows it, and the error clears
   when the user edits that field.

**Secure by default**
7. Secret fields (password, PIN, CVV, API key): `obscureText: true` or a
   toggle that starts hidden (FORM-001). With a toggle, also set
   `enableSuggestions: false, autocorrect: false` and
   `enableIMEPersonalizedLearning: false` (FORM-002).
8. Credentials: `AutofillGroup`, `autofillHints` (`password`, `newPassword`,
   `username`/`email`, `oneTimeCode`), and `TextInput.finishAutofillContext()`
   on success (FORM-003). No account hints on third-party credentials.
9. Never put field values in `print`, `debugPrint`, `log`, analytics, crash
   keys or breadcrumbs (FORM-004). Log the event, not the input.
10. `trim()` and normalise every value before validating and sending (lower-case
    emails, E.164 phones), except passwords. Limit lengths with `maxLength` or
    `LengthLimitingTextInputFormatter` to match the server.
11. Error text never echoes the input, never shows a raw server message, and
    doesn't reveal whether an account exists.
12. OTP: one field, `TextInputType.number`, `digitsOnly`, length-limited,
    `AutofillHints.oneTimeCode`, and not obscured. The server expires codes and
    rate-limits attempts.
13. Don't block paste into password fields. Avoid copy buttons for secrets
    (`flutter-security-audit` STO-CLIPBOARD).
14. Never persist secrets in restoration data, HydratedBloc JSON, drafts or
    preferences.
15. Treat client validation as UX: every rule is checked again on the server,
    and non-idempotent submits carry an idempotency key.

**Keyboard, focus and accessibility**
16. Pick the right `keyboardType` (emailAddress, phone, number, url, name,
    multiline) (FORM-007), and a `textInputAction` on every field: `next` to
    advance, `done` to submit through the same guarded handler.
17. Give every field a visible `labelText` (not just a hint), and every icon
    button a `tooltip`.
18. After a failed submit, focus the first invalid field
    (`validateGranularly()`), and switch to
    `AutovalidateMode.onUserInteraction`. Avoid `AutovalidateMode.always`.
19. Fields survive a 200 % text scale: no fixed heights around them.
20. Guard unsaved changes with `PopScope` only when the values differ from
    the initial ones.

## REVIEW checklist

Script rules (`FORM-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| FORM-001 | secret-field-not-obscured | Medium (Low for API keys/tokens) | password/PIN/CVV/secret field without `obscureText` |
| FORM-002 | secret-field-keyboard-learning | Low | toggleable secret field without `enableSuggestions: false` / `autocorrect: false` |
| FORM-003 | credential-field-missing-autofill | Low | obscured password or OTP field without `autofillHints` |
| FORM-004 | field-value-logged | High for secrets/OTP, Medium otherwise (one lower under `kDebugMode`) | `controller.text`, callback values or form-state values in print/log/analytics/crash calls |
| FORM-005 | submit-without-busy-guard | Medium | an async submit from a button that stays enabled while in flight |
| FORM-006 | form-never-validated | Medium | a `GlobalKey<FormState>` with validators that nothing `validate()`s |
| FORM-007 | input-type-mismatch | Low | email or phone field on the default text keyboard |
| FORM-008 | controller-created-inline | High | `controller: TextEditingController(…)` / `focusNode: FocusNode()` as an inline argument |

Reading-level findings (`FORM-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| FORM-client-only-validation | High | a security or business rule enforced only on the client |
| FORM-secret-persisted | High | secrets in restoration data, HydratedBloc, drafts or preferences |
| FORM-validation-in-widget | Medium | business rules in `validator:` or `onPressed` instead of logic |
| FORM-double-submit-logic | Medium | a logic-layer submit that accepts a second call while busy |
| FORM-pii-in-error | Medium | errors echoing input or raw server text (compare ERR-008) |
| FORM-enumeration | Medium | messages that reveal whether an account exists |
| FORM-missing-label | Medium | hint-only fields, icon buttons without tooltips |
| FORM-lost-input-on-step | Medium | multi-step flows that lose input on Back |
| FORM-unsaved-changes-unguarded | Low | dirty editable form with no `PopScope`/`onExit` guard, or a guard that fires when clean |
| FORM-untrimmed-input / FORM-unbounded-input | Low | values sent untrimmed; no length limit on server-bound text |
| FORM-paste-blocked | Low | paste disabled on password fields |
| FORM-focus-order / FORM-autovalidate-always / FORM-text-scale / FORM-silent-disabled-submit / FORM-split-otp-boxes | Low | see `references/rules.md` §3 |

**Don't report here (cross-reference instead):**
- undisposed controller fields: `UI-lifecycle` / the `undisposed-resource`
  heuristic
- controllers or form state in a provider: ARCH-109
- `context` after `await` in a submit: `UI-context-after-await`
- navigation from logic after submit: ARCH-102
- `isLoading`/`error` flag pairs: `AP-boolean-soup-state`
- `e.toString()` in the UI: ERR-008
- secrets on the clipboard: STO-CLIPBOARD

**When not to flag:**
- formz-style Bloc forms with no controllers at all: that's the bloclibrary
  pattern.
- GetX controllers owning `TextEditingController`s, when disposed in `onClose`.
- Inline format validators in `validator:`: the Flutter cookbook does this.
- `obscureText` missing on OTP, username or email fields.
- A button that dispatches synchronously to a bloc, notifier or command. The
  guard then belongs in the logic (`FORM-double-submit-logic`), not FORM-005.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] Password typed into the login form is printed to the device log
- id: FORM-004
- where: lib/features/auth/presentation/view/login_view.dart:26
- evidence: `print('login with ${_passwordController.text}')`
- rule: never log or report field values (flutter-forms › secure-inputs.md §4)
- why: Android prints `print` to logcat in release builds; anyone with adb, or any bug-report log capture, reads the password
- fix: |
    log('login submitted');   // the event, never the value
- confidence: confirmed

### [MEDIUM] Sign-in button can submit twice
- id: FORM-005
- where: lib/features/auth/presentation/view/login_view.dart:45
- evidence: `ElevatedButton(onPressed: _submit)`; `_submit` awaits `loginProvider.notifier.submit(...)` with no busy check
- rule: MVN: the sealed state carries the busy status; the view disables the button (multi-step-and-dirty-state.md §1)
- why: a double tap sends two sign-in requests and can pop the route twice
- fix: |
    onPressed: state is LoginSubmitting ? null : _submit,
    // and in the notifier: if (state is LoginSubmitting) return;
- confidence: confirmed
```

Open the report with one line naming the profile and the form style (`mvn,
controllers in views, no form package`). Report a pattern-wide issue (for
example, no field anywhere has autofill hints) **once**, with a few
locations.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern, ARCH-109 and the
  layer rules. Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-ui-practices`** for controller lifecycle, `context.mounted`
  after `await`, and accessibility basics. Fallback:
  `../flutter-ui-practices/references/flutter-ui.md`.
- **`flutter-error-handling`** for mapping submit failures to typed errors
  and user-safe messages (ERR-008). Fallback: `../flutter-error-handling/SKILL.md`.
- **`flutter-secure-defaults`** for token storage, logging policy and
  input validation at other boundaries. **`flutter-security-audit`** for deep
  audits (clipboard, screenshots, RASP). Fallbacks:
  `../flutter-secure-defaults/SKILL.md`; the audit skill is installed
  separately.
- **`flutter-navigation`** for route `onExit` guards and post-submit
  navigation. **`flutter-i18n`** for localized error text.
- **`flutter-testing`** for widget tests of forms, fakes and `bloc_test`.
- **`dart-flutter-review`** merges FORM findings into its report.

## References

| File | Read it when |
|---|---|
| `references/placement-by-architecture.md` | deciding where controllers, drafts, rules, submission and status go in MVN, MVVM+Command, Bloc/Cubit, Provider, GetX or setState |
| `references/validation-patterns.md` | writing sync, cross-field or debounced async validators, mapping server errors to fields, normalising input, formatters and masks |
| `references/secure-inputs.md` | writing password, PIN, CVV, API-key or OTP fields; autofill; logging; clipboard; keyboard types; accessibility |
| `references/multi-step-and-dirty-state.md` | submit sequencing and double-submit per pattern, wizards and steppers, dirty state and `PopScope`, drafts and restoration |
| `references/rules.md` | every FORM rule: detection, why, fix, false positives; the reading-level slugs; what's checked elsewhere |
