# flutter-forms: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

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
