# flutter-ui-practices: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist (in order of harm)

Work top to bottom (in a diff, only the changed lines and what they affect).
Stop polishing style while a correctness item is open.

1. **Lifecycle and leaks** (High): undisposed controllers, uncancelled
   subscriptions and timers, listeners removed with a different closure, a
   passed-in controller being disposed, `super.initState()` not first.
2. **Async and context** (High): `context`/`setState` after `await` without a
   mounted check (the `use_build_context_synchronously` lint misses `context`
   captured in closures and helpers), futures created in `build()`, swallowed
   errors, unawaited futures.
3. **I/O and logic in widgets** (High for I/O, Medium for logic): HTTP, database
   or `jsonDecode` in a widget; business rules in `build()` or `onPressed`.
   Escalate the structural side to the `flutter-architecture` skill.
4. **Wrong UI** (Medium to High): a missing exhaustive case, `default:` hiding a
   state, missing or unstable keys that attach state to the wrong item,
   a layout that overflows at large text scales.
5. **Performance** (Medium): eager lists, `shrinkWrap`/intrinsics on long
   lists, oversized image decoding, `Opacity` in animations, root-level
   `setState`, `MediaQuery.of`, expensive work in `build()`.
6. **Structure** (Low): helper methods instead of widget classes, oversized
   `build()`, missing `const` on large static subtrees (only if the project
   enables the lints or the subtree is big).
7. **Theming, accessibility, i18n** (Low to Medium): hard-coded colours and
   styles, unlabeled icon buttons, tap targets under 48×48, literal strings in
   a localised app, LTR-only padding in an app that ships RTL.
8. **Tests** (Info to Medium): views without widget tests, mocks where a fake
   would do, `pumpAndSettle` on endless animations.

## Reporting findings

Use the suite finding format, with `UI-<slug>` IDs:

```markdown
### [HIGH] AnimationController never disposed
- id: UI-lifecycle
- where: lib/ui/home/home_screen.dart:31
- evidence: `late final _c = AnimationController(vsync: this);` with no dispose() override
- rule: Flutter: dispose what you create (flutter-ui-practices › flutter-ui.md §1)
- why: keeps ticking and retains the State after pop → memory/CPU leak per visit
- fix: |
    @override
    void dispose() { _c.dispose(); super.dispose(); }
- confidence: confirmed
```

| Slug | Default severity | Rule (§ in `references/flutter-ui.md`) |
|---|---|---|
| `UI-lifecycle` | High | Created disposable not disposed, cancelled or closed; wrong `super` order (§1) |
| `UI-dispose-not-owned` | Medium | Disposing a controller or client that was passed in (§1) |
| `UI-did-update-widget` | Medium | Config-dependent resource not swapped in `didUpdateWidget` (§1) |
| `UI-context-after-await` | High | `context` used after `await` without a mounted check (§2) |
| `UI-setstate-after-await` | High | `setState` after `await` without a mounted check (§2) |
| `UI-future-in-build` | High | Future or stream created in `build()` (§2) |
| `UI-silent-catch` | High | Async UI action with no failure path (§2) |
| `UI-unawaited-future` | Medium | Future neither awaited nor `unawaited(...)` (§2) |
| `UI-blocking-ui-isolate` | Medium | Heavy sync work on the UI isolate (§2) |
| `UI-build-side-effect` | Medium | Side effects, allocations or heavy work in `build()` (§3) |
| `UI-helper-method` | Low | `Widget _buildX()` instead of a widget class (§3) |
| `UI-rebuild-scope` | Low | `setState` or `watch` wider than what changes (§3) |
| `UI-mediaquery-of` | Low | `MediaQuery.of(context).x` instead of `MediaQuery.xOf` (§3) |
| `UI-keys` | Medium | Missing or unstable keys, `UniqueKey()` in `build()` (§3) |
| `UI-eager-list` | Medium | Long list built eagerly, `shrinkWrap`, intrinsics (§4) |
| `UI-image-decode-size` | Medium | Image decoded far above display size (§4) |
| `UI-opacity` | Low | `Opacity`/clipping in animations (§4) |
| `UI-non-exhaustive-state` | Medium | State rendered without an exhaustive `switch` (§5) |
| `UI-duplicated-state` | Medium | Logic-holder state copied into `State` fields (§5) |
| `UI-effect-in-build` | Medium | Snackbar, dialog or navigation triggered from `build()` (§5) |
| `UI-logic-in-widget` | Medium | Business logic in a widget (§6) |
| `UI-hardcoded-style` | Low | Colours and text styles not from the theme (§7) |
| `UI-a11y` | Medium | Unlabeled tappable icons, small targets, colour-only meaning, fixed heights around text (§7) |
| `UI-l10n` | Low | Literal user-facing strings in a localised app (§7) |
| `UI-rtl` | Medium | LTR-only `EdgeInsets`/`Alignment` in an app that ships RTL (§7) |
| `UI-widget-test` | Info | Untested view, mocks over fakes, `pumpAndSettle` on endless animations (§8) |

Raise or lower the severity with the evidence (an eager list of five fixed
items isn't Medium). **Dedupe** against the other passes. I/O in a widget is
`ARCH-101` when the `flutter-architecture` checker reports it, so add a
`UI-*` finding only for what that doesn't cover. Analyzer hits
(`use_build_context_synchronously`, `cancel_subscriptions`, `avoid_print`) are
`LINT:<code>` findings. Missing `const` that `dart fix` resolves goes in the
single collapsed **Mechanical** finding.
