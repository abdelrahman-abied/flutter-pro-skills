# Multi-step forms, dirty state and submit handling

## Contents

1. Submit handling and double-submit, per pattern
2. Multi-step forms (wizards, steppers)
3. Dirty state and unsaved-changes guards
4. Drafts, restoration and what never to persist
5. Testing these flows

## 1. Submit handling and double-submit

A second tap while the first request is in flight sends a second request. You
get two orders, two sign-up emails, or a pop that removes the screen *under*
the form. The guard belongs in two places:

1. **The UI**: the button is disabled (`onPressed: null`) or replaced by a
   progress indicator while busy, so the user sees that something is
   happening. FORM-005 checks this when the async work runs from the widget.
2. **The logic**: the submit method ignores calls while busy, because
   keyboard "done", a second button or a test can call it too.

| Pattern | UI guard | Logic guard |
|---|---|---|
| MVN | `onPressed: state is XSubmitting ? null : submit` | `if (state is XSubmitting) return;` at the top of the notifier method |
| Riverpod `AsyncNotifier` | `onPressed: state.isLoading ? null : submit` | `if (state.isLoading) return;` |
| MVVM + Command | `onPressed: cmd.running ? null : cmd.execute` inside a `ListenableBuilder` | `Command.execute` already returns early while `running` |
| Bloc | `status.isInProgress ? null : () => bloc.add(Submitted())`, or a spinner instead of the button | `on<Submitted>(_onSubmitted, transformer: droppable())` (bloc_concurrency) or `if (state.status.isInProgress) return;` |
| Cubit | same as Bloc | `if (state.status.isInProgress) return;` |
| Provider | `model.isSubmitting ? null : model.submit` | `if (_status == FormStatus.submitting) return;` |
| GetX | `Obx(() => … c.isSubmitting.value ? null : c.submit)` | `if (isSubmitting.value) return;` |
| setState | `_submitting ? null : _submit` | `if (_submitting) return;` before the first `await` |

The submit sequence, in any pattern:

```dart
Future<void> _submit() async {
  if (_submitting) return;                        // 1. guard
  final form = _formKey.currentState!;
  if (!form.validate()) return;                   // 2. client validation (UX)
  form.save();
  FocusScope.of(context).unfocus();               // 3. close the keyboard
  setState(() => _submitting = true);
  try {
    await widget.onSubmit(_draft.normalised());   // 4. logic → use case → repository
    if (!mounted) return;                         // 5. context after await (UI-context-after-await)
    TextInput.finishAutofillContext();
    context.pop();                                // or let a listener navigate
  } on ValidationFailure catch (f) {
    if (mounted) setState(() => _serverErrors = f.fieldErrors);   // 6. server errors to fields
  } finally {
    if (mounted) setState(() => _submitting = false);
  }
}
```

In MVN, Bloc and MVVM, steps 1 and 4 to 6 live in the logic holder, and the
widget only validates and forwards the draft (`placement-by-architecture.md`).

Non-idempotent submits (payments, transfers, orders) also send an
**idempotency key**, created once per form instance and reused on retry. The
server then dedupes what the UI guard missed.

## 2. Multi-step forms

One draft, many steps:

- **Keep one draft object for the whole flow** in the logic holder (the
  notifier, view model or bloc scoped to the flow), not one per step. Each
  step reads its slice and writes it back on "Next".
- **Keep a `GlobalKey<FormState>` per step**, and validate the current step
  before advancing. Validate everything again on the final submit, since an
  earlier step may have been edited.
- **Keep the controllers alive.** A `PageView` or `Stepper` disposes the
  steps that are off screen, along with their controllers and typed text,
  unless you either:
  - hoist the controllers to the parent `State`, or seed each step's
    controllers from the draft in `initState`, or
  - use `AutomaticKeepAliveClientMixin` on the step widgets.

  Losing typed input on "Back" is `FORM-lost-input-on-step`.
- **Navigation inside the flow is UI.** Use `PageController.nextPage`,
  `Stepper(currentStep:)` or nested routes. The logic holder exposes which
  steps are valid and complete. It doesn't push routes (`AP-navigation-in-logic`).
