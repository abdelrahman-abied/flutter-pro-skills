---
name: flutter-error-handling
description: Design, write and review error handling in Flutter and Dart apps so failures flow through the project's own architecture. Sources throw transport exceptions, repositories map them to typed failures or a Result, and logic turns them into error state (MVN sealed XError, Bloc XFailure, MVVM Command error, Riverpod AsyncValue.error). The UI then shows user-safe messages and one-time snackbars. Covers try/catch, `on` clauses, rethrow, Error vs Exception, Result/Either vs exceptions, DioException mapping, retry, and global handlers (FlutterError.onError, PlatformDispatcher, runZonedGuarded, Crashlytics, Sentry). Includes a checker for swallowed catches, leaked transport errors and stuck loading. Use it whenever code catches, throws or reports errors, or when someone says "app crashes", "error not shown" or "spinner never stops", even if they never say "error handling".
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.1"
  suite: flutter-pro-skills
---

# Flutter error handling

Dart exceptions are unchecked: nothing tells a caller what a function can throw.
So failures get lost. Nobody catches them (a crash, or an async error lost in
the zone), someone catches and drops them (the spinner never stops), or they
reach the UI raw (the user reads `DioException [connection error]`).

This skill makes every failure take one deliberate path through the layers the
project *already has*. The rules depend on the architecture. An MVN notifier
catches into a sealed error state. An MVVM view model gets a `Result` from the
repository and runs through a `Command`. A Bloc emits a failure state. Riverpod
uses `AsyncValue.guard`. So detect the pattern first, then apply that
pattern's flow.

## Workflow

### 1. Detect the profile and the error style

