# Lists, images, painting and animations

The frame budget is about 16 ms at 60 Hz and 8 ms at 120 Hz, split between
the UI thread (build, layout, paint recording) and the raster thread
(drawing). Lists multiply every per-item cost by the number of visible
items, and scrolling repeats it every frame. Most jank in real apps lives
here.

## Contents

1. Lazy lists and slivers
2. Layout costs: shrinkWrap and intrinsics
3. Images: decode at display size
4. Painting: saveLayer, Opacity, clips and RepaintBoundary
5. Animations

## 1. Lazy lists and slivers

- **DO use builder constructors for data:** `ListView.builder`,
  `ListView.separated`, `GridView.builder`, `SliverList.builder`,
  `SliverGrid.builder`. They build only what's visible plus `cacheExtent`
  (PERF-001).
- **PREFER `itemExtent` or `prototypeItem`** when items share a height. The
  list then knows its scroll extent without laying out items, so scrollbars
  are stable and `jumpTo` doesn't lay out every item in between.
- **DO give reorderable or animated items a stable `ValueKey(item.id)`.**
- **PREFER one `CustomScrollView`** for pages with headers, carousels and a
  feed: `SliverAppBar`, `SliverToBoxAdapter`, `SliverList.builder`,
  `SliverGrid.builder`, `SliverPersistentHeader`.
- **CONSIDER `addAutomaticKeepAlives: false`** for long lists of cheap items
  that don't need to keep state off screen.
- Pagination belongs to the logic layer: the view reports "near the end"
  (the item builder reaching `items.length - 5`, or a threshold in a scroll
  listener) and the notifier, view model, bloc or controller fetches the next
  page. Bloc: debounce or `droppable()` the fetch event.

## 2. Layout costs: shrinkWrap and intrinsics

- **AVOID `shrinkWrap: true` inside another scrollable** (PERF-002). A
  shrink-wrapped list lays out all of its children to measure itself, so a
  nested builder list stops being lazy. Use slivers instead.
- **AVOID `IntrinsicHeight`/`IntrinsicWidth` in list items** (PERF-003). They
  add a speculative layout pass per item, and nesting goes quadratic.
- A `Column` in a `SingleChildScrollView` is fine for a form or a settings
  page with fixed content. It's an eager list as soon as its children come
  from data.
- **DO prefer `MediaQuery.sizeOf`** and friends to `MediaQuery.of`
  (heuristic `mediaquery-of`). `LayoutBuilder` only when the layout really
  depends on the parent's constraints.

## 3. Images: decode at display size

- **DO set `cacheWidth` or `cacheHeight`** (one is enough, the aspect ratio
  is kept) to `logicalSize * MediaQuery.devicePixelRatioOf(context)`, or wrap
  the provider in `ResizeImage` (PERF-004). `width:`/`height:` size the
  widget, not the decode.
- **cached_network_image:** `memCacheWidth`/`memCacheHeight` size the decoded
  image, `maxWidthDiskCache` the stored file.
- **PREFER thumbnails from the server** for grids (`?w=200`), and full
  resolution only in the detail or zoom view.
- **CONSIDER `precacheImage`** for the next page's hero image, and
  `FadeInImage`/`frameBuilder` instead of `Opacity` for fade-in.
- Debug aid: `debugInvertOversizedImages = true` inverts the colours of any
  image decoded much larger than it's displayed. Remove it before
  committing.
- **Secure by default:** don't disable TLS verification or certificate checks
  to make an image cache "faster", and don't cache authenticated images to
  public storage. Auth headers go through the app's HTTP client or
  interceptor (`flutter-secure-defaults`).

## 4. Painting: saveLayer, Opacity, clips and RepaintBoundary

`saveLayer` renders a subtree into an offscreen buffer and composites it back.
It's the most expensive common paint operation, worst on older GPUs and in
lists.

| Widget | Cost | Cheaper alternative |
|---|---|---|
| `Opacity` (0 < value < 1) | offscreen layer for the subtree | translucent colour; `FadeTransition`/`AnimatedOpacity` for animation (PERF-005) |
| `BackdropFilter` | reads back and blurs what's behind it | one blur behind the whole list; a pre-blurred image (PERF-006) |
| `ShaderMask`, `ColorFilter` | offscreen layer | bake into the asset; apply once outside the list |
| `ClipPath` | path clipping (`Clip.antiAliasWithSaveLayer` adds a layer) | `ClipRRect`/`borderRadius`, `ShapeDecoration`, `Clip.hardEdge` |
| `ClipRRect` | cheaper than a path; still a clip per item | `BoxDecoration(borderRadius:)` with `clipBehavior: Clip.none` when content doesn't overflow |
| shadows on many items | blur per item | `Material(elevation:)` for small counts, a pre-rendered shadow asset |

**`RepaintBoundary`** gives a subtree its own layer, so repainting it doesn't
repaint its neighbours, and vice versa.

- **It helps** when a small part repaints often and independently: a
  spinner, a ticking clock, a progress ring, a video or map next to static
  content, or a complex static background under an animation.
- **It hurts** when everything repaints together anyway, or when it's
  sprinkled everywhere: each boundary is an extra layer (GPU memory,
  compositing work).
- List and grid items already get one each (`addRepaintBoundaries: true`), so
  don't add your own around items.
- **DO verify** with DevTools' "Highlight repaints" (or
  `debugRepaintRainbowEnabled = true`): a boundary is worth it when the
  rainbow stays still around the animated part.

## 5. Animations

- **PREFER implicit animations** (`AnimatedContainer`, `AnimatedOpacity`,
  `AnimatedSwitcher`, `TweenAnimationBuilder`) for A-to-B transitions.
- **DO use `*Transition` widgets** (`FadeTransition`, `SlideTransition`,
  `ScaleTransition`, `RotationTransition`) with an `AnimationController`.
  They update a render object directly, with no rebuild per tick.
- **DO pass static subtrees as `child:`** to `AnimatedBuilder`.
- **AVOID `controller.addListener(() => setState(() {}))`** (PERF-009).
- **DO stop off-screen animations.** `TickerMode` stops tickers in inactive
  routes and in tabs that use it, but a `repeat()` in an always-mounted
  widget keeps ticking. Pause it from visibility or lifecycle signals.
- **AVOID animating layout** (size, padding) of large subtrees every frame
  when a transform (`Transform.scale`, `SlideTransition`) gives the same
  look. Transforms don't trigger layout.
- Respect reduced motion: `MediaQuery.disableAnimationsOf(context)`.