- **Disable swiping** in a wizard `PageView` (`physics: NeverScrollableScrollPhysics()`),
  so users can't skip a step's validation.
- **Each step is announced.** Give the step title a heading
  (`Semantics(header: true)`), and move focus to the first field of the new
  step.

```dart
// Bloc/Cubit-scoped wizard: one draft, step validity from the logic
class OnboardingCubit extends Cubit<OnboardingState> {
  OnboardingCubit() : super(const OnboardingState());

  void profileChanged(ProfileDraft p) => emit(state.copyWith(profile: p));
  void addressChanged(AddressDraft a) => emit(state.copyWith(address: a));
  void next() {
    if (state.currentStepValid) emit(state.copyWith(step: state.step + 1));
  }
  void back() => emit(state.copyWith(step: state.step - 1));
}

// view
final step = context.select((OnboardingCubit c) => c.state.step);
return PopScope(
  canPop: step == 0,                                    // system back goes to the previous step
  onPopInvokedWithResult: (didPop, _) {
    if (!didPop) context.read<OnboardingCubit>().back();
  },
  child: IndexedStack(index: step, children: const [ProfileStep(), AddressStep(), ReviewStep()]),
);
```

`IndexedStack` keeps every step mounted, so controllers survive, which is fine
for 3 to 5 light steps. For long or heavy flows, use a `PageView` with hoisted
controllers.

## 3. Dirty state and unsaved-changes guards

"Dirty" means the current values differ from the values the form opened with,
not "the user typed something". Compare values, so that typing and then
deleting is clean again:

```dart
// in logic (notifier/view model/cubit); drafts are value objects with ==
bool get isDirty => _draft != _initial;
```

Guard leaving the screen with `PopScope` (Flutter 3.12+; `WillPopScope` is
deprecated):

```dart
PopScope(
  canPop: !isDirty || isSaving,
  onPopInvokedWithResult: (didPop, _) async {
    if (didPop) return;
    final discard = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.discardChangesTitle),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.keepEditing)),
          TextButton(onPressed: () => Navigator.pop(context, true), child: Text(l10n.discard)),
        ],
      ),
    );
    if (discard == true && context.mounted) Navigator.of(context).pop();
  },
  child: form,
)
```

- After a successful save, reset the baseline (`_initial = _draft`) **before**
  popping, or the guard fires on your own `pop()`.
- `PopScope` only sees pops of its own route. With go_router, a `go()` to
  another branch skips it. Use the route's `onExit` callback for those exits
  (see the `flutter-navigation` skill, if installed).
- Don't guard read-only screens, and don't prompt when nothing changed. A
  needless "Discard changes?" dialog trains users to tap through it.
- On the web, warn on tab close with a `beforeunload` handler only when dirty.

## 4. Drafts, restoration and what never to persist

- **State restoration** (`restorationId` on a `TextField`, `RestorationMixin`
  with `RestorableTextEditingController`) brings typed text back after the OS
  kills the app in the background. Use it on long forms.
- **Drafts** (saved to local storage so the user can resume later) are app
  state. Save them in the data layer through a repository, debounced, and
  clear them on submit.
- **Never persist secrets**: passwords, PINs, CVVs, one-time codes and
  security answers must not reach restoration data, HydratedBloc JSON, draft
  storage or `shared_preferences`. Restoration data is saved by the OS and may
  end up in backups. Leave `restorationId` off secret fields, and exclude them
  from `toJson` (`FORM-secret-persisted`).

## 5. Testing these flows

- **Double submit**: tap the button twice in one frame and verify the fake use
  case or repository was called once. Then complete the fake's `Completer` and
  verify the button is re-enabled.
- **Wizard**: enter step 1, go next and back, and expect the text to still be
  there.
- **Dirty guard**: edit, then `tester.binding.handlePopRoute()` (or tap back),
  and expect the dialog. With no edits, expect no dialog.
- **Server errors**: have the fake return `ValidationFailure({email: taken})`
  and expect the error under the email field. Edit the field and expect it to
  clear.

See `flutter-testing` for `bloc_test`, `ProviderContainer` overrides and fakes.
