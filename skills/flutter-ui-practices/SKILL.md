---
name: flutter-ui-practices
description: Write and review Flutter widget code the way the Flutter team recommends - StatefulWidget lifecycle (initState, didUpdateWidget, dispose), disposing controllers, FocusNodes, subscriptions and timers, BuildContext after await (context.mounted), setState scope, a pure and cheap build(), widget classes over helper methods, const, keys, lazy lists and slivers, MediaQuery.sizeOf, rebuilds and jank, animations, images, theming, accessibility, l10n and RTL, and widget tests. Use it whenever you write, refactor or review a widget, screen or Flutter UI file, fix a leak or a "setState() called after dispose()" or "deactivated widget's ancestor" error, chase jank or excess rebuilds, or write widget tests, even if nobody says "best practice". Reports UI-* findings with severity, evidence and a concrete fix.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.1"
  suite: flutter-pro-skills
---

# Flutter UI practices

Most real Flutter bugs live in a handful of places: something created in a
`State` and never disposed, a `BuildContext` used after the widget is gone, a
future created in `build()` that refires on every rebuild, and work in
`build()` that makes frames late. This skill helps you write widgets that avoid
those by construction, and review widgets for them in order of how much harm
they do.

Architecture (layers, which object holds logic, repositories, DI) is the job of
the `flutter-architecture` skill (if your agent doesn't auto-load skills, read
`../flutter-architecture/SKILL.md`). Naming is the job of `dart-naming`
(`../dart-naming/SKILL.md`).

## Precedence

1. **The project's own decisions**: its lint config, its project instructions
   file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
   `.github/copilot-instructions.md`), its declared architecture and state
   solution, and conventions used consistently in its code.
2. The canonical source of the pattern it uses (Riverpod, Bloc, MVN, MVVM).
3. Effective Dart, then 4. Flutter team guidance for apps (what this skill
   condenses), then 5. the framework's style guide, only where the project follows it.

Match the project's conventions, not its defects. A leak copied from the
neighbouring file is still a leak.

## Before you start: read the project

- `pubspec.yaml`: the Flutter SDK constraint decides which APIs you may use
  (`BuildContext.mounted` needs Flutter ≥3.7, `MediaQuery.sizeOf` and friends
  ≥3.10, `WidgetTester.view` ≥3.10). Note the state solution (Riverpod, Bloc,
  Provider, GetX, plain `setState`), the router, and whether the app is
  localised (`flutter_localizations`, `l10n.yaml`).
- `analysis_options.yaml`: `flutter_lints`, `very_good_analysis` or custom, and
  whether `prefer_const_*`, `use_build_context_synchronously` or
  `unawaited_futures` are on.
- Two or three neighbouring widgets: how they get their logic holder, how they
  read theme and strings, and how they split screens into widgets.

## WRITE checklist

Hold every widget you write or change to these. Each is detailed in
`references/flutter-ui.md`.

- [ ] **Dispose what you create** (§1). Every `AnimationController`,
      `TextEditingController`, `ScrollController`, `PageController`,
      `TabController`, `FocusNode` and owned `ValueNotifier` is disposed,
      every `StreamSubscription` and `Timer` cancelled, every `StreamController`
      closed, in `dispose()`, with `super.dispose()` last. Never dispose of what
      was passed in.
- [ ] **Config-dependent resources** are swapped in `didUpdateWidget`.
- [ ] **No `context` or `setState` after an `await`** without
      `if (!context.mounted) return;` (`if (!mounted) return;` in a `State`), or
      read what you need (`ScaffoldMessenger.of(context)`) before the await (§2).
- [ ] **No futures or streams created in `build()`.** Create them in
      `initState` or the state layer and keep them in a field (§2).
- [ ] **Every async user action has a visible failure path.** No empty `catch`
      (§2).
- [ ] **`build()` is pure and cheap**: no I/O, no side effects, no sorting or
      filtering of big lists, no allocations that could be fields (§3).
- [ ] **Widget classes, not `Widget _buildX()` helpers**, for reusable or
      non-trivial pieces (§3).
- [ ] **`setState` and `ref.watch`/`select` cover the smallest subtree that
      changes.** Static subtrees are `const` or passed as `child` (§3).
- [ ] **`MediaQuery.sizeOf(context)`** (and `paddingOf`, `viewInsetsOf`, …),
      not `MediaQuery.of(context).size` (§3).
