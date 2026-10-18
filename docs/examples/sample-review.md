# Sample review: `smelly_app` (the review skill's test fixture)

This is what the `dart-flutter-review` skill produces. It follows the report
template in
[`skills/dart-flutter-review/references/review-guide.md`](../../skills/dart-flutter-review/references/review-guide.md).

**How it was made.** The project is
[`skills/dart-flutter-review/tests/fixtures/smelly_app`](../../skills/dart-flutter-review/tests/fixtures/smelly_app),
a 10-file fixture with deliberately planted smells. It was copied to a temp
folder, `flutter pub get --offline` was run in the copy, and then
`bash skills/dart-flutter-review/scripts/review.sh <copy> --max 3` was run
(Dart 3.13.5, suite v1.6). The unedited output is in
[`review-smelly_app.txt`](review-smelly_app.txt). Every finding below comes
from a line in that output or from reading the fixture's code, and each one was
re-checked against the source. Nothing was added for effect.

---

# Dart/Flutter review: smelly_app (whole project)

**Scope:** whole project: lib/ 10 files (all read)
**Toolchain:** Dart 3.13.5 · lints: `flutter_lints` (`package:flutter_lints/flutter.yaml`, no custom rules) · format: all formatted
**Architecture:** detected: mvn, feature-first, confidence low (signals: `flutter_riverpod` dependency, 1 file under `presentation/notifier/`, 0 use cases). No notifier or use case exists yet, so only MVN rules that don't depend on them are applied
**Coverage:** mechanical ✓ · architecture ✓ · UI ✓ · Dart/naming ✓ · security ✓ (no findings; the deep `flutter-security-audit` scan is not installed) · errors ✓ · tests ✓ · forms ✓ · performance ✓ · networking ✓ · design system ✓ · adaptive layout ✓ · accessibility ✓ · navigation, i18n, persistence, Firebase, platform, release: nothing to review (no router, not localised, no local store, no Firebase, no native code, no android/ or ios/ folder)
**Verdict:** `CartView` has four bugs to fix before merge (network I/O in the widget, a request re-fired on every rebuild, a timer that outlives the screen, and errors swallowed in `CartApi`). The rest is structure, naming and widget polish.

| # | Severity | Finding | Location |
|---|---|---|---|
| 1 | High | The view does network I/O itself, on a `Dio()` with no timeouts | lib/features/cart/presentation/view/cart_view.dart:7, :35 |
| 2 | High | `FutureBuilder` gets a new future on every build, so the request repeats and the label shows `null` | lib/features/cart/presentation/view/cart_view.dart:54-55 |
| 3 | High | `Timer.periodic` never cancelled and `ScrollController` never disposed | lib/features/cart/presentation/view/cart_view.dart:20, :27 |
| 4 | High | Network errors swallowed in `CartApi`, and the repository passes transport errors straight through | lib/features/cart/data/sources/cart_api.dart:24, :32; lib/features/cart/data/repositories/cart_repository_impl.dart:12 |
| 5 | Medium | The Pay button never disables: `isDisabled` is written but never read | lib/features/cart/presentation/view/cart_view.dart:22, :31, :63 |
| 6 | Medium | `UniqueKey()` on the root `Container` remounts the whole screen on every rebuild | lib/features/cart/presentation/view/cart_view.dart:47 |
| 7 | Medium | The cart list builds every item up front (`ListView(children: items.map(...))`) | lib/features/cart/presentation/view/cart_view.dart:58-60 |
| 8 | Medium | `dynamic parse(dynamic raw)` turns off type checking, and nothing calls it | lib/core/utils.dart:5 |
| 9 | Low | No tests at all; the repository, source and screens are unprotected | test/ (missing) |
| 10 | Low | No global error handler, so uncaught errors are only printed | lib/main.dart:6 |
| 11 | Low | The email field uses the default text keyboard | lib/features/cart/presentation/view/checkout_form.dart:36 |
| 12 | Low | `get`/`Async`/`I`/`Manager` names, inconsistent with the repository's own `fetchItems` | lib/features/cart/data/sources/cart_api.dart:6, :7, :10, :20, :29; lib/core/utils.dart:7 |
| 13 | Low | Public `onSubmit()` method on a `State` | lib/features/cart/presentation/view/cart_view.dart:30 |
| 14 | Low | `build()` polish: `_buildHeader()` helper, `MediaQuery.of`, static `Opacity`, hard-coded colour | lib/features/cart/presentation/view/cart_view.dart:39-49 |
| 15 | Low | `warmUp()` starts a future and throws the result away; `countItems()` chains `.then` | lib/features/cart/data/sources/cart_api.dart:35-36, :39 |
| 16 | Low | Grab-bag `utils.dart` with a `k`-prefixed constant nobody uses | lib/core/utils.dart:1-3 |
| 17 | Info | The MVN layering is only half there: the repository exists, but no use case or notifier uses it | lib/features/cart/ |
| M | Mechanical | `dart fix --apply` resolves 1 issue (curly_braces_in_flow_control_structures ×1) | 1 file |

## Findings

