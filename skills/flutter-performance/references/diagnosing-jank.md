# Diagnosing jank with DevTools

Fix what you measured, not what looks slow in the code. Debug builds are
JIT-compiled, run assertions and add debug-only work, so they are often 10×
slower than release and their timings mean nothing. Measure in **profile
mode** on a **real device**, preferably a low-end one.

## Contents

1. Run in profile mode
2. Read the Performance view: UI thread vs raster thread
3. Find what rebuilds too much
4. Raster jank: shaders, Impeller and saveLayer
5. Debug flags (and remove them afterwards)
6. Benchmarks that stay fixed: `integration_test` + `traceAction`
7. Report the evidence

## 1. Run in profile mode

```bash
flutter run --profile                       # on a device; emulators and simulators distort GPU timings
flutter run --profile --trace-startup       # startup timeline in build/start_up_info.json
```

Open DevTools from the URL the run prints (or from the IDE). Use a physical
device: emulator GPU timings don't reflect real hardware. iOS simulators
don't support profile mode.

## 2. Read the Performance view: UI thread vs raster thread

The frame chart shows two bars per frame. A frame is janky when either bar
exceeds the budget (16 ms at 60 Hz, 8 ms at 120 Hz).

| Slow bar | It means | Look at |
|---|---|---|
| **UI** | Dart work: build, layout, paint recording, your own sync code | the CPU profiler (bottom-up), the timeline events for `Build`/`Layout`; lists, rebuild scope, work in `build`, sync parsing (`isolates.md`) |
| **Raster** | the engine drawing the layer tree on the GPU thread | `saveLayer` (Opacity, BackdropFilter, ShaderMask, clips), huge images, shader compilation on the first use of an effect |

Select a janky frame to see its timeline events. Turn on the "Enhance
tracing" options (track widget builds, layouts and paints) to see which
widgets were built in that frame. They add overhead, so compare relative
numbers, not absolute ones.

## 3. Find what rebuilds too much

- **Rebuild counts.** DevTools can count widget rebuilds per frame (the
  "Track widget rebuilds" option, with counts shown in the Performance view's
  rebuild stats and the Inspector). Interact with the screen and look for
  widgets whose count climbs with every scroll frame or keystroke.
- `debugProfileBuildsEnabled = true` (in `main()`, debug or profile) adds a
  timeline event for every `build`. `debugProfileBuildsEnabledUserWidgets`
  limits it to your own widgets.
- `debugPrintRebuildDirtyWidgets = true` logs every rebuilt widget to the
  console in debug mode. It's noisy, so use it for a few seconds.
- Then fix the scope with the project's own tools (`rebuild-scope.md`).

## 4. Raster jank: shaders, Impeller and saveLayer

- **Shader compilation jank** (a stutter the first time an animation or
  effect runs) was the classic Skia problem. **Impeller**, Flutter's
  renderer that precompiles its shaders, is the default on iOS and on modern
  Android, which removes most of it. Check which renderer the run reports
  before chasing shader jank.
- The old Skia fix, SkSL warm-up (`--cache-sksl`, `--bundle-sksl-path`), only
  ever applied to the Skia backend. Don't add it to new projects. If a
  project still ships it, check whether its targets still use Skia.
- `flutter run --profile --trace-skia` adds Skia-level events to the
  timeline when the Skia backend is in use. With Impeller, read the raster
  thread's events in the timeline directly.
- Most remaining raster cost is `saveLayer` and oversized images. DevTools'
  "Highlight oversized images" and the raster thread's events point at them
  (`lists-images-painting.md` §3–§4).

## 5. Debug flags (and remove them afterwards)

| Flag | Shows |
|---|---|
| `debugProfileBuildsEnabled` | build events in the timeline |
| `debugProfileLayoutsEnabled` / `debugProfilePaintsEnabled` | layout and paint events |
| `debugRepaintRainbowEnabled` | rotating colours on every repaint (also DevTools "Highlight repaints") |
| `debugInvertOversizedImages` | images decoded far larger than displayed |
| `debugPrintRebuildDirtyWidgets` | each rebuilt widget, in the console |
| `MaterialApp(showPerformanceOverlay: true)` | the UI and raster graphs on screen |

None of these belong in committed code. Set them in a local `main_profile.dart`
or behind `kDebugMode`.

## 6. Benchmarks that stay fixed: `integration_test` + `traceAction`

Turn a jank fix into a regression test that records a timeline:

```dart
// integration_test/scroll_perf_test.dart
void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('feed scrolls smoothly', (tester) async {
    app.main();
    await tester.pumpAndSettle();
    final list = find.byType(Scrollable).first;
    await binding.traceAction(() async {
      await tester.fling(list, const Offset(0, -2000), 4000);
      await tester.pumpAndSettle();
    }, reportKey: 'feed_scroll');
  });
}

// test_driver/perf_driver.dart
Future<void> main() => integrationDriver(
      responseDataCallback: (data) async {
        final summary = TimelineSummary.summarize(
          Timeline.fromJson(data!['feed_scroll'] as Map<String, dynamic>),
        );
        await summary.writeTimelineToFile('feed_scroll', pretty: true, includeSummary: true);
      },
    );
```

```bash
flutter drive --profile --driver=test_driver/perf_driver.dart --target=integration_test/scroll_perf_test.dart
```

The summary file (in `build/`) holds average and worst frame build and raster
times and the missed-frame counts. Compare them before and after the change,
on the same device. `binding.watchPerformance` records frame timings without
a full timeline.

## 7. Report the evidence

A performance finding is `confirmed` when it carries a measurement: the
device, the mode (profile), the janky frame's UI and raster times, and the
widget or function the timeline points at. Without one, keep the checker's
severity and mark it `likely`. A "fix" with no before/after numbers is
`PERF-unmeasured-claim` (Info).
