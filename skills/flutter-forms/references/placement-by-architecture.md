# Where each piece of a form goes, per architecture

A form has five kinds of state. Each has one home. Most form bugs come from
putting one of them in the wrong place: controllers in a global provider, so
the back button shows stale text; validation rules in the widget, so they
can't be tested; or a `bool isLoading` beside a `String? error`, so the two
contradict each other.

| Piece | What it is | Home (all patterns) |
|---|---|---|
| **Field plumbing** | `TextEditingController`, `FocusNode`, `GlobalKey<FormState>`, scroll position, "password visible" toggle | The widget (`State`, or hooks). Ephemeral: create it in `initState`, dispose it in `dispose` |
| **Field values (the draft)** | what the user typed, as a typed value object | The logic holder (notifier, view model, bloc, controller), pushed in with `onChanged` or read once on submit |
| **Validation rules** | "is this a valid email", "end date after start date", "username taken" | Pure functions or value objects (domain or `core/validation`). Called by the widget's `validator:` (format checks) and by the logic holder (cross-field, async, submit) |
| **Submission** | calling the use case or repository, mapping the result | The logic holder. Never the widget |
| **Form status** | idle → submitting → success / failure (with field errors) | A sealed state, a status enum, or a `Command`. Never separate `isLoading` / `error` booleans (`AP-boolean-soup-state`) |

Two rules from the canonical sources drive this table:

- **riverpod.dev, DO/DON'T:** AVOID using providers for ephemeral state, which
  includes form state and anything Flutter manages with a controller
  (`TextEditingController`). This is ARCH-109 (`ephemeral-state-in-provider`)
  in the `flutter-architecture` checker, so don't report it again as a FORM
  finding. Read `../flutter-architecture/references/anti-patterns.md`
  (ARCH-109) if your agent doesn't auto-load skills.
- **The Flutter architecture guide:** views contain no logic beyond simple
  conditions, layout and animation. Business validation and submission belong
  in the view model.

GetX is the exception for plumbing: a `GetxController` that owns
`TextEditingController`s and disposes them in `onClose()` is idiomatic GetX,
and ARCH-109 doesn't apply to it.

## Contents

1. The shared domain layer
2. MVN (Riverpod codegen notifier, sealed state)
3. MVVM with Command (Flutter architecture guide)
4. Bloc / Cubit
5. Provider (ChangeNotifier)
6. GetX
7. setState (no state-management package)
8. Review notes by pattern

## The shared domain layer

The examples below share a domain layer:

```dart
// domain/value_objects/email.dart: pure Dart, unit-testable, reused by every pattern
extension type const Email._(String value) {
  static Email? tryParse(String raw) {
    final v = raw.trim().toLowerCase();
    return _re.hasMatch(v) && v.length <= 254 ? Email._(v) : null;
  }

  static final _re = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
}

sealed class EmailError { const EmailError(); }
final class EmailEmpty extends EmailError { const EmailEmpty(); }
final class EmailMalformed extends EmailError { const EmailMalformed(); }

EmailError? validateEmail(String raw) => raw.trim().isEmpty
    ? const EmailEmpty()
    : Email.tryParse(raw) == null ? const EmailMalformed() : null;
```

Validators return **typed errors, not strings**. The view turns them into
localized text, because only the view has `BuildContext` and l10n. That is the
same split that `flutter-error-handling` uses for failures.

---

## MVN (Riverpod codegen notifier, sealed state)

Under MVN the view owns the plumbing. The notifier owns the draft, the rules
that need more than one field, and the submission, which goes through a use
case. The state is sealed, so the view's `switch` is exhaustive.