- [ ] **Stable keys** (`ValueKey(item.id)`) on items in reorderable, animated or
      dismissible lists. No `UniqueKey()` in `build()` (§3).
- [ ] **Lazy lists** for long or unbounded data: `ListView.builder`,
      `.separated`, slivers. No `shrinkWrap: true` on long lists (§4).
- [ ] **Images decoded at display size** (`cacheWidth`/`cacheHeight`) (§4).
- [ ] **Implicit animations** for simple transitions. A controller only when
      you need control, and then disposed (§4).
- [ ] **No logic or I/O in widgets.** It goes to the project's view model,
      notifier, bloc or controller (§6).
- [ ] **Render state with an exhaustive `switch`**. One-time effects
      (snackbar, navigation) go in a listener, not in `build()` (§5).
- [ ] **Colours and text styles from `Theme.of(context)`**, strings from the
      app's localizations, `EdgeInsetsDirectional`/`AlignmentDirectional` for
      RTL, a `tooltip` or `Semantics` label on icon buttons (§7).

Then run `dart format` and `dart analyze` on the files you touched and fix what
*your* change introduced (full WRITE workflow: the `dart-flutter-best-practices`
skill, `../dart-flutter-best-practices/SKILL.md`).

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Mechanical candidates (bundled heuristics)

The heuristics now live in the `dart-flutter-review` skill. Run its read-only
script on the project:

```bash
bash ../dart-flutter-review/scripts/review.sh <project-root> [--diff <git-ref>]
```

Its `CANDIDATES` section lists UI hits: controllers with no `dispose`,
widget-returning helper methods, `MediaQuery.of(...).size`, futures in
builders, `.map` children, `Opacity`, `UniqueKey()` and hard-coded colours.
Treat every hit as a *candidate* and confirm it by reading the code. If that
skill isn't installed or the script can't run (for example, there's no Dart SDK), fall back to
plain searches and read each hit:

```bash
grep -rnE 'Widget _?build[A-Z][A-Za-z0-9_]*\(' lib
grep -rnE 'MediaQuery\.of\([A-Za-z_]+\)\.(size|padding|viewInsets)' lib
grep -rnE '(future|stream): *[A-Za-z_][A-Za-z0-9_.]*\(' lib
grep -rnE 'UniqueKey\(\)|(^|[^.A-Za-z0-9_])Opacity\(' lib
grep -rlE '(Animation|TextEditing|Scroll|Page|Tab)Controller\(|FocusNode\(' lib | xargs grep -L 'dispose()'
```

## When to load `references/flutter-ui.md`

It's about 280 lines with a Contents list. Read the sections the code touches:

| The code involves… | Read |
|---|---|
| `initState`/`dispose`, controllers, subscriptions, timers, listeners | §1 |
| `async` handlers, `await` then `context`, `FutureBuilder`, isolates | §2 |
| `build()` structure, helper methods, `const`, keys, `MediaQuery` | §3 |
| Lists, scrolling, opacity, clipping, images, animations, jank | §4 |
| How a widget reads, renders and reacts to state | §5 |
| Where logic belongs (pointer to `flutter-architecture`) | §6 |
| Theme, colours, accessibility, localisation, RTL, logging | §7 |
| Unit and widget tests | §8 |
| Which of the above the lints already cover | §9 |

## Related skills

Sibling skills (if your agent doesn't auto-load skills, read `../<name>/SKILL.md`):
`dart-flutter-best-practices` (the hub: WRITE workflow, Effective Dart, lints),
`flutter-architecture` (layers, patterns, state management, import-graph
checker), `dart-naming` (names of widgets, callbacks, files) and
`dart-flutter-review` (full reviews that run the script above and merge `UI-*`
findings with the rest). For depth on one concern, load its specialist:
`flutter-performance` (rebuild scope, lazy lists, isolates, image decode
size, DevTools; its `PERF-` IDs beat `UI-image-decode-size`,
`UI-blocking-ui-isolate` and `UI-rebuild-scope`), `flutter-design-system`
(tokens, `ThemeExtension`, dark mode; `DS-` beats `UI-hardcoded-style`),
`flutter-accessibility` (semantics, targets, contrast, text scale; `A11Y-`
beats `UI-a11y`) and `flutter-persistence` (local storage behind the
repository). If a sibling is missing, this skill still works on its own. Say
which check you skipped.
