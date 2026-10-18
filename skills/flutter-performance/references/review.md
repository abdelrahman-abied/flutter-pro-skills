# flutter-performance: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

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