```dart
// presentation/state/sign_up_state.dart
sealed class SignUpState { const SignUpState(); }
final class SignUpEditing extends SignUpState {
  const SignUpEditing({this.fieldErrors = const {}});
  final Map<SignUpField, FieldError> fieldErrors;   // server errors mapped to fields
}
final class SignUpSubmitting extends SignUpState { const SignUpSubmitting(); }
final class SignUpDone extends SignUpState { const SignUpDone(); }
final class SignUpFailed extends SignUpState {
  const SignUpFailed(this.failure);
  final Failure failure;                            // typed, translated in the view
}

// presentation/notifier/sign_up_notifier.dart
@riverpod
class SignUpNotifier extends _$SignUpNotifier {
  @override
  SignUpState build() => const SignUpEditing();

  Future<void> submit(SignUpDraft draft) async {
    if (state is SignUpSubmitting) return;          // double-submit guard in logic too
    state = const SignUpSubmitting();
    try {
      await ref.read(signUpUseCaseProvider)(draft.normalised());
      state = const SignUpDone();
    } on ValidationFailure catch (f) {
      state = SignUpEditing(fieldErrors: f.fieldErrors);
    } on Failure catch (f) {
      state = SignUpFailed(f);
    }
  }
}
```

```dart
// presentation/view/sign_up_view.dart
class SignUpView extends ConsumerStatefulWidget {
  const SignUpView({super.key});
  @override
  ConsumerState<SignUpView> createState() => _SignUpViewState();
}

class _SignUpViewState extends ConsumerState<SignUpView> {
  final _formKey = GlobalKey<FormState>();          // plumbing: widget-owned
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    ref.read(signUpProvider.notifier).submit(
          SignUpDraft(email: _email.text, password: _password.text),
        );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(signUpProvider);
    ref.listen(signUpProvider, (_, next) {          // one-time effects in a listener
      if (next is SignUpDone) TextInput.finishAutofillContext();
    });
    final errors = switch (state) {
      SignUpEditing(:final fieldErrors) => fieldErrors,
      _ => const <SignUpField, FieldError>{},
    };
    return AutofillGroup(
      child: Form(
        key: _formKey,
        child: Column(children: [
          EmailField(controller: _email, serverError: errors[SignUpField.email]),
          NewPasswordField(controller: _password),
          FilledButton(
            onPressed: state is SignUpSubmitting ? null : _submit,
            child: const Text('Create account'),
          ),
        ]),
      ),
    );
  }
}
```

A hooks-based MVN view (`HookConsumerWidget`) uses `useTextEditingController()`
and `useFocusNode()`, which dispose themselves.

Riverpod 3 also has *mutations* for tracking a submit's progress outside the
provider's own state. They're experimental, so prefer the sealed state unless
the project already uses them.

## MVVM with Command (Flutter architecture guide)

The view model holds the draft and a `Command` for the submit. The command's
`running` flag is the busy state, and it already refuses a second `execute`
while running. Plumbing stays in the view.

```dart
class SignUpViewModel extends ChangeNotifier {
  SignUpViewModel({required AuthRepository auth}) : _auth = auth {
    signUp = Command1<void, SignUpDraft>(_signUp);
  }

  final AuthRepository _auth;
  late final Command1<void, SignUpDraft> signUp;
  Map<SignUpField, FieldError> fieldErrors = const {};

  Future<Result<void>> _signUp(SignUpDraft draft) async {
    final result = await _auth.signUp(draft.normalised());
    if (result case Error(error: ValidationFailure(:final fieldErrors))) {
      this.fieldErrors = fieldErrors;
      notifyListeners();
    }
    return result;
  }
}

// view
ListenableBuilder(
  listenable: viewModel.signUp,
  builder: (context, _) => FilledButton(
    onPressed: viewModel.signUp.running
        ? null
        : () {
            if (_formKey.currentState!.validate()) {
              viewModel.signUp.execute(SignUpDraft(email: _email.text, password: _password.text));
            }
          },
    child: const Text('Create account'),
  ),
)
```

## Bloc / Cubit

The bloclibrary `flutter_login` and `flutter_firebase_login` examples put the
**field values** in the bloc state as `formz` inputs, updated on every
keystroke (`LoginUsernameChanged`). Validation lives in the `FormzInput`
subclasses, and `FormzSubmissionStatus` is the form status. The widget then
needs no `TextEditingController` at all. Use that style when the project
already does. Otherwise keep the Form/controller approach and send the draft on
submit.

