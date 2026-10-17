# Validation patterns

Client-side validation is **UX**: it tells the user early, in their language,
what to fix. It isn't security. Anyone can call the API without the app, so
the server validates everything again, and the app has to handle the server
saying no (§5). Write each rule once, as a pure function or value object, and
call it from wherever it's needed.

## Contents

1. Sync field validators
2. When to validate (autovalidate modes) and focusing the first error
3. Cross-field validation
4. Async validation with debounce
5. Server errors mapped to fields
6. Normalising input: trim, case, length, formatters and masks
7. Error text: localized, specific, no PII
8. Testing validators

## 1. Sync field validators

A `FormFieldValidator<String>` is synchronous and runs on every `validate()`
call, and on every rebuild when autovalidation is on. Keep it cheap. Don't
allocate `RegExp`s in it (make them `static final`), and do no I/O.

```dart
// core/validation/validators.dart: pure, unit-tested, l10n-free
typedef Rule<E> = E? Function(String value);

enum TextError { required, tooShort, tooLong, malformed }

Rule<TextError> requiredText({int min = 1, int max = 200}) => (v) {
      final t = v.trim();
      if (t.isEmpty) return TextError.required;
      if (t.length < min) return TextError.tooShort;
      if (t.length > max) return TextError.tooLong;
      return null;
    };

// view: translate the typed error where BuildContext lives
TextFormField(
  controller: _name,
  maxLength: 200,
  validator: (v) => switch (requiredText(min: 2)(v ?? '')) {
    TextError.required => l10n.errorRequired,
    TextError.tooShort => l10n.errorTooShort(2),
    TextError.tooLong => l10n.errorTooLong(200),
    TextError.malformed => l10n.errorMalformed,
    null => null,
  },
)
```

Inline format checks like this are fine in the widget: the Flutter forms
cookbook does exactly that. What doesn't belong in a `validator:` closure is
**business** validation (uniqueness, limits that depend on the account,
rules spanning entities). Put that in the logic layer (`FORM-validation-in-widget`).

## 2. When to validate

| `autovalidateMode` | Behaviour | Use for |
|---|---|---|
| `disabled` (default) | only when you call `validate()` | most forms: validate on submit, then switch to `onUserInteraction` |
| `onUserInteraction` | after the field has changed | re-validating after a failed submit; long forms |
| `onUnfocus` (newer Flutter) | when the field loses focus | avoiding errors while the user is still typing |
| `always` | from the first frame | almost never: it shows errors before the user has typed anything (`FORM-autovalidate-always`) |

A common, polite pattern is to start at `disabled`, and after the first failed
submit set `_autovalidate = AutovalidateMode.onUserInteraction` on the `Form`.

After a failed submit, move focus to the first invalid field, so that
screen-reader and keyboard users land on the problem. On Flutter 3.16+,
`FormState.validateGranularly()` returns the failing fields:

```dart
void _submit() {
  final invalid = _formKey.currentState!.validateGranularly();
  if (invalid.isNotEmpty) {
    setState(() => _autovalidate = AutovalidateMode.onUserInteraction);
    _focusFor[invalid.first.widget.key]?.requestFocus();   // or keep a list of FocusNodes in field order
    return;
  }
  // ...hand the draft to the logic holder
}
```

## 3. Cross-field validation

"Confirm password matches", "end after start" and "at least one contact
method" need two values. Write the rule over the whole draft:

```dart
@immutable
final class PasswordChangeDraft {
  const PasswordChangeDraft({required this.current, required this.next, required this.confirm});
  final String current, next, confirm;

  Map<PasswordField, PasswordError> validate() => {
        if (next.length < 12) PasswordField.next: PasswordError.tooShort,
        if (next == current) PasswordField.next: PasswordError.sameAsCurrent,
        if (confirm != next) PasswordField.confirm: PasswordError.mismatch,
      };
}
```

- **In the widget**, a `validator:` may read a sibling controller
  (`(v) => v != _next.text ? l10n.mismatch : null`). Re-run it when the other
  field changes: call `_confirmKey.currentState?.validate()` from the first
  field's `onChanged`, or validate the whole form.
- **In logic** (bloc/notifier), compute errors from the draft whenever any
  field changes. formz's `Formz.validate([...])` covers single inputs, so add
  the cross-field rule in the bloc.
- Report the error on the field the user should change (the confirmation),
  not on both.

## 4. Async validation with debounce

"Username taken", "promo code valid" and "postcode exists" need the network.
`FormFieldValidator` can't be async. So keep the async check in the logic
holder, debounce it, discard stale answers, and let the sync validator read
the cached result.

```dart
// MVN notifier (the same shape works in a Cubit or a view model)
@riverpod
class UsernameCheck extends _$UsernameCheck {
  Timer? _debounce;
  int _seq = 0;

  @override
  UsernameStatus build() {
    ref.onDispose(() => _debounce?.cancel());
    return const UsernameUnchecked();
  }

  void changed(String raw) {
    final name = raw.trim().toLowerCase();
    _debounce?.cancel();
    if (validateUsernameFormat(name) != null) {
      state = const UsernameUnchecked();             // the sync validator shows the format error
      return;
    }
    state = const UsernameChecking();
    final seq = ++_seq;
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      try {
        final free = await ref.read(checkUsernameUseCaseProvider)(name);
        if (seq != _seq) return;                     // a newer keystroke won
        state = free ? const UsernameFree() : const UsernameTaken();
      } on Failure {
        if (seq == _seq) state = const UsernameUnknown();   // don't block the form on a flaky check
      }
    });
  }
}

// view
TextFormField(
  controller: _username,
  onChanged: ref.read(usernameCheckProvider.notifier).changed,
  validator: (v) =>
      usernameFormatMessage(v, l10n) ??
      (ref.read(usernameCheckProvider) is UsernameTaken ? l10n.usernameTaken : null),
  decoration: InputDecoration(
    labelText: l10n.username,
    suffixIcon: switch (ref.watch(usernameCheckProvider)) {
      UsernameChecking() => const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2)),
      UsernameFree() => Icon(Icons.check, semanticLabel: l10n.usernameAvailable),
      _ => null,
    },
  ),
)
```

