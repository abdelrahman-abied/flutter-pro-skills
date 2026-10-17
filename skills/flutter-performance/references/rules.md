# PERF rules: what the checker reports, and why

`scripts/check_performance.py` is static and read-only. It needs only the
Python standard library and no `pub get`. Every hit is a candidate: read the
code before you call a finding `confirmed`, and measure in profile mode
before you call it a regression (`diagnosing-jank.md`). Each rule lists the
false positives calibration found and how the rule avoids them.

## Contents

1. How "list item", "build" and "data" are recognised
2. PERF-001 … PERF-011
3. Reading-level findings (PERF-<slug>)
4. What this skill deliberately doesn't check (and who does)
5. Suppression
6. Calibration

## 1. How the checker sees the code

- **List item.** Code inside the `itemBuilder` (or `builder`, or the first
  positional argument of a `*BuilderDelegate`) of a lazy list or grid:
  `ListView.builder/.separated`, `GridView.builder`, `SliverList`,
  `SliverGrid`, `ReorderableListView.builder`, `AnimatedList`,
  `SliverChildBuilderDelegate`, `MasonryGridView`, `PagedListView` and other
  `*List`/`*Grid` widgets. **One hop:** a project widget constructed directly
  inside such an item builder counts too, in whichever file it is declared
  (its `build` and its `State`). The note names the hop
  (`in PostTile, built in the ListView.builder itemBuilder of …`).
  `PageView`, `TabBarView` and carousels aren't lists: their items are
  full-screen pages, where a full-size decode or a blur is expected.
- **build().** A method named `build` in a widget or `State` class. A
  `Notifier`/provider `build()` is not a widget build and is skipped by
  PERF-008 and PERF-010.
- **Plausibly unbounded data.** A collection that isn't a list literal, an
  enum's `.values`, a `const`/`final … = [ … ]` list in the same file, a
  `SCREAMING_CASE`/`kName` constant, or `.take(n)`. `List.generate(n, …)` only
  counts when `n` is `<collection>.length`.
- **Layers.** UI rules run on presentation/app/core files; PERF-011 runs only on
  data-layer files (sources, services, repositories). Roles come from
  `flutter-architecture`'s `arch_check.py --json` (`files[]`), with a
  path-based fallback. `barrel`, `di` and generated files are skipped.

## 2. Rules

| ID | Name | Default severity | Detects |
|---|---|---|---|
| PERF-001 | eager-list-over-data | Medium (Low when mixed with fixed children or horizontal) | `ListView`/`GridView`/`GridView.count`, or a `Column`/`Row`/`Wrap` inside a `SingleChildScrollView`, whose `children` come from `data.map(…)`, `List.generate(data.length, …)`, `...data.map(…)` or `for (… in data)` |
| PERF-002 | shrinkwrap-nested-scrollable | Medium for a builder list, Low for a children list or horizontal | `shrinkWrap: true` on a list or grid that is inside another scroll view or a list item |
| PERF-003 | intrinsic-in-list-item | Medium | `IntrinsicHeight`/`IntrinsicWidth` in a list item |
| PERF-004 | image-full-size-decode-in-list | Low | `Image.network/file/memory`, `NetworkImage`, `FileImage`, `CachedNetworkImage` … in a list item with no `cacheWidth`/`cacheHeight`/`memCacheWidth`/`ResizeImage` |
| PERF-005 | opacity-animated-or-in-list | Low | `Opacity` inside `AnimatedBuilder`/`TweenAnimationBuilder`/an `AnimatedWidget`, or driven by `animation.value`; or a non-0/1 `Opacity` in a list item |
| PERF-006 | savelayer-in-list-item | Medium for `BackdropFilter`, Low for `ShaderMask`/`ClipPath` | those widgets in a list item |
| PERF-007 | global-key-in-build | Medium | `GlobalKey(…)` constructed inside `build()` or an item builder (not `??=`, not `useMemoized`) |
| PERF-008 | watch-whole-for-one-field | Low | in a widget `build()`: `ref.watch(p).field`, `context.watch<T>().field`, `context.watch<B>().state.field`, `Provider.of<T>(context).field` |
| PERF-009 | setstate-per-frame-listener | Medium for scroll, Low for animation | `scrollController.addListener(…)` / `animationController.addListener(…)` whose callback calls `setState` unconditionally |
| PERF-010 | sort-in-build | Low | `.sort(` / `..sort(` inside a widget `build()` |
| PERF-011 | json-decode-on-ui-isolate | Info | `jsonDecode(…) as List` in a data-layer file, outside `Isolate.run`/`compute` |

### PERF-001 eager-list-over-data