Look for a declared convention in your agent's project instructions file
(`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
`.github/copilot-instructions.md`): "repositories return Result", "we use
fpdart", "errors go to Sentry". A declared convention wins. Then run the
checker. It is read-only, needs only the Python standard library, and doesn't
need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_errors.py <project-root>                 # text report
python3 -I <skill-dir>/scripts/check_errors.py <project-root> --json          # schema flutter-pro-skills/error-check@1
python3 -I <skill-dir>/scripts/check_errors.py <project-root> --files changed.txt  # diff review: report only these files
python3 -I <skill-dir>/scripts/check_errors.py <project-root> --profile bloc   # declared pattern wins
```

The CLI is `check_errors.py <project-root> [--json] [--files <list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
`--files` takes a file of relative paths (one per line) or a comma-separated
list. It still analyses the whole project, because some rules need to know
whether a source maps its errors. The exit code is `0` whenever a report is
produced and `2` on a usage error.

The checker takes layers and roles from the `files` array of the
`flutter-architecture` checker (`../flutter-architecture/scripts/arch_check.py
--json`). If that sibling is missing, it falls back to path-based
classification and prints `classification: path-based fallback (...)`.
The header also reports the **error style** (`exceptions`, `result` or `mixed`)
and which **global handlers** exist. Read both before writing anything.

```text
== ERROR HANDLING
  profile: mvn (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 142 files, 37 catch clauses, 21 throw statements, 0 Result-returning methods (style: exceptions)
  global handlers: none found
  [ERR-001] swallowed-catch (high) x3 — A catch (or catchError/onError handler) discards the error: ...
      lib/features/sync/data/sync_runner.dart:84  onError: (Object _) {}   [stream/future errors are dropped silently]
      ... 1 more
  suppressed: 2 (see --json)
```

### 2. Apply the pattern's error flow

Each layer has one job. Never skip a layer, and never let one layer do
another's job:

| Layer | Its one job | MVN | MVVM (+Command) | Bloc / Cubit | Riverpod (plain) | Provider / GetX |
|---|---|---|---|---|---|---|
| Source / service | Do I/O. May throw transport exceptions | throws `DioException` | throws, or returns `Result` (Compass app) | throws | throws | throws |
| Repository | **Map**: transport → domain failure, or `Result` | throws a typed `Failure`, or returns `Result` | returns `Result<T>` | throws a typed failure (Bloc samples), or `Result` | either | either |
| Use case (if any) | Pass through, or combine failures. Never transport types | `call()` rethrows / returns `Result` | optional | optional | optional | rare |
| Logic | **Decide**: failure → UI state | `try/catch` → sealed `XError` | `Command` captures the `Result` | `try/catch` → `emit(XFailure)` or `status: failure` | `state = await AsyncValue.guard(...)` | `try/catch` → error field + `notifyListeners()` / `.obs` |
| UI | **Show**: render the error state; one-time effects in a listener | `switch` on state; `ref.listen` → snackbar | `ListenableBuilder` on the command; listener → snackbar, `clearResult()` | `BlocBuilder` + `BlocListener` | `switch` on `AsyncValue`; `ref.listen` | `Consumer` / `Obx`; `Get.snackbar` in `ever` |
| Global | Catch what escaped, then report it | `FlutterError.onError` + `PlatformDispatcher.instance.onError` (or `runZonedGuarded`) → Crashlytics/Sentry, plus `ProviderObserver` / `BlocObserver` | same | same + `BlocObserver.onError` | same + `ProviderObserver` | same |

Read `references/error-flow-by-architecture.md` for the full source → repo →
logic → UI code of each pattern, including Clean Architecture with `Either`.
Read `references/result-vs-exceptions.md` before choosing between `Result` and
exceptions. Read `references/global-handlers.md` before you write `main()`.

### 3. Write or review

Use the checklists below. Match the project's error style: a `Result` codebase
gets `Result`, an exception codebase gets typed exceptions, and an app on the
Flutter `Result` doesn't get `Either`. A second style is worse than either
alone (ERR-009).

### 4. Run the checker and confirm every hit

Read the code behind every hit before you call it `confirmed`.
`references/rules.md` lists each rule's false positives. The checker grades
severity from context, and the `note` column says why. For example, a
**documented** best-effort cleanup (`catch (_) { /* already disposed */ }`) is
`info` and an undocumented empty catch-all is `high`. Suppress a deliberate
hit in the code with a reason:
`// err-ignore: ERR-001 the channel may already be closed` (on the reported
line, the line above or the line below) or
`// err-ignore-file: ERR-005 <reason>`.

## WRITE checklist

1. **Sources throw. Repositories map.** Catch `DioException`, `SocketException`,
   `http.ClientException`, `TimeoutException`, `FormatException` and
   `PlatformException` at the repository boundary, and turn them into a domain
   `Failure` (thrown, or returned as `Result.error`). Nothing above the
   repository should import `dio`.
2. **Catch specific types**: `on DioException catch (e, st)`. Use a catch-all
   only at a real boundary (a logic class, a global handler, an isolate entry),
   and even there log or report what you catch.
3. **Never catch `Error`.** `StateError`, `TypeError` and `RangeError` are bugs.
   Fix the code, or validate first (`int.tryParse`, `list.firstOrNull`).
4. **Throw `Exception` subtypes for runtime failures** and `Error` subtypes
   (`ArgumentError`, `StateError`) for misuse by the caller. Never throw a
   `String` or a `Map`.
5. **Keep the cause and the stack.** Use `rethrow;`, not `throw e;`. When you
   map, store the `cause` on the failure, or use
   `Error.throwWithStackTrace(failure, st)`.
6. **Choose one error style per codebase.** With `Result`, every repository
   method returns it, and none of them throws.
7. **Every loading state has an exit.** If you set `Loading`, the matching
   `catch`, `finally` or `Result` branch must set `Error` or `Success`. In
   Riverpod, use `AsyncValue.guard`.
8. **Store typed failures in state, not strings from `e.toString()`.**
   Translate a failure to localized, user-safe text in the UI layer, where
   `BuildContext` and l10n live.
9. **One-time effects go in listeners**: `ref.listen`, `BlocListener`, a
   `Command` listener. Never show them from `build()`, and never keep a
   `showError` bool in state.
10. **Install both global handlers in `main()`**: `FlutterError.onError` and
    `PlatformDispatcher.instance.onError`, wired to the crash reporter. Call
    `WidgetsFlutterBinding.ensureInitialized()` inside the zone if you use
    `runZonedGuarded`.
11. **Retry only transient failures** (network errors, timeouts, 5xx, 429), use
    backoff, and only for idempotent requests. Give the user a retry action on
    the error state. The retry *interceptor* in the HTTP client belongs to
    `flutter-networking` (`NET-004` retry-resends-any-method; fallback
    `../flutter-networking/SKILL.md`), which beats `ERR-retry-non-idempotent`
    for the same line.
12. **Don't catch what you can't handle.** Let it reach the logic layer or
    the global handler, so it gets reported instead of swallowed.

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern and its layer rules.
  `AP-exceptions-across-layers`, `AP-leaky-repository` and ARCH-107 (a
  repository returning transport *types*) live there. This skill adds the
  error *flow* and the ERR checks. Fallback: `../flutter-architecture/SKILL.md`,
  `../flutter-architecture/references/anti-patterns.md` (the index; all three
  entries are in `../flutter-architecture/references/anti-patterns/data-and-repositories.md`).
- **`dart-flutter-best-practices`** for the Effective Dart error rules
  (`avoid_catches_without_on_clauses`, `only_throw_errors`,
  `avoid_catching_errors`, `use_rethrow_when_possible`) and the lint set.
  Fallback: `../dart-flutter-best-practices/references/effective-dart.md`.
- **`flutter-ui-practices`** for `context.mounted` after `await`, listeners and
  lifecycle. Fallback: `../flutter-ui-practices/references/flutter-ui.md`.
- **`dart-flutter-review`** runs this checker in its `== ERROR HANDLING`
  section and an optional errors reviewer pass. Fallback:
  `../dart-flutter-review/SKILL.md`.
- **`flutter-testing`** for testing failure paths (fake repositories returning
  `Result.error`, `blocTest` `errors:`, `expectLater(..., throwsA(...))`).
  Fallback: `../flutter-testing/SKILL.md`.
- **`mvn`** (the MVN author's scaffolding skill; some agents list it as
  `mvn-architect:mvn`) for generating MVN features with the sealed error state.

## References

| File | Read it when |
|---|---|
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/error-flow-by-architecture.md` | writing or reviewing the source → repo → logic → UI path for MVN, MVVM+Command, Bloc/Cubit, Clean (Either), Riverpod, Provider, GetX, setState |
| `references/result-vs-exceptions.md` | choosing `Result` vs exceptions, designing typed failures, mapping DioException/http errors, retry |
| `references/rules.md` | every ERR-0xx rule: severity, profiles, detection, why, bad/good code, fix, false positives |
| `references/global-handlers.md` | writing `main()`: FlutterError.onError, PlatformDispatcher, runZonedGuarded, ErrorWidget, Crashlytics/Sentry, isolates, observers |
