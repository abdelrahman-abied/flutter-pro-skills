---
name: flutter-performance
description: Find and fix Flutter jank and wasted work, judged by the app's own architecture - rebuild scope per pattern (Riverpod select, BlocSelector and buildWhen, ListenableBuilder with child, Provider Selector, GetX Obx), const, RepaintBoundary, lazy lists and slivers, shrinkWrap, isolates and compute placed in the data layer, image decode sizing (cacheWidth, ResizeImage), saveLayer costs (Opacity, BackdropFilter, clips), animations, and DevTools diagnosis in profile mode (UI vs raster thread, rebuild counts, benchmarks). Ships a read-only PERF checker. Use it whenever someone says jank, lag, slow, stutter, dropped frames, choppy scrolling, too many rebuilds, the UI freezes while loading, or images eat memory, or when building or reviewing a long list, grid, feed or animation, even if they never say "performance". For widget correctness and lifecycle, load flutter-ui-practices instead.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.0"
  suite: flutter-pro-skills
---

# Flutter performance

> **Writing a standard feature?** If you're filling in a feature that
> `flutter-feature-scaffold` generated, its cross-cutting rules already cover
> this skill's write-time defaults (lists, images and rebuilds). You can stop reading here and check
> once at the end with `bash ../dart-flutter-review/scripts/review.sh <project-root> --diff HEAD --findings-only`.
> Read on when the work is about this area itself, or to fix a finding it reports.

Smooth Flutter apps come from a few habits applied in the right layer:
rebuild only what changed, build only what's visible, decode images at the
size they're shown, keep expensive paint effects out of lists, and keep
heavy CPU work off the UI isolate. This skill applies those habits in the
architecture the project already uses, and it never trades safety for
speed.

Three principles run through everything here:

- **Measure first.** Profile mode on a real device, then the DevTools
  Performance view. Debug-mode timings are meaningless
  (`references/diagnosing-jank.md`).
- **Fix in the pattern's own idiom.** A rebuild-scope fix is
  `ref.watch(p.select(...))` in MVN or Riverpod, `BlocSelector` in Bloc,
  `ListenableBuilder` with `child` in MVVM, `Selector` in Provider, a smaller
  `Obx` in GetX. Don't add a second state library to save a rebuild.
