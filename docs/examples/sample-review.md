# Sample review: `smelly_app` (the review skill's test fixture)

This is what the `dart-flutter-review` skill produces. It follows the report
template in
[`skills/dart-flutter-review/references/review-guide.md`](../../skills/dart-flutter-review/references/review-guide.md).

**How it was made.** The project is
[`skills/dart-flutter-review/tests/fixtures/smelly_app`](../../skills/dart-flutter-review/tests/fixtures/smelly_app),
a 10-file fixture with deliberately planted smells. It was copied to a temp
folder, `flutter pub get --offline` was run in the copy, and then
`bash skills/dart-flutter-review/scripts/review.sh <copy> --max 3` was run
(Dart 3.13.5). The unedited output is in
[`review-smelly_app.txt`](review-smelly_app.txt). Every finding below comes
from a line in that output or from reading the fixture's code, and each one was
re-checked against the source. Nothing was added for effect.

---

# Dart/Flutter review: smelly_app (whole project)

**Scope:** whole project: lib/ 10 files (all read)
**Toolchain:** Dart 3.13.5 · lints: `flutter_lints` (`package:flutter_lints/flutter.yaml`, no custom rules) · format: all formatted
**Architecture:** detected: mvn, feature-first, confidence medium (signals: `flutter_riverpod` dependency, 1 file under `presentation/notifier/`). No notifier or use case exists yet, so only MVN rules that don't depend on them are applied
**Coverage:** mechanical ✓ · architecture ✓ · UI ✓ · Dart/naming ✓ · security: not run
**Verdict:** `CartView` has four bugs to fix before merge (network I/O in the widget, a request re-fired on every rebuild, a timer that outlives the screen, and errors swallowed in `CartApi`). The rest is naming and widget polish.

| # | Severity | Finding | Location |
|---|---|---|---|
| 1 | High | The view does network I/O itself (`Dio()` inside the `State`) | lib/features/cart/presentation/view/cart_view.dart:7, :35 |
| 2 | High | `FutureBuilder` gets a new future on every build, so the request repeats and the label flashes `null` | lib/features/cart/presentation/view/cart_view.dart:54-55 |
| 3 | High | `Timer.periodic` never cancelled and `ScrollController` never disposed | lib/features/cart/presentation/view/cart_view.dart:20, :27 |
| 4 | High | Network errors swallowed: `getItems()` returns `[]`, `syncAsync()` has an empty `catch` | lib/features/cart/data/sources/cart_api.dart:23, :31 |
| 5 | Medium | The Pay button never disables: `isDisabled` is written but never read | lib/features/cart/presentation/view/cart_view.dart:22, :31, :63 |
| 6 | Medium | `UniqueKey()` on the root `Container` remounts the whole screen on every rebuild | lib/features/cart/presentation/view/cart_view.dart:47 |
| 7 | Medium | `dynamic parse(dynamic raw)` turns off type checking, and nothing calls it | lib/core/utils.dart:4 |
| 8 | Low | `get`/`Async`/`I`/`Manager` names, inconsistent with the repository's own `fetchItems` | lib/features/cart/data/sources/cart_api.dart:5, :6, :9, :19, :28 |
| 9 | Low | Public `onSubmit()` method on a `State` | lib/features/cart/presentation/view/cart_view.dart:30 |
| 10 | Low | `build()` polish: `_buildHeader()` helper, `MediaQuery.of`, static `Opacity`, hard-coded colour, eager `ListView(children:)` | lib/features/cart/presentation/view/cart_view.dart:39-60 |
| 11 | Low | `warmUp()` starts a future and throws the result away | lib/features/cart/data/sources/cart_api.dart:34-35 |
| 12 | Low | Grab-bag `utils.dart` with a `k`-prefixed constant nobody uses | lib/core/utils.dart:1-2 |
| 13 | Info | The MVN layering is only half there: the repository exists, but no use case or notifier uses it | lib/features/cart/ |
| M | Mechanical | `dart fix --apply` resolves 1 issue (curly_braces_in_flow_control_structures ×1) | 1 file |

## Findings

### 1. The view does network I/O itself (High)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:7` (`import 'package:dio/dio.dart';`), `:35` (`await Dio().get<int>('https://example.com/cart/count')`)
**Rule:** ARCH-005 ui-depends-on-data-source, ARCH-101 io-in-widget (`flutter-architecture` › anti-patterns.md)
**Why it matters:** the widget owns a transport client, a hard-coded URL and the
parsing. It can't be tested without the network, and it bypasses the
`CartApi` → `CartRepository` path the feature already has. Under MVN the flow
is View → Notifier → UseCase → Repository → Source.
**Fix:** move the call into the data layer, and have the view watch a notifier.
```dart
// data/sources/cart_api.dart
Future<int> fetchCount() async =>
    (await _dio.get<int>('/cart/count')).data ?? 0;

// presentation/notifier/cart_count_notifier.dart (calls a use case, per MVN)
@riverpod
class CartCountNotifier extends _$CartCountNotifier {
  @override
  Future<int> build() => ref.watch(fetchCartCountProvider)();
}

// view: no dio import
final count = ref.watch(cartCountNotifierProvider);
```