**Medium** (Low when the list mixes fixed children with one data loop, or
scrolls horizontally) · all profiles

**Detects:** a scrollable that takes `children:` built from a data collection.
Bounded sources (literal lists, enum values, constants, `List.generate(5, …)`,
counts that aren't `.length`) are skipped.
**Why:** `ListView(children: …)` and `Column` in a `SingleChildScrollView`
build, lay out and keep alive every item, including the thousands off screen.
Builder constructors build only what's visible plus `cacheExtent`.

```dart
// Bad: every order is built on first frame
ListView(children: orders.map((o) => OrderTile(order: o)).toList());

// Good
ListView.builder(
  itemCount: orders.length,
  itemExtent: 72,                       // fixed height: no per-item measuring
  itemBuilder: (context, i) => OrderTile(order: orders[i]),
);
```

**Profile notes:** the note carries the fix for the detected pattern: the
list comes from the notifier state (MVN), a watched provider (Riverpod),
`ListenableBuilder` over the view model (MVVM), `BlocBuilder`/`BlocSelector`
(Bloc), `context.select` (Provider), `Obx` around the builder (GetX).
**Mixed lists** (a header, a search field, then the data): use a
`CustomScrollView` with `SliverToBoxAdapter`s and one `SliverList.builder`.
That's why calibration graded them Low: the eager part is real, the fix is
a restructure.
**False positives:** a list known to be small but held in a variable (a
settings screen's four sections). Suppress it with the reason, or make it a
`const` list.

### PERF-002 shrinkwrap-nested-scrollable

**Medium** for `.builder`/`.separated` (laziness lost), **Low** for a children
list or a horizontal strip · all profiles

**Detects:** `shrinkWrap: true` on `ListView`/`GridView`/`CustomScrollView`/
`ReorderableListView` when an ancestor call is a scroll view
(`ListView`, `SingleChildScrollView`, `CustomScrollView`, `SliverToBoxAdapter`,
`NestedScrollView` …) or the list is in a list item.
**Why:** a shrink-wrapped list must lay out every child to know its own
height, so a builder list nested this way builds all of its items, on every
layout of the outer list.

```dart
// Bad
ListView(children: [const Header(), ListView.builder(shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), itemCount: users.length, itemBuilder: …)]);

// Good: one scrollable, slivers inside
CustomScrollView(slivers: [
  const SliverToBoxAdapter(child: Header()),
  SliverList.builder(itemCount: users.length, itemBuilder: …),
]);
```

**False positives:** a shrink-wrapped list in a bottom sheet or dialog that
isn't itself inside a scroll view is not flagged. A nested list that is
genuinely tiny (three chips) is a Low or a suppression.

### PERF-003 intrinsic-in-list-item

**Medium** · all profiles

**Detects:** `IntrinsicHeight`/`IntrinsicWidth` in a list item (including one
hop into the item widget).
**Why:** intrinsic sizing lays the subtree out speculatively before the real
layout. In a list item that cost repeats for every item on every layout, and
nested intrinsics go quadratic.
**Fix:** give the row a fixed or min height (`SizedBox`, `ConstrainedBox`),
use `CrossAxisAlignment.stretch` inside a sized parent, a `Table`, or a
custom `MultiChildLayoutDelegate`.
**False positives:** intrinsics outside lists (a dialog's button row) are
not flagged.

### PERF-004 image-full-size-decode-in-list

**Low** · all profiles

**Detects:** an image constructor or provider in a list item without decode
sizing: `cacheWidth`/`cacheHeight` (Image), `memCacheWidth`/`memCacheHeight`
or `maxWidthDiskCache` (cached_network_image), or a surrounding `ResizeImage`.
**Why:** the engine decodes the full source resolution unless told otherwise.
A 4000×3000 photo shown as a 64 px thumbnail costs ~48 MB of decoded pixels
and decode time on a worker thread, and it evicts the rest of the image
cache. `width:`/`height:` only size the widget, not the decode.

```dart
// Bad
Image.network(url, width: 64, height: 64, fit: BoxFit.cover);

// Good
final px = (64 * MediaQuery.devicePixelRatioOf(context)).round();
Image.network(url, width: 64, height: 64, fit: BoxFit.cover, cacheWidth: px);
CachedNetworkImage(imageUrl: url, width: 64, height: 64, memCacheWidth: px);
Image(image: ResizeImage(NetworkImage(url), width: px, policy: ResizeImagePolicy.fit));
```

**False positives:** a server that already returns thumbnails sized for the
slot (an avatar endpoint with `?s=64`). Suppress with the reason. Low
severity because the checker can't see the source resolution; turn on
`debugInvertOversizedImages = true` in a debug run to see which ones matter.

### PERF-005 opacity-animated-or-in-list

**Low** · all profiles

**Detects:** `Opacity` whose `opacity:` isn't a literal and that sits inside
`AnimatedBuilder`/`TweenAnimationBuilder`, inside an `AnimatedWidget`, or is
driven by `<animation|controller>.value`; or an `Opacity` with a value other
than 0 or 1 in a list item.
**Why:** the Flutter performance guide says to avoid `Opacity`, particularly in
animations. Intermediate values composite the whole subtree into an
offscreen layer, and the builder rebuilds it every tick. `FadeTransition` and
`AnimatedOpacity` animate the layer's alpha without a rebuild.

```dart
// Bad
AnimatedBuilder(animation: _c, builder: (_, child) => Opacity(opacity: _c.value, child: child), child: const Logo());

// Good
FadeTransition(opacity: _c, child: const Logo());
```

For static translucency in list items, paint with a translucent colour
(`color.withValues(alpha: 0.6)`) or use the theme's disabled colours. A
static `Opacity` outside lists and animations isn't flagged: its cost is one
layer, once.
**False positives:** a one-shot splash fade measured as cheap. Suppress the
file with the measurement in the reason.

### PERF-006 savelayer-in-list-item

**Medium** for `BackdropFilter`, **Low** for `ShaderMask` and `ClipPath` · all profiles

**Detects:** those widgets in a list item. A `ClipPath` with
`clipBehavior: Clip.hardEdge` or `Clip.none` is skipped.
**Why:** `BackdropFilter` reads back and blurs everything behind it: one
offscreen pass per visible item, every frame while scrolling. `ShaderMask`
needs a saveLayer for its subtree. `ClipPath` clips along an arbitrary path
(and saves a layer with `Clip.antiAliasWithSaveLayer`). In a list these
multiply by the number of visible items.
**Fix:** blur once behind the whole list (one `BackdropFilter` under a
`Stack`), use a pre-blurred image, bake gradients into assets, use
`ClipRRect`/`borderRadius` for rounded corners.
**False positives:** a single highlighted item that alone has the effect.
Suppress it with the reason.

### PERF-007 global-key-in-build

**Medium** · all profiles

**Detects:** `GlobalKey(…)`/`GlobalKey<T>(…)` constructed in `build()` or an
item builder, unless cached (`_key ??= GlobalKey()`) or memoised
(`useMemoized(() => GlobalKey<FormState>())`).
**Why:** a new key on every build tells the framework the subtree is a new
widget: its `State` is discarded and remounted (a `Form` loses its field
state and validation), and every global key churns the registry.
Calibration found `final formKey = GlobalKey<FormState>();` inside hook
widgets' `build`, which resets the form on every rebuild.
**Fix:** a `final` field in the `State`, `useMemoized(GlobalKey<FormState>.new)`
in hooks, or a `ValueKey(item.id)` when you only need identity.
**Related:** `UniqueKey()` in build is the `unique-key` heuristic
(`dart-flutter-review`), not this rule.

### PERF-008 watch-whole-for-one-field

**Low** · riverpod and mvn (`ref.watch`), provider (`context.watch`,
`Provider.of`), bloc (`context.watch<B>().state.x`)

**Detects:** in a widget `build()`, a watch whose result is used for exactly
one field, and the same object isn't watched elsewhere in that build.
`AsyncValue` members (`value`, `valueOrNull`, `isLoading`, `when` …), collection
members, `.notifier` and `.select` are skipped.
**Why:** the widget rebuilds on every change of any field of the object.

```dart
// Bad
final isSoundEnabled = ref.watch(generalPreferencesProvider).isSoundEnabled;
// Good
final isSoundEnabled = ref.watch(generalPreferencesProvider.select((p) => p.isSoundEnabled));

// Bloc
final status = context.select((CartBloc b) => b.state.status);
// Provider
final count = context.select((CartModel m) => m.count);
```

**False positives:** objects that change all at once anyway (a settings
snapshot that's replaced wholesale). The finding is still cheap to apply.
Provider `build()` methods (a `Notifier.build` composing other providers)
are not widget rebuilds and are skipped (calibration).

### PERF-009 setstate-per-frame-listener

**Medium** for scroll and page controllers, **Low** for animation controllers · all profiles

**Detects:** `x.addListener(cb)` where `x` is declared or created as a
`ScrollController`/`PageController` (scroll) or an `AnimationController`/
`Animation` (animation), or has `scroll`/`anim` in its name when no type is
visible, and `cb` (inline, or a method in the same class) calls `setState`
outside any `if`/`else`/`?:`.
**Why:** scroll listeners fire for every pixel of offset, animation
listeners on every tick. An unconditional `setState` rebuilds the whole
`State`'s subtree at that rate.

```dart
// Bad
_scroll.addListener(() => setState(() => _offset = _scroll.offset));

// Good: rebuild only on the threshold crossing
_scroll.addListener(() {
  final collapsed = _scroll.offset > 120;
  if (collapsed != _collapsed) setState(() => _collapsed = collapsed);
});
// or rebuild only the dependent widget
ListenableBuilder(listenable: _scroll, builder: (context, child) => …, child: const ExpensiveBody());
```

**Profile notes:** Bloc should add an event only on a threshold crossing
(load more), never per offset. GetX updates an `Rx` only when the derived
value flips. The view model, notifier or bloc never sees raw scroll offsets.
**False positives:** listeners on `TextEditingController`, `FocusNode`,
`ValueNotifier` subclasses named `*Controller` (calibration: a panel
controller that toggles on taps) are not per-frame and are skipped by type.

### PERF-010 sort-in-build

**Low** · all profiles

**Detects:** `.sort(` or `..sort(` inside a widget `build()`.
**Why:** O(n log n) work on every rebuild, and `List.sort` mutates in place:
sorting `widget.items` or `state.items` changes data the widget doesn't own,
which surprises the state layer (and `==`-based rebuild skipping). The note
says when the receiver is such a list.
**Fix:** sort once where the data changes: the use case or notifier (MVN), a
derived provider (Riverpod), the view model (MVVM), the event handler before
`emit` (Bloc), the controller (GetX).
**False positives:** immutable collections whose `sort` returns a copy
(`IList`) still pay the cost per build, so they stay Low findings.

### PERF-011 json-decode-on-ui-isolate

**Info** · all profiles

**Detects:** `jsonDecode(…)`/`json.decode(…)` whose result is cast or assigned
to a `List` in a data-layer source, service or repository, when it isn't inside
`Isolate.run(…)`/`compute(…)` (or a function passed to them), and isn't in a
`fromJson` factory.
**Why:** decoding is synchronous. A multi-megabyte list payload decoded on
the UI isolate drops frames (docs.flutter.dev cookbook "Parse JSON in the
background").

```dart
// Good: still in the data source, now off the UI isolate
Future<List<Post>> fetchPosts() async {
  final body = (await _client.get(uri)).body;
  return Isolate.run(() => (jsonDecode(body) as List).map((j) => Post.fromJson(j as Map<String, dynamic>)).toList());
}
```

Info, because most payloads are small (calibration: compass_app's API
client decodes short lists inline, as the sample intends). Escalate only
when profiling shows the decode on the UI thread. Read `isolates.md` for
where the isolate call goes in each architecture and what it may receive.

## 3. Reading-level findings (`PERF-<slug>`)

The checker can't see these. Report them from reading, in the suite's
finding format.

| ID | Severity | Look for |
|---|---|---|
| PERF-rebuild-scope | Medium | a whole screen rebuilt for one value: `BlocBuilder` with no `buildWhen` at the page root, one `Obx` around a screen, `ListenableBuilder` without `child`, `setState` at the root (`rebuild-scope.md`) |
| PERF-heavy-build | Medium | filtering, grouping, regex, date formatting of big lists in `build()` |
| PERF-isolate-in-ui | Medium | `compute`/`Isolate.run` called from a widget or view model instead of the data layer |
| PERF-secret-in-isolate | High | a token, API key, Dio/http client or the whole repository sent to an isolate that only needs the payload |
| PERF-log-in-hot-path | Medium | `print`/logger calls in `build`, item builders, scroll listeners or isolate loops, especially with payloads (and SEC-004 if they carry PII or tokens) |
| PERF-missing-item-extent | Low | a long uniform list without `itemExtent`/`prototypeItem` (scrollbar jumps, `jumpTo` lays out every item) |
| PERF-repaint-boundary | Low | `RepaintBoundary` everywhere (layer memory) or missing around a ticking widget next to static content (`lists-images-painting.md` §4) |
| PERF-animation-offscreen | Low | `AnimationController.repeat()` that keeps ticking when its route or tab isn't visible |
| PERF-unmeasured-claim | Info | a performance change justified without a profile-mode measurement |

## 4. What this skill deliberately doesn't check (and who does)

| Concern | Owner |
|---|---|
| `MediaQuery.of(context).size` | heuristic `mediaquery-of` / `UI-mediaquery-of` |
| `UniqueKey()` in build | heuristic `unique-key` / `UI-keys` |
| `FutureBuilder(future: load())` in build | heuristic `future-in-build` / `UI-future-in-build` |
| `Widget _buildX()` helper methods | heuristic `widget-helper-method` / `UI-helper-method` |
| `jsonDecode`/HTTP inside a widget | ARCH-101 (architecture first; then move it off the UI isolate) |
| tokens or PII in logs | SEC-004, FORM-004 |
| undisposed controllers | heuristic `undisposed-resource` / `UI-lifecycle` |

**Superseded when this checker ran** (CONTRACTS §23): the heuristics
`eager-children-map` and `opacity-widget` keep only their count and point at
PERFORMANCE. PERF findings beat `UI-eager-list`, `UI-opacity`,
`UI-image-decode-size`, `UI-blocking-ui-isolate`, `UI-rebuild-scope` and
`UI-build-side-effect` (for a sort in build) on the same file and line; cite
the dropped slug in `rule:`.

## 5. Suppression

- `// perf-ignore: PERF-004 avatars come pre-sized from the CDN` on the reported
  line or the line above.
- `// perf-ignore-file: PERF-005 one-shot splash fade, measured at 1 ms` anywhere
  in the file.

Several IDs may share a comment (`PERF-001, PERF-002`). Suppressed hits are
listed under `suppressed` in the JSON with their reason; the text report
ends with `suppressed: N (see --json)`.

## 6. Calibration

Run on the canonical reference apps (exit criterion: zero High or Medium
false positives) and on two large non-canonical apps. Each bloc and riverpod
example was run as its own project. Hits are after the fixes below.

| App | Commit | Profile | Hits by rule | Judged |
|---|---|---|---|---|
| flutter/samples `compass_app` | flutter/samples@5541c59 | mvvm | PERF-004 ×4 (low), PERF-011 ×5 (info) | all TP: `CachedNetworkImage` without `memCacheWidth` in list cards (one shown at 80 px); list payloads decoded inline (info, as designed) |
| felangel/bloc `examples/*` (19 projects) | felangel/bloc@b9be1e2 | bloc | PERF-004 ×1 (low) | TP: full-size `Image.network` avatar in the github_search result tile |
| rrousselGit/riverpod `examples/*` (7 projects) | rrousselGit/riverpod@1efba1c | riverpod | PERF-005 ×1 (low), PERF-001 ×1 (low) | TP: `Opacity` in a `TweenAnimationBuilder` (marvel); todos list mixed with a header (todos) |
| immich-app/immich `mobile/` | immich-app/immich@188d64e | riverpod | PERF-001 ×3 (low), PERF-002 ×2 (medium) ×4 (low), PERF-004 ×1, PERF-005 ×3, PERF-007 ×3 (medium), PERF-008 ×13 (low) | all TP after fixes; the medium PERF-007s are form keys recreated in hook widgets' `build` |
| lichess-org/mobile | lichess-org/mobile@99e1fb7 | riverpod | PERF-001 ×3 (medium) ×15 (low), PERF-002 ×2 (medium), PERF-008 ×8, PERF-009 ×1 (medium), PERF-010 ×5, PERF-011 ×2 (info) | all TP after fixes (eager lists over teams/openings/moves, nested builder lists, a `PageController` listener rebuilding the screen per frame) |
| gskinnerTeam/flutter-wonderous-app | gskinnerTeam/flutter-wonderous-app@747b945 | provider | PERF-001 ×1 (medium), PERF-004 ×1, PERF-005 ×1 | TP (an unbounded debug log list; a masonry tile image; an animated cloud `Opacity`) |

**False-positive causes fixed** (each has a `calib_<app>` regression fixture
with the related true positive asserted next to it):

| Cause | Rule | Fix | Fixture |
|---|---|---|---|
| `List.generate(_imgCount, …)` in a fixed, non-scrolling 5×5 grid | PERF-001 (medium) | `List.generate` only counts as data when its count is `<collection>.length` | `calib_wonderous` |
| `PanelController extends ValueNotifier<bool>` listener matched by the name `*Controller` | PERF-009 (low) | classify by the declared type first; unknown types need `scroll`/`anim` in the name | `calib_wonderous` |
| `TextEditingController` listeners (`albumTitleController`, `inputController`) | PERF-009 (low) | same: only scroll/page and animation types count | `calib_immich` |
| `ref.watch(service).field` inside a `Notifier.build()` | PERF-008 (low) | only widget and `State` `build()` methods | `calib_lichess` |
| a todo `ListView` that mixes a title, a text field and a data loop graded Medium | PERF-001 (severity) | mixed fixed + data children are Low, data-only children stay Medium | `calib_riverpod_todos` |
