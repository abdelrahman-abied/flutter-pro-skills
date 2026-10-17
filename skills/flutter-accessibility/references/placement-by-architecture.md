# Accessibility placement by architecture

Accessibility is mostly presentation, so most of it lives in views and shared
components in every pattern. The patterns differ in one place: how a fact or
a one-time event travels from logic to the view, which then labels it or
announces it. Judge code by the pattern the project uses (detect it with
`../flutter-architecture/scripts/arch_check.py --json`, or read the project).

## Contents

1. What goes where (all patterns)
2. MVN (Riverpod codegen notifiers + use cases)
3. Plain Riverpod
4. MVVM with Command
5. Bloc / Cubit
6. Provider (ChangeNotifier)
7. GetX
8. setState
9. Design-system components

## 1. What goes where

| Concern | Lives in | Never in |
|---|---|---|
| labels, hints, tooltips, roles (`button`, `header`), `MergeSemantics` | the view, or a shared component | logic, state, repositories |
| semantic *facts*: status, counts, selection, progress | state / logic fields (enums, ints, bools) | pre-built sentences in state |
| one-time announcements | an effect or status emitted by logic, spoken by a listener in the view | `SemanticsService.announce` inside logic (A11Y-011) |
| text-scale and reduced-motion reads | the view (`MediaQuery.textScalerOf`, `disableAnimationsOf`) | logic |
| colours and contrast | the theme (`ColorScheme`, `ThemeExtension`) | feature widgets, logic |
| focus nodes, traversal groups | the view's `State` | providers, blocs (ARCH-109) |

Why: announcements need localised text and a `TextDirection`, and both come
from the `BuildContext`. Logic that builds sentences can't be localised or
tested without a widget tree, and logic that holds a `BuildContext` breaks
ARCH-102. Logic stays testable when it emits `SaveResult.saved` and the view
decides it says "Profile saved".

## 2. MVN

The notifier's sealed state carries the fact. A one-time effect is a separate
sealed value (or a field on the state that the view reacts to once), and the
view announces in `ref.listen`.

```dart
// presentation/state/cart_state.dart
sealed class CartEffect { const CartEffect(); }
final class CartItemAdded extends CartEffect { const CartItemAdded(this.name); final String name; }

// presentation/notifier/cart_effect_notifier.dart
@riverpod
class CartEffectNotifier extends _$CartEffectNotifier {
  @override
  CartEffect? build() => null;
  void emit(CartEffect effect) => state = effect;
}

// presentation/view/cart_view.dart
ref.listen(cartEffectNotifierProvider, (_, effect) {
  if (effect case CartItemAdded(:final name)) {
    SemanticsService.announce(context.l10n.itemAdded(name), Directionality.of(context));
  }
});
```

Counts and statuses for labels come straight from the state:
`Semantics(label: l10n.unreadCount(state.unread), child: badge)`.

## 3. Plain Riverpod

The same, with `AsyncValue`: announce in `ref.listen` when the value moves
from loading to data or error.

```dart
ref.listen(searchProvider, (prev, next) {
  if (prev?.isLoading == true && next.hasValue) {
    SemanticsService.announce(l10n.resultsFound(next.value!.length), Directionality.of(context));
  }
});
```

## 4. MVVM with Command

The view model exposes `Command`s and plain getters. The view adds a listener
to the command and announces its result, exactly as it shows a snackbar.

```dart
@override
void initState() {
  super.initState();
  widget.viewModel.save.addListener(_onSave);
}

void _onSave() {
  final command = widget.viewModel.save;
  if (command.completed) {
    SemanticsService.announce(AppLocalizations.of(context).saved, Directionality.of(context));
  } else if (command.error) {
    SemanticsService.announce(AppLocalizations.of(context).saveFailed, Directionality.of(context));
  }
}
```

Remove the listener in `dispose` and in `didUpdateWidget` when the view model
changes. Busy state is `command.running`; expose it to the reader with a
`Semantics(liveRegion: true)` status line or by disabling the button, which
is announced as "disabled".

## 5. Bloc / Cubit

State carries the status; `BlocListener` turns status changes into
announcements. Use `listenWhen` so the listener fires once per transition.

```dart
BlocListener<CheckoutBloc, CheckoutState>(
  listenWhen: (prev, next) => prev.status != next.status,
  listener: (context, state) {
    final l10n = context.l10n;
    final message = switch (state.status) {
      CheckoutStatus.success => l10n.orderPlaced,
      CheckoutStatus.failure => l10n.orderFailed,
      _ => null,
    };
    if (message != null) SemanticsService.announce(message, Directionality.of(context));
  },
  child: const CheckoutForm(),
)
```

Blocs never import `flutter/semantics.dart`. Their tests assert the emitted
status, and a widget test asserts the announcement.

## 6. Provider (ChangeNotifier)

The model exposes a status. The widget's `State` adds a listener in
`initState` and announces when the status changes. Removing the listener in
`dispose` matters as much as for any listener.

## 7. GetX

The controller exposes `Rx` fields. Set up the worker from the view (or from
`onReady` only if the project already does this) and announce there.

```dart
// in the view's State or a GetView's build-once hook
ever<SyncStatus>(controller.status, (status) {
  if (status == SyncStatus.done) {
    SemanticsService.announce('sync_done'.tr, Directionality.of(context));
  }
});
```

`Get.context` inside a controller is the GetX idiom for navigation, but avoid
it for announcements: the message then can't be tested without a widget tree.

## 8. setState

The `State` owns everything. Announce after the async work, once you've
checked `mounted`:

```dart
Future<void> _refresh() async {
  final items = await widget.repository.load();
  if (!mounted) return;
  setState(() => _items = items);
  SemanticsService.announce(AppLocalizations.of(context).updated, Directionality.of(context));
}
```

## 9. Design-system components

The cheapest accessibility fix is in the shared components, because every
screen inherits it. Whatever the pattern:

- `AppIconButton` takes a **required** `String tooltip` (or `semanticLabel`).
- `AppCard` or a list row wraps its content in `MergeSemantics` (or
  `Semantics(container: true)`) and exposes `onTap` with `button: true`.
- Custom toggles, chips and segmented controls set `toggled:`, `selected:` or
  `checked:` and the matching actions, and use `FocusableActionDetector`.
- Buttons keep a 48 dp minimum and `MaterialTapTargetSize.padded`.
- Text styles come from the theme and never pin the text scale.
- Motion tokens read `disableAnimationsOf`.

Token structure and theming belong to `flutter-design-system` (or read
`../flutter-design-system/SKILL.md`; if it's missing, apply the list above
directly).