### 2. `FutureBuilder` gets a new future on every build (High)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:54` (`future: fetchCount(),`), `:55`
**Rule:** UI-future-in-build: Flutter: don't create futures in `build()` (`flutter-ui-practices` › flutter-ui.md §3)
**Why it matters:** `build()` calls `fetchCount()`, so every rebuild starts a
new HTTP request. Rebuilds happen at least every 30 s (the timer in finding 3
calls `setState`) and on every tap of Pay. Each new future resets the snapshot,
and `Text('${snapshot.data}')` shows the literal text `null` while it loads and
after any error.
**Fix:** create the future once (or, better, use the notifier from finding 1),
and render the loading and error states.
```dart
late final Future<int> _count = fetchCount(); // until finding 1 lands

builder: (context, snapshot) => switch (snapshot) {
  AsyncSnapshot(hasError: true) => const Text('—'),
  AsyncSnapshot(:final data?) => Text('$data'),
  _ => const SizedBox.square(dimension: 16, child: CircularProgressIndicator()),
},
```

### 3. `Timer.periodic` never cancelled and `ScrollController` never disposed (High)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:27` (`_poll = Timer.periodic(...)`), `:20` (`final _scroll = ScrollController();`). The analyzer's `unused_field` warning on `_poll` (`:21`) belongs to this finding.
**Rule:** UI-lifecycle: Flutter: dispose what you create (`flutter-ui-practices` › flutter-ui.md §1)
**Why it matters:** `_CartViewState` has no `dispose()` override. After the
screen is popped, the timer keeps firing and calls `setState` on a defunct
`State` every 30 s, which throws "setState() called after dispose()". It also
keeps the `State` and its controller alive.
**Fix:**
```dart
@override
void dispose() {
  _poll?.cancel();
  _scroll.dispose();
  super.dispose();
}
```