```dart
class Password extends FormzInput<String, PasswordError> {
  const Password.pure() : super.pure('');
  const Password.dirty([super.value = '']) : super.dirty();
  @override
  PasswordError? validator(String value) => value.length < 12 ? PasswordError.tooShort : null;
}

class LoginBloc extends Bloc<LoginEvent, LoginState> {
  LoginBloc({required AuthRepository auth}) : _auth = auth, super(const LoginState()) {
    on<LoginPasswordChanged>(_onPasswordChanged);
    on<LoginSubmitted>(_onSubmitted, transformer: droppable()); // bloc_concurrency: ignore taps while busy
  }

  final AuthRepository _auth;

  void _onPasswordChanged(LoginPasswordChanged e, Emitter<LoginState> emit) {
    final password = Password.dirty(e.password);
    emit(state.copyWith(password: password, isValid: Formz.validate([password, state.email])));
  }

  Future<void> _onSubmitted(LoginSubmitted e, Emitter<LoginState> emit) async {
    if (!state.isValid) return;
    emit(state.copyWith(status: FormzSubmissionStatus.inProgress));
    try {
      await _auth.logIn(email: state.email.value.trim(), password: state.password.value);
      emit(state.copyWith(status: FormzSubmissionStatus.success));
    } on AuthFailure {
      emit(state.copyWith(status: FormzSubmissionStatus.failure));
    }
  }
}

// view: the button is disabled while in progress, or replaced by a spinner
final inProgress = context.select((LoginBloc b) => b.state.status.isInProgressOrSuccess);
if (inProgress) return const CircularProgressIndicator();
```

With a `HydratedBloc`, never persist secrets: override `toJson` so the
password field isn't written to disk (`FORM-secret-persisted`).

## Provider (ChangeNotifier)

The same split as MVVM without commands: the model holds the draft, a status
enum and the submit method. It also checks `if (status == FormStatus.submitting) return;`
before starting. The widget owns the controllers and reads the model with
`context.watch` / `Consumer`.

## GetX

A `GetxController` may own the `TextEditingController`s (that's idiomatic
GetX) and must dispose them in `onClose()`. Expose the busy state as an
`RxBool` or `Rx<FormStatus>` and wrap the button in `Obx`:

```dart
class SignUpController extends GetxController {
  final email = TextEditingController();
  final password = TextEditingController();
  final isSubmitting = false.obs;

  Future<void> submit() async {
    if (isSubmitting.value) return;
    isSubmitting.value = true;
    try {
      await _auth.signUp(email.text.trim(), password.text);
    } finally {
      isSubmitting.value = false;
    }
  }

  @override
  void onClose() {
    email.dispose();
    password.dispose();
    super.onClose();
  }
}

Obx(() => FilledButton(
      onPressed: c.isSubmitting.value ? null : c.submit,
      child: const Text('Create account'),
    ))
```

## setState (no state-management package)

All five pieces live in one `State`. That's fine for a small screen. Keep the
validation rules in pure functions anyway, so they stay testable. Use a single
`_submitting` flag that the handler checks first and that drives `onPressed`.

## Review notes by pattern

| Pattern | Flag | Don't flag |
|---|---|---|
| MVN | controllers in a notifier (ARCH-109, not FORM); `submit` in the view calling a repository (ARCH-012); `bool isSubmitting` in a sealed-state codebase | `ref.read(p.notifier).submit(draft)` from the view; a `GlobalKey<FormState>` in the view |
| MVVM | `validate()` logic or HTTP in the view; a second `execute` path that bypasses the command | controllers in the view; `Command.running` driving `onPressed` |
| Bloc | `TextEditingController` held in a bloc; a submit handler without a `droppable()`/status guard when double events matter | formz inputs updated on every keystroke; no controllers at all |
| Provider | controllers inside the ChangeNotifier (ARCH-109) | a status enum on the model |
| GetX | controllers created in `build()`; no `onClose` disposal | controllers owned by the `GetxController` |