Rules:
- Debounce for 300–500 ms, and drop stale responses (a sequence number or a
  cancel token).
- An "unknown" result (offline, timeout) must not block submission. The
  server decides at submit time anyway.
- Don't run async checks on secrets (passwords against a breach API go through
  the server, using k-anonymity, not from the client).
- Availability endpoints leak which accounts exist (enumeration). The server
  should rate-limit them. Consider checking only at submit.

## 5. Server errors mapped to fields

The server is the authority. When it rejects a submit with field errors (HTTP
400/422 with a body like `{"errors": {"email": "taken"}}`), map them in the
**repository** to a typed failure that carries field keys and error codes,
never raw server text. Then show them on the fields.

```dart
// data: map transport → domain (see flutter-error-handling for the full flow)
on DioException catch (e) {
  if (e.response?.statusCode == 422) {
    final raw = (e.response!.data as Map)['errors'] as Map? ?? const {};
    throw ValidationFailure({
      for (final MapEntry(:key, :value) in raw.entries)
        if (SignUpField.fromApi(key as String) case final field?) field: FieldError.fromCode('$value'),
    });
  }
  rethrow;
}
```

```dart
// view: show the server error until the user edits that field
TextFormField(
  controller: _email,
  onChanged: (_) => ref.read(signUpProvider.notifier).clearFieldError(SignUpField.email),
  forceErrorText: serverErrors[SignUpField.email]?.message(l10n), // newer Flutter; else decoration.errorText
  validator: (v) => emailMessage(validateEmail(v ?? ''), l10n),
)
```

- Clear a server error as soon as the user edits that field. Otherwise it
  sticks around after they've fixed it.
- Show errors for unknown keys, or form-level errors, above the submit button.
- Focus the first field with a server error, as in §2.
- Don't display the server's message verbatim. It may echo the submitted
  value, internal IDs or English-only text (`FORM-pii-in-error`; compare
  ERR-008 in `flutter-error-handling`).

## 6. Normalising input

| Concern | Do |
|---|---|
| Whitespace | `trim()` every text value before validating and before sending. Never trim passwords: spaces are valid characters |
| Case | lower-case emails for comparison and sending (the local part is technically case-sensitive, but no real provider treats it that way) |
| Unicode | normalise (NFC) usernames on the **server**. The client can't do it reliably with the standard library |
| Length | set `maxLength` (with `counterText: ''` if you hide the counter) or `LengthLimitingTextInputFormatter(n)` on every field that reaches the server: names ≤100, emails ≤254, passwords ≤128 (long enough for passphrases). It stops accidental megabyte pastes and matches the server's limits |
| Digits | `FilteringTextInputFormatter.digitsOnly` plus `keyboardType: TextInputType.number` for codes and amounts. Parse with `int.tryParse` / `num.tryParse`, never `parse` |
| Decimals | use `TextInputType.numberWithOptions(decimal: true)` and accept the locale's separator; parse with `intl`'s `NumberFormat` |
| Phone | `TextInputType.phone` plus `AutofillHints.telephoneNumber`; store as E.164 (the server or a library like `phone_numbers_parser` normalises it) |
| Masks | a custom `TextInputFormatter` for display formatting (card groups, dates). Strip the mask before validating or sending, and keep the caret right (return a `TextEditingValue` with an updated `selection`) |

```dart
class CardNumberFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(TextEditingValue old, TextEditingValue next) {
    final digits = next.text.replaceAll(RegExp(r'\D'), '');
    final capped = digits.length > 19 ? digits.substring(0, 19) : digits;
    final grouped = [
      for (var i = 0; i < capped.length; i += 4) capped.substring(i, i + 4 > capped.length ? capped.length : i + 4),
    ].join(' ');
    return TextEditingValue(text: grouped, selection: TextSelection.collapsed(offset: grouped.length));
  }
}
```

Formatters run on every keystroke, so keep them allocation-light. A formatter
that moves the caret to the end on every edit makes mid-string edits
painful. Compute the new offset from the old one when the mask allows editing
in the middle.

## 7. Error text

- Say what to do, not what went wrong: "Enter an email like name@example.com",
  not "Invalid input".
- Use l10n for every message (`flutter-i18n`, if installed).
- Never include the entered value, especially for secrets ("Password 'hunter2'
  is too short").
- Don't reveal which half of a login was wrong ("No account for this email").
  Use one message for a bad email or a bad password, so the form doesn't
  enable account enumeration.
- `errorText` is part of the field's semantics, so screen readers read it when
  the field is focused. Focus the first invalid field after submit (§2). For
  errors that appear without a focus change, announce them (see the
  accessibility section in `secure-inputs.md`).

## 8. Testing validators

Pure rules are unit-tested without widgets:

```dart
test('confirm must match', () {
  const d = PasswordChangeDraft(current: 'old-pass-1234', next: 'new-pass-1234', confirm: 'nope');
  expect(d.validate(), {PasswordField.confirm: PasswordError.mismatch});
});
```

Widget-test the wiring once per form: enter text with `tester.enterText`, tap
submit, `pump()`, and expect the error text and that the submit callback
wasn't called. Test async validators with `fake_async` or by awaiting the
fake use case, never with real delays (`flutter-testing`).