### 1. The view does network I/O itself, on a `Dio()` with no timeouts (High)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:7` (`import 'package:dio/dio.dart';`), `:35` (`await Dio().get<int>('https://example.com/cart/count')`)
**Rule:** ARCH-005 ui-depends-on-data-source, ARCH-101 io-in-widget (`flutter-architecture` › anti-patterns.md); also NET-001 client-without-timeouts (`flutter-networking` › rules.md) on the same line
**Why it matters:** the widget owns a transport client, a hard-coded URL and the
parsing. It can't be tested without the network, and it bypasses the
`CartApi` → `CartRepository` path the feature already has. Under MVN the flow
is View → Notifier → UseCase → Repository → Source. The client is also built
per call with Dio's defaults, which have no timeouts, so on a dead network the
request never fails and the label never leaves its loading state.
**Fix:** move the call into the data layer, on the one configured client, and
have the view watch a notifier.
```dart
// core/network/dio_provider.dart: one client, with timeouts
@Riverpod(keepAlive: true)
Dio dio(Ref ref) => Dio(BaseOptions(
      baseUrl: 'https://example.com',
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 20),
    ));

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
**Where:** `lib/features/cart/data/sources/cart_api.dart:24` (`catch (e) { return const []; }`), `:32` (`catch (e) {}`, also the analyzer's `empty_catches`); `lib/features/cart/data/repositories/cart_repository_impl.dart:12` (`fetchItems() => _api.getItems()`)
**Rule:** ERR-001 swallowed-catch (High), ERR-004 repository-leaks-transport-exception (Medium) (`flutter-error-handling` › rules); the `swallowed-catch` candidate and `ED-swallowed-catch` are the same root cause
**Why it matters:** a failed request looks exactly like an empty cart, so the
UI shows "0 items" instead of an error with a retry. A failed `/cart/sync` is
silently lost. Nothing is logged, so you can't see it in the field either. Once
the source stops swallowing, the repository is where `DioException` must
become a typed failure; today it would pass the transport error straight to
the logic layer.
**Fix:** let the source throw, and map in the repository.
```dart
// data/sources/cart_api.dart
Future<List<String>> fetchItems() async {
  final response = await _dio.get<List<String>>('/cart');
  return response.data ?? const [];
} // DioException propagates

// data/repositories/cart_repository_impl.dart
@override
Future<List<String>> fetchItems() async {
  try {
    return await _api.fetchItems();
  } on DioException catch (e) {
    throw CartFailure.fromDio(e); // or return a Result
  }
}
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

### 7. The cart list builds every item up front (Medium)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:58-60` (`ListView(controller: _scroll, children: widget.items.map((i) => Text(i)).toList())`)
**Rule:** PERF-001 eager-list-over-data (`flutter-performance` › rules.md); the `eager-children-map` candidate defers to it
**Why it matters:** `widget.items` is the whole cart, so every row is built and
laid out on every rebuild, including the ones off screen. With the 30 s timer
and the `UniqueKey` from finding 6, that is the full list, every time.
**Fix:**
```dart
ListView.builder(
  controller: _scroll,
  itemCount: widget.items.length,
  itemBuilder: (context, i) => Text(widget.items[i]),
)
```
Under MVN, keep the list in the notifier's state and build from that.

### 8. `dynamic parse(dynamic raw)` turns off type checking (Medium)
**Where:** `lib/core/utils.dart:5`
**Rule:** ED-avoid-dynamic: Effective Dart: AVOID `dynamic` unless you mean to disable static checking
**Why it matters:** the function returns its argument unchanged and has no
callers. If someone starts using it, every value passing through it loses its
type.
**Fix:** delete it. If a parser is needed later, give it real types
(`Cart parseCart(Map<String, Object?> json)`).

### 9. No tests at all (Low)
**Where:** there is no `test/` folder. `test_gaps.py` ranks 7 untested units: `CartRepositoryImpl`, `ticks_provider.dart`, `CartApi` and the three screens first.
**Rule:** TEST-untested-repository, TEST-untested-logic, TEST-untested-source, TEST-untested-view (`flutter-testing`)
**Severity note:** `test_gaps.py` grades the untested provider Medium. It is a
10-line `StreamProvider` with no branches, so it is graded Low here.
**Fix:** start where a fake pays off most: a `CartApi` test over a fake Dio
adapter (parsing and error mapping, once finding 4 lands), then a widget test
of `CartView` with the notifier overridden.

### 10. No global error handler (Low)
**Where:** `lib/main.dart:6` (`void main() => runApp(...)`)
**Rule:** ERR-012 missing-global-error-handler (`flutter-error-handling`)
**Fix:** set `FlutterError.onError` and `PlatformDispatcher.instance.onError`
(or use `runZonedGuarded`) and send both to the crash reporter or a logger.

### 11. The email field uses the default text keyboard (Low)
**Where:** `lib/features/cart/presentation/view/checkout_form.dart:36` (`TextField(controller: _email)`)
**Rule:** FORM-007 input-type-mismatch (`flutter-forms`)
**Fix:** `TextField(controller: _email, keyboardType: TextInputType.emailAddress, autofillHints: const [AutofillHints.email])`.