### 4. Network errors swallowed in `CartApi` (High)
**Where:** `lib/features/cart/data/sources/cart_api.dart:23` (`catch (e) { return const []; }`), `:31` (`catch (e) {}`, also the analyzer's `empty_catches`)
**Rule:** ED-swallowed-catch: Effective Dart: DON'T discard errors
**Why it matters:** a failed request looks exactly like an empty cart, so the
UI shows "0 items" instead of an error with a retry. A failed `/cart/sync` is
silently lost. Nothing is logged, so you can't see it in the field either.
**Fix:** let the error reach a layer that can map it to a typed failure (or a
`Result`), and catch only what you expect.
```dart
Future<List<String>> fetchItems() async {
  final response = await _dio.get<List<String>>('/cart');
  return response.data ?? const [];
} // DioException propagates; the repository maps it to a CartFailure
```

### 5. The Pay button never disables (Medium)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:22` (`bool isDisabled = false;`), `:31`, `:63` (`onPressed: onSubmit`)
**Rule:** UI-state-never-read, plus NAME-negative-bool (Effective Dart: PREFER positive boolean names)
**Why it matters:** `onSubmit` sets `isDisabled = true`, but nothing reads it.
The button stays enabled, so a second tap submits again. The negative name
doesn't help: `!isDisabled` reads worse than `isSubmitting`.
**Fix:**
```dart
bool _isSubmitting = false;
// ...
ElevatedButton(
  onPressed: _isSubmitting ? null : _handleSubmit,
  child: const Text('Pay'),
),
```
**Confidence:** confirmed that the field is never read. That disabling the
button was the intent is inferred from the name.

### 6. `UniqueKey()` remounts the whole screen on every rebuild (Medium)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:47` (`key: UniqueKey(),`)
**Rule:** UI-keys: Flutter: use stable keys (`flutter-ui-practices` › flutter-ui.md §3)
**Why it matters:** a new key on every `build()` makes Flutter throw away the
`Container` and everything under it, including the `FutureBuilder`'s state and
the `ListView`, and build them again from scratch. With the 30 s timer, that
happens even when nothing changed.
**Fix:** remove the key. Nothing here needs one.

### 7. `dynamic parse(dynamic raw)` turns off type checking (Medium)
**Where:** `lib/core/utils.dart:4`
**Rule:** ED-avoid-dynamic: Effective Dart: AVOID `dynamic` unless you mean to disable static checking
**Why it matters:** the function returns its argument unchanged and has no
callers. If someone starts using it, every value passing through it loses its
type.
**Fix:** delete it. If a parser is needed later, give it real types
(`Cart parseCart(Map<String, Object?> json)`).

### 8. `get`/`Async`/`I`/`Manager` names in `CartApi` (Low)
**Where:** `lib/features/cart/data/sources/cart_api.dart:5` (`ICartApi`), `:6`/`:19` (`getItems()`), `:9` (`CartManager`), `:28` (`syncAsync()`)
**Rule:** NAME-inconsistent-term, NAME-i-prefix, NAME-get-prefix, NAME-async-suffix, NAME-noise-word (`dart-naming` › naming.md)
**Why it matters:** the project isn't consistent with itself. The repository
contract already says `fetchItems()` (cart_repository.dart:3) while the source
says `getItems()`. Every Dart class is an interface, so `I` adds nothing. The
`Future` return type already says "async". And `CartManager` is an unused class
holding a public mutable list.
**Fix:** `ICartApi` → `CartApi` (and rename the impl, e.g. `DioCartApi`, or
drop the interface if there's no fake). `getItems` → `fetchItems`, `syncAsync`
→ `sync`. Delete `CartManager`.

### 9. Public `onSubmit()` method on a `State` (Low)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:30`
**Rule:** NAME-on-method: Flutter style: `onFoo` names callback *properties*; handlers are `_handleFoo` (`dart-naming`)
**Fix:** rename it to `_handleSubmit` (private, since only `build()` uses it).

### 10. `build()` polish (Low)
**Where:** `lib/features/cart/presentation/view/cart_view.dart`
- `:39` `Widget _buildHeader()`: make it a small `StatelessWidget` (`_CartHeader`) so it gets its own element and can be `const`.
- `:45` `MediaQuery.of(context).size.width`: use `MediaQuery.sizeOf(context).width`, so the widget rebuilds only on size changes. Here the `width:` is the full width anyway, so you can drop it.
- `:40` static `Opacity(opacity: 0.5, ...)`: use a translucent text colour instead, and avoid the `saveLayer`.
- `:49` `Color(0xFF00897B)`: read it from `Theme.of(context).colorScheme`.
- `:60` `ListView(children: widget.items.map(...).toList())`: fine for a few items. For a cart that can grow, use `ListView.builder`.

**Rule:** UI-helper-method, UI-mediaquery-of, UI-opacity, UI-hardcoded-style, UI-eager-list (`flutter-ui-practices` › flutter-ui.md §3, §4, §7)

### 11. `warmUp()` starts a future and throws it away (Low)
**Where:** `lib/features/cart/data/sources/cart_api.dart:34-35` (`getItems().then((items) => items.length);`)
**Rule:** UI-unawaited-future: Effective Dart: PREFER async/await over raw futures
**Why it matters:** the computed length goes nowhere, and the future is neither
awaited nor marked `unawaited`. It only works because `getItems()` swallows
every error (finding 4). Once that's fixed, an error here would be unhandled.
**Fix:** `Future<void> warmUp() => fetchItems();`, awaited by the caller, or
delete it if nothing calls it (nothing does today).

### 12. Grab-bag `utils.dart` with an unused `k` constant (Low)
**Where:** `lib/core/utils.dart:1-2` (`const kDefaultTimeout = Duration(seconds: 5);`)
**Rule:** NAME-grab-bag-file, NAME-prefix-letters (Effective Dart: DON'T use prefix letters). The project has no other `k` constants, so this isn't an established convention.
**Fix:** after finding 7 the file holds only this constant, and nothing uses
it. Delete it, or move it next to the Dio setup as `defaultTimeout`.

### 13. The MVN layering is only half there (Info)
**Where:** `lib/features/cart/`
The checker reads this as MVN (Riverpod plus a `presentation/notifier/` folder),
but that folder holds only a `StreamProvider` (`ticks_provider.dart`, which
correctly releases its subscription with `ref.onDispose`). There is a
`CartRepository` contract and a `CartRepositoryImpl`, but no use case and no
notifier calls them, and `CartView` is a plain `StatefulWidget` that talks to
Dio. So `clean_architecture: false` and `use_cases: false`. Fixing finding 1
the MVN way (add a `fetchCartCount` use case and a `CartCountNotifier`) also
completes the layering. If the team doesn't want MVN, declare the pattern in
`AGENTS.md`, and the review will judge the code by that pattern's rules instead.

## Mechanical fixes
Run `dart fix --apply && dart format .`. That fixes
`curly_braces_in_flow_control_structures` ×1
(`lib/features/cart/presentation/view/checkout_form.dart:25`). Formatting is
already clean.

## Worth adopting (optional)
- The Effective Dart set in
  `dart-flutter-best-practices/assets/analysis_options.yaml` would flag one
  more issue: `unnecessary_lambdas` at `cart_view.dart:60` (`(i) => Text(i)` →
  `Text.new`). The project hasn't opted into it, so this isn't a violation.

---

*Next step offered, not performed:* apply the mechanical fix, fix findings 1–4,
or fix a specific finding. After any change, rerun `scripts/review.sh` on the
touched files and compare the counts.