- **Heavy work belongs to the layer that owns the data.** Parsing and
  transforms go in sources and repositories (behind `Isolate.run` when
  they're big), never in widgets, and never in a view model or bloc just to
  be "off the widget".

This is the deep dive that `flutter-ui-practices` points to for performance.
For widget lifecycle, `BuildContext` after `await`, keys and helper methods,
load `flutter-ui-practices` (if your agent doesn't auto-load skills, read
`../flutter-ui-practices/SKILL.md`).

## Workflow

### 1. Detect the architecture, then run the checker

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern. A declared pattern wins. Then run the checker. It is
read-only, uses only the Python standard library, and doesn't need
`pub get`:

```bash
python3 -I <skill-dir>/scripts/check_performance.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_performance.py <project-root> --json              # schema flutter-pro-skills/performance@1
python3 -I <skill-dir>/scripts/check_performance.py <project-root> --files changed.txt # diff review
python3 -I <skill-dir>/scripts/check_performance.py <project-root> --profile bloc      # declared pattern wins
```

The CLI is `check_performance.py <project-root> [--json] [--files <list-file-or-comma-list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
It exits `0` whenever a report is produced and `2` on a usage error. It reads
the profile and file roles from the `flutter-architecture` checker
(`../flutter-architecture/scripts/arch_check.py --json`, reusing
`$FPS_ARCH_JSON` when `dart-flutter-review` already ran it). If that sibling
is missing, it falls back to path-based detection and says so on the
`classification:` line.

```text
== PERFORMANCE
  profile: mvn (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 9 files, 7 build methods, 2 lazy item builders (+1 item widgets one hop), 2 eager-capable scrollables, 2 network/file images
  [PERF-001] eager-list-over-data (medium) x1 — A scrollable builds one child per data item up front ...
      lib/features/feed/presentation/view/feed_view.dart:21  ListView( children: sorted.map((item) => ...   [ListView over `sorted`; MVN: keep the list in the notifier state and render ListView.builder(...)]
```

The checker finds candidates. It can't see frame times, so confirm a
Medium hit by reading the code, and a "this is slow" claim by profiling.

### 2. Measure in profile mode

```bash
flutter run --profile        # a physical device, ideally a low-end one
```

Open DevTools' Performance view and reproduce the jank. A long **UI** bar is
Dart work (build, layout, your sync code): fix rebuild scope, lists or heavy
work. A long **raster** bar is drawing: fix saveLayer effects, image sizes, or
(on the Skia backend) shader compilation. Turn on rebuild tracking and find
the widgets whose rebuild count climbs every frame. The full procedure,
debug flags and an `integration_test` benchmark with `traceAction` are in
`references/diagnosing-jank.md`.

### 3. Fix by the pattern

| Concern | MVN | Riverpod | MVVM | Bloc / Cubit | Provider | GetX | setState |
|---|---|---|---|---|---|---|---|
| rebuild one value | `ref.watch(p.select((s) => s.x))` | same; through `AsyncValue` with `valueOrNull?.x` | `ListenableBuilder(listenable: vm.cmd, child:)`, `ValueListenableBuilder` | `context.select`, `BlocSelector`, `buildWhen` | `context.select`, `Selector` | one `Obx` per leaf, `GetBuilder(id:)` | push state into a small `StatefulWidget` |
| heavy parse / transform | data source or repository impl (`Isolate.run`) | the repository behind the provider | service or repository | data provider or repository | the service | provider/repository | a service function |
| sorted/filtered lists | use case or notifier, exposed in state | a derived provider | view model | event handler before `emit` | the model | the controller | when the data arrives |
| scroll/animation visuals | widget (`ListenableBuilder` on the controller) | widget | widget | widget; add an event only on thresholds | widget | widget; `Rx` only on thresholds | widget, `setState` only on change |
| pagination | notifier method from "near end" | provider method | `Command` on the view model | event with `droppable()`/debounce | model method | controller method | `State` method |

Read `references/rebuild-scope.md` for each pattern in detail,
`references/lists-images-painting.md` for lists, slivers, images, saveLayer,
`RepaintBoundary` and animations, and `references/isolates.md` before
moving work to an isolate.

### 4. Verify

Re-run the checker, then re-profile the same interaction on the same device.
Report the before and after frame times with the fix.

## WRITE checklist

**Rebuilds**
1. **DO subscribe narrow and low**: select the field, put the builder at the
   leaf, and pass static subtrees as `child:` (PERF-008,
   `references/rebuild-scope.md`).
2. **DO use `const`** for static subtrees. Don't file a finding per missing
   `const` (the lints are off by default in `flutter_lints`).
3. **AVOID `setState` per scroll offset or animation tick** (PERF-009). Use
   `ListenableBuilder` on the controller, or `setState` only when a derived
   value flips.
4. **DO keep `build()` pure and cheap**: no sorting (PERF-010), filtering of
   big lists, parsing or allocation of keys (PERF-007) in `build`.

**Lists and layout**
5. **DO use builder constructors for data** (PERF-001), with `itemExtent` or
   `prototypeItem` for uniform rows.
6. **PREFER one `CustomScrollView` with slivers** over nested scrollables with
   `shrinkWrap: true` (PERF-002).
7. **AVOID `IntrinsicHeight`/`IntrinsicWidth` in list items** (PERF-003).

**Images and painting**
8. **DO decode images at display size** in lists and grids: `cacheWidth`,
   `ResizeImage`, `memCacheWidth` (PERF-004).
9. **AVOID `Opacity` in animations** (use `FadeTransition`/`AnimatedOpacity`)
   **and per list item** (use a translucent colour) (PERF-005).
10. **AVOID `BackdropFilter`, `ShaderMask` and `ClipPath` per list item**
    (PERF-006). Blur once behind the list. Prefer `borderRadius` to clips.
11. **CONSIDER `RepaintBoundary`** only around a part that repaints
    independently (spinner, clock, video). Verify with "Highlight repaints".
    List items already have one.

**Work off the UI isolate**
12. **DO parse large or unbounded JSON lists in the data layer with
    `Isolate.run` or `compute`** (PERF-011). Widgets, view models, blocs and
    notifiers only await the result.
13. **DO measure before moving work.** Small payloads are cheaper inline.

## Secure by default

Performance work tempts shortcuts. Don't take them:

- **Never disable TLS or certificate checks** (`badCertificateCallback =>
  true`, a permissive `HttpOverrides`) to speed up a cache or a CDN. That's
  SEC territory: load `flutter-secure-defaults` (or read
  `../flutter-secure-defaults/SKILL.md`).
- **Send isolates only what they compute on.** Pass the response body, not
  the HTTP client, the repository or a token. A closure that captures `this`
  ships the whole object, secrets included (`PERF-secret-in-isolate`,
  `references/isolates.md` §4).
- **No payload logging in hot paths or isolates.** A `print` in an item
  builder, a scroll listener or a parser runs constantly and puts PII in the
  device log (SEC-004). Log counts and durations.
- **Don't cache authenticated images or responses in public storage** to
  make them load faster. Auth headers go through the app's interceptor, and
  private caches stay in app-private directories.
- **Remove debug flags** (`debugProfileBuildsEnabled`,
  `debugRepaintRainbowEnabled`, `showPerformanceOverlay`) before committing.

## REVIEW checklist

Script rules (`PERF-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| PERF-001 | eager-list-over-data | Medium (Low if mixed with fixed children or horizontal) | `ListView(children: data.map(...))`, `List.generate(data.length, ...)`, a data `Column` in a `SingleChildScrollView` |
| PERF-002 | shrinkwrap-nested-scrollable | Medium for builder lists, Low otherwise | `shrinkWrap: true` list inside another scroll view or list item |
| PERF-003 | intrinsic-in-list-item | Medium | `IntrinsicHeight`/`IntrinsicWidth` in an item builder (or one hop into the item widget) |
| PERF-004 | image-full-size-decode-in-list | Low | list-item images without `cacheWidth`/`ResizeImage`/`memCacheWidth` |
| PERF-005 | opacity-animated-or-in-list | Low | `Opacity` driven by an animation, or per list item |
| PERF-006 | savelayer-in-list-item | Medium (`BackdropFilter`), Low (`ShaderMask`, `ClipPath`) | offscreen-layer or path-clip widgets per list item |
| PERF-007 | global-key-in-build | Medium | `GlobalKey()` constructed in `build()` or an item builder |
| PERF-008 | watch-whole-for-one-field | Low | `ref.watch(p).x`, `context.watch<T>().x`, `context.watch<B>().state.x` in a widget build |
| PERF-009 | setstate-per-frame-listener | Medium (scroll), Low (animation) | unconditional `setState` in a scroll or animation listener |
| PERF-010 | sort-in-build | Low | `.sort()` inside a widget `build()` |
| PERF-011 | json-decode-on-ui-isolate | Info | `jsonDecode(...) as List` in a source/repository, outside `Isolate.run`/`compute` |

Reading-level findings (`PERF-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| PERF-secret-in-isolate | High | tokens, clients or whole repositories sent to an isolate |
| PERF-rebuild-scope | Medium | a page-root `BlocBuilder`/`Obx`/`Consumer`/`setState` for one value; `ListenableBuilder` without `child` |
| PERF-heavy-build | Medium | filtering, grouping, regex or formatting of big lists in `build()` |
| PERF-isolate-in-ui | Medium | `compute`/`Isolate.run` in a widget, view model, bloc or notifier |
| PERF-log-in-hot-path | Medium | logging in builders, item builders, listeners or isolate loops |
| PERF-missing-item-extent / PERF-repaint-boundary / PERF-animation-offscreen | Low | see `references/rules.md` §3 |
| PERF-unmeasured-claim | Info | a performance change with no profile-mode numbers |

**Don't report here (cross-reference instead):**
- `MediaQuery.of(context).x`, `UniqueKey()` in build, a `FutureBuilder`
  future made in build, `Widget _buildX()` helpers: the `dart-flutter-review`
  heuristics `mediaquery-of`, `unique-key`, `future-in-build` and
  `widget-helper-method` own them (with the `UI-*` slugs).
- `jsonDecode` or HTTP inside a widget: ARCH-101 first (it's an architecture
  violation before it's a performance one).
- tokens or PII in logs: SEC-004; undisposed controllers: `UI-lifecycle`.

**Dedupe.** When this checker ran, PERF findings replace the heuristics
`eager-children-map` and `opacity-widget`, and beat `UI-eager-list`,
`UI-opacity`, `UI-image-decode-size`, `UI-blocking-ui-isolate`,
`UI-rebuild-scope` and `UI-build-side-effect` (sort in build) for the same
file and line. Cite the dropped slug in `rule:`.

**When not to flag:**
- Small fixed children (`[a, b, c]`, enum values, `List.generate(5, ...)`), a
  form in a `SingleChildScrollView`, a short horizontal chip strip.
- Full-size images and blurs in `PageView` pages, detail and zoom views.
- A static `Opacity` outside lists and animations.
- `ref.watch(p)` reading one field in a provider's or notifier's own `build()`.
- Listeners on text controllers, focus nodes and value notifiers.
- Small JSON payloads decoded inline: PERF-011 is Info for a reason.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [MEDIUM] Feed builds every post up front
- id: PERF-001
- where: lib/features/feed/presentation/view/feed_view.dart:21
- evidence: `ListView(children: state.items.map((p) => PostTile(post: p)).toList())`
- rule: build lazily (flutter-performance › lists-images-painting.md §1); supersedes UI-eager-list
- why: 2,000 posts are built and laid out on the first frame; the profile showed a 180 ms UI-thread frame on open
- fix: |
    ListView.builder(
      itemCount: state.items.length,
      itemBuilder: (context, i) => PostTile(post: state.items[i]),
    )
- confidence: confirmed

### [LOW] Settings tile rebuilds on every preference change
- id: PERF-008
- where: lib/src/view/settings/sound_tile.dart:18
- evidence: `final enabled = ref.watch(preferencesProvider).isSoundEnabled;`
- rule: MVN: select the field (flutter-performance › rebuild-scope.md §2)
- why: any preference change (theme, board, language) rebuilds this tile
- fix: |
    final enabled = ref.watch(preferencesProvider.select((p) => p.isSoundEnabled));
- confidence: confirmed
```

Open the report with one line naming the profile and how you measured
(`mvn, profiled on a Pixel 4a in profile mode`). Report a pattern-wide
issue (no list image in the app is decode-sized) **once**, with a few
locations.

## Official guidance

Defer to the Flutter team's own material for step-by-step tooling: the
docs.flutter.dev performance pages ("Performance best practices", "Flutter
performance profiling", "Use the Performance view", "Parse JSON in the
background") and, if installed, the official `flutter/agent-plugins` skills
and `dart-lang/skills`. This skill adds per-architecture placement, the
review checklist and the checker.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-ui-practices`** for widget lifecycle, keys, `build()` purity and
  the `UI-*` slugs. Fallback: `../flutter-ui-practices/SKILL.md`.
- **`flutter-architecture`** for detecting the pattern and where layers
  begin. Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-secure-defaults`** for TLS, token handling and logging policy
  (SEC-004). Fallback: `../flutter-secure-defaults/SKILL.md`.
- **`flutter-error-handling`** for mapping isolate and parse failures to
  typed errors. Fallback: `../flutter-error-handling/SKILL.md`.
- **`flutter-testing`** for widget tests and `integration_test` setup.
  Fallback: `../flutter-testing/SKILL.md`.
- **`dart-flutter-review`** merges PERF findings into its report (section
  `== PERFORMANCE`).

## References

| File | Read it when |
|---|---|
| `references/rebuild-scope.md` | narrowing rebuilds in MVN, Riverpod, Bloc, MVVM, Provider, GetX or setState; `const`, `child:` |
| `references/lists-images-painting.md` | lazy lists and slivers, `shrinkWrap`, intrinsics, image decode sizing, saveLayer, `RepaintBoundary`, animations |
| `references/isolates.md` | moving work off the UI isolate: `Isolate.run` vs `compute`, which layer calls it, what it may receive |
| `references/diagnosing-jank.md` | profiling: profile mode, UI vs raster thread, rebuild counts, debug flags, Impeller, `traceAction` benchmarks |
| `references/rules.md` | every PERF rule: detection, why, bad/good code, false positives, suppression, calibration |