### 12. `get`/`Async`/`I`/`Manager` names (Low)
**Where:** `lib/features/cart/data/sources/cart_api.dart:6` (`ICartApi`), `:7`/`:20` (`getItems()`), `:10` (`CartManager`), `:29` (`syncAsync()`); `lib/core/utils.dart:7` (`String getVersion()`)
**Rule:** NAME-inconsistent-term, NAME-i-prefix, NAME-get-prefix, NAME-async-suffix, NAME-noise-word (`dart-naming` › naming.md)
**Why it matters:** the project isn't consistent with itself. The repository
contract already says `fetchItems()` (cart_repository.dart:3) while the source
says `getItems()`. Every Dart class is an interface, so `I` adds nothing. The
`Future` return type already says "async". `CartManager` is an unused class
holding a public mutable list. A cheap, argument-free `getVersion()` reads
better as a getter.
**Fix:** `ICartApi` → `CartApi` (and rename the impl, e.g. `DioCartApi`, or
drop the interface if there's no fake). `getItems` → `fetchItems`, `syncAsync`
→ `sync`, `getVersion()` → `String get version`. Delete `CartManager`.

### 13. Public `onSubmit()` method on a `State` (Low)
**Where:** `lib/features/cart/presentation/view/cart_view.dart:30`
**Rule:** NAME-on-method: Flutter style: `onFoo` names callback *properties*; handlers are `_handleFoo` (`dart-naming`)
**Fix:** rename it to `_handleSubmit` (private, since only `build()` uses it).

### 14. `build()` polish (Low)
**Where:** `lib/features/cart/presentation/view/cart_view.dart`
- `:39` `Widget _buildHeader()`: make it a small `StatelessWidget` (`_CartHeader`) so it gets its own element and can be `const`.
- `:45` `MediaQuery.of(context).size.width`: use `MediaQuery.sizeOf(context).width`, so the widget rebuilds only on size changes. Here the `width:` is the full width anyway, so you can drop it.
- `:40` static `Opacity(opacity: 0.5, ...)`: use a translucent text colour instead, and avoid the `saveLayer`.
- `:49` `Color(0xFF00897B)`: read it from `Theme.of(context).colorScheme`. `check_design_system.py` grades this info (DS-001), because the app has no theme tokens yet; adding a `ColorScheme` is the first step.

**Rule:** UI-helper-method, UI-mediaquery-of, UI-opacity, DS-001 raw-color-in-widget (`flutter-ui-practices` › flutter-ui.md §3, §4; `flutter-design-system`)

### 15. `warmUp()` throws its future away; `countItems()` chains `.then` (Low)
**Where:** `lib/features/cart/data/sources/cart_api.dart:35-36` (`getItems().then((items) => items.length);`), `:39` (`Future<int> countItems() => getItems().then(...)`)
**Rule:** UI-unawaited-future, ED-prefer-async-await (Effective Dart: PREFER async/await over raw futures)
**Why it matters:** in `warmUp()` the computed length goes nowhere, and the
future is neither awaited nor marked `unawaited`. It only works because
`getItems()` swallows every error (finding 4). Once that's fixed, an error here
would be unhandled. `countItems()` is fine at runtime, but reads better as
`async`/`await`.
**Fix:** `Future<void> warmUp() => fetchItems();`, awaited by the caller, or
delete it if nothing calls it (nothing does today).
`Future<int> countItems() async => (await fetchItems()).length;`

### 16. Grab-bag `utils.dart` with an unused `k` constant (Low)
**Where:** `lib/core/utils.dart:1-3` (`const kDefaultTimeout = Duration(seconds: 5);`)
**Rule:** NAME-grab-bag-file, NAME-prefix-letters (Effective Dart: DON'T use prefix letters). The project has no other `k` constants, so this isn't an established convention.
**Fix:** after findings 8 and 12 the file holds only this constant, and nothing
uses it. Delete it, or use it in the client's `BaseOptions` from finding 1 as
`defaultTimeout`.

### 17. The MVN layering is only half there (Info)
**Where:** `lib/features/cart/`
The checker reads this as MVN with low confidence (Riverpod plus a
`presentation/notifier/` folder, but 0 use cases). That folder holds only a
`StreamProvider` (`ticks_provider.dart`, which correctly releases its
subscription with `ref.onDispose`). There is a `CartRepository` contract and a
`CartRepositoryImpl`, but no use case and no notifier calls them, and
`CartView` is a plain `StatefulWidget` that talks to Dio. So
`clean_architecture: false` and `use_cases: false`. Fixing finding 1 the MVN way
(add a `fetchCartCount` use case and a `CartCountNotifier`) also completes the
layering. If the team doesn't want MVN, declare the pattern in `AGENTS.md`, and
the review will judge the code by that pattern's rules instead.

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
- Install `flutter-security-audit` next to the suite for the deep release
  checks (pinning, manifests, obfuscation) that this review skipped.

---

*Next step offered, not performed:* apply the mechanical fix, fix findings 1–4,
or fix a specific finding. After any change, rerun `scripts/review.sh` on the
touched files and compare the counts.
