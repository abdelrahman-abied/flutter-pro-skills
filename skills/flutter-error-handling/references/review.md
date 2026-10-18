# flutter-error-handling: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

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
