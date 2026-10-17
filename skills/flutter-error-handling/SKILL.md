---
name: flutter-error-handling
description: Design, write and review error handling in Flutter and Dart apps so failures flow through the project's own architecture. Sources throw transport exceptions, repositories map them to typed failures or a Result, and logic turns them into error state (MVN sealed XError, Bloc XFailure, MVVM Command error, Riverpod AsyncValue.error). The UI then shows user-safe messages and one-time snackbars. Covers try/catch, `on` clauses, rethrow, Error vs Exception, Result/Either vs exceptions, DioException mapping, retry, and global handlers (FlutterError.onError, PlatformDispatcher, runZonedGuarded, Crashlytics, Sentry). Includes a checker for swallowed catches, leaked transport errors and stuck loading. Use it whenever code catches, throws or reports errors, or when someone says "app crashes", "error not shown" or "spinner never stops", even if they never say "error handling".
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.1.0"
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
    the error state.
12. **Don't catch what you can't handle.** Let it reach the logic layer or
    the global handler, so it gets reported instead of swallowed.

## REVIEW checklist

Script rules (`ERR-0xx`; full detail in `references/rules.md`):

| ID | Name | Default severity | What to look for |
|---|---|---|---|
| ERR-001 | swallowed-catch | High (graded down: Medium if typed or print-only, Low for cleanup, probes and lookups, Info if documented or `xOrNull`/`tryX`) | empty, comment-only, print-only or `return <default>;` catch; `catchError((_) {})`; `onError: (_) {}` |
| ERR-002 | untyped-catch-unmapped | Medium (Low for a fallback attempt, Info if documented) | `catch (_)` / `on Object` in data or domain that drops the error |
| ERR-003 | catches-error | Medium | `on StateError`, `on TypeError`, `on Error` … |
| ERR-004 | repository-leaks-transport-exception | Medium | repository awaits a network source, or calls `jsonDecode`, with no mapping |
| ERR-005 | throws-non-exception | Medium | `throw 'msg'`, `throw {...}`, `Future.error('msg')` |
| ERR-006 | domain-throws-transport | High (Medium for `on`/`is`) | `DioException` / `SocketException` / `PlatformException` in domain code |
| ERR-007 | repository-null-on-failure | Medium | a repository `catch` that returns `null`; `catchError((_) => null)` |
| ERR-008 | raw-error-shown-to-user | Medium in UI, Low in logic/state | `Text(e.toString())`, `'$error'`, `XError(e.toString())` |
| ERR-009 | mixed-result-and-throw | Medium (Low for a signature mix) | a `Result` method that throws; `Result` and throwing APIs on one repository |
| ERR-010 | loading-without-error-path | High | `state = Loading` / `emit(Loading)` / `_loading = true`, then an unguarded `await` |
| ERR-011 | rethrow-loses-stack | Low | `throw e;` inside `catch (e)` |
| ERR-012 | missing-global-error-handler | Medium with a crash-reporter dependency, else Low | no `FlutterError.onError`, or no `PlatformDispatcher.instance.onError` / `runZonedGuarded` |
| ERR-013 | zone-mismatch | Medium | `ensureInitialized()` outside the `runZonedGuarded` that calls `runApp` |
| ERR-014 | unguarded-io-in-ui | Medium | a Widget/State callback awaits an http/dio call with no try/catch |

Reading-level findings (`ERR-<slug>`; the script can't see these):

| ID | Severity | Look for |
|---|---|---|
| ERR-result-unguarded-await | High | a `Future<Result<T>>` method awaits a throwing call outside `try`, so the `Result` promise is broken |
| ERR-return-without-await | High | `try { return fetch(); } catch …` in an `async` function. Without `await`, the catch never runs |
| ERR-unawaited-future | Medium | a fire-and-forget future with no error handling, which becomes an uncaught zone error (`unawaited_futures`, `discarded_futures`) |
| ERR-error-replaces-data | Medium | a refresh failure wipes data that was already shown. Keep the previous value (`AsyncValue` keeps `value`; Bloc status enum) |
| ERR-stringly-failure | Low | error state carries a `String` built in logic instead of a typed failure |
| ERR-effect-in-build | Medium | `showSnackBar` / `showDialog` called from `build()` instead of a listener |
| ERR-context-after-await | High | the catch uses `context` after an `await` without a `context.mounted` check (defer to `flutter-ui-practices`, `UI-context-after-await`) |
| ERR-retry-non-idempotent | Medium | automatic retry of POST/payment calls, or retry on 4xx/parse failures |
| ERR-double-report | Low | the same failure is logged in the repository, the logic layer and the global handler |
| ERR-provider-exception | Low | Riverpod 3: `on DioException` around `ref.read(p.future)`, which now throws a `ProviderException` that wraps the original (see `references/error-flow-by-architecture.md`) |

**When not to flag:**
- MVN and MVVM logic catching everything (`catch (e)`) and mapping it to error
  state. That is the boundary, and it is sanctioned. ERR-002 only applies to
  data and domain.
- A project that consistently uses exceptions *and* catches them at the logic
  layer. Don't demand `Result` (the Flutter guide calls it "a recommendation,
  but not a requirement").
- `tryParse`-style helpers (`on FormatException { return null; }` in a parser).
- Documented best-effort cleanup.

## Finding examples

Use the suite's finding format, so `dart-flutter-review` can merge the
findings:

```markdown
### [HIGH] Loading state never ends when the fetch fails
- id: ERR-010
- where: lib/features/movie/presentation/notifier/movie_notifier.dart:18
- evidence: `state = const MovieLoading(); final movies = await ref.read(getTrendingProvider)();` with no try/catch
- rule: MVN: the notifier catches and sets the sealed XError state (flutter-error-handling › rules.md ERR-010)
- why: a DioException leaves the screen on a spinner forever and surfaces only as an uncaught zone error
- fix: |
    try {
      state = MovieSuccess(await ref.read(getTrendingProvider)());
    } on Failure catch (f) {
      state = MovieError(f);            // the view maps the failure to localized text
    }
- confidence: confirmed

### [MEDIUM] Repository lets DioException escape
- id: ERR-004
- where: lib/features/movie/data/repositories/movie_repository_impl.dart:14
- evidence: `final rows = await _api.trending();` with no catch; MovieApi uses Dio and maps nothing
- rule: repositories map transport exceptions to domain failures (AP-exceptions-across-layers)
- why: every caller has to know about Dio; one forgotten try in the UI layer is a crash
- fix: catch `on DioException` and `on FormatException` in the repository and throw `NetworkFailure`/`ParseFailure`, or return `Result.error(...)`
- confidence: confirmed
```

Open the report with one line naming the profile and the error style
(`mvn, exceptions, no global handlers`). Report a pattern-wide problem
**once**, with a few locations.

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
| `references/error-flow-by-architecture.md` | writing or reviewing the source → repo → logic → UI path for MVN, MVVM+Command, Bloc/Cubit, Clean (Either), Riverpod, Provider, GetX, setState |
| `references/result-vs-exceptions.md` | choosing `Result` vs exceptions, designing typed failures, mapping DioException/http errors, retry |
| `references/rules.md` | every ERR-0xx rule: severity, profiles, detection, why, bad/good code, fix, false positives |
| `references/global-handlers.md` | writing `main()`: FlutterError.onError, PlatformDispatcher, runZonedGuarded, ErrorWidget, Crashlytics/Sentry, isolates, observers |
