# ERR rule catalog

Each rule that `scripts/check_errors.py` reports has an entry here, and so does
each reading-level `ERR-<slug>` finding. An entry gives the default severity,
the profiles the rule applies to, how it is detected, why it matters, bad and
good Dart, the fix, and known false positives. Severities use the suite scale:
High means a lost error, a crash or wrong UI under ordinary use; Medium hurts
maintainability or hides failures; Low is a local fix; Info is a trade-off, not
a defect.

## Contents

- How the checker works (layers, grading, suppression)
- ERR-001 swallowed-catch
- ERR-002 untyped-catch-unmapped
- ERR-003 catches-error
- ERR-004 repository-leaks-transport-exception
- ERR-005 throws-non-exception
- ERR-006 domain-throws-transport
- ERR-007 repository-null-on-failure
- ERR-008 raw-error-shown-to-user
- ERR-009 mixed-result-and-throw
- ERR-010 loading-without-error-path
- ERR-011 rethrow-loses-stack
- ERR-012 missing-global-error-handler
- ERR-013 zone-mismatch
- ERR-014 unguarded-io-in-ui
- Reading-level findings (ERR-<slug>)

## How the checker works

- **Scope.** It scans `lib/**.dart` and skips generated files (`*.g.dart`,
  `*.freezed.dart`, `*.gr.dart`, `*.mocks.dart`, `*.config.dart`,
  `*.chopper.dart`, `*.pb*.dart`, l10n output, and files headed "GENERATED
  CODE - DO NOT MODIFY").
- **Lexing.** Comments are stripped and strings are kept. Rules that look at
  structure (braces, `try`/`catch`, `throw`) run on a copy whose string
  *contents* are blanked, so `'{'` or `'catch ('` inside a string never
  matches. Rules that need string contents (ERR-008's `'$e'`) read the
  strings themselves.
- **Layers and roles.** The checker uses the `files` array of
  `../flutter-architecture/scripts/arch_check.py --json` when that script
  exists. Otherwise it classifies by path, following the suite's §5
  classification (`domain/`, `data/`, `presentation/`, `*_repository_impl.dart`,
  `notifier/`, `*_bloc.dart` …), and says so in its output. In both modes,
  content refines the role: `@riverpod class`, `extends _$X`, `Bloc`/`Cubit`/
  `ChangeNotifier`/`GetxController` mean logic. A non-abstract `*Repository`
  class in the data or core layer counts as a repository implementation.
  The phase-3 roles are honoured: `repository` (a concrete repository with no
  contract) gets the same rules as `repository-impl` (ERR-004/007/009);
  `barrel` and `di` files are skipped; any other unknown role is tolerated.
  When `files[]` is present it is the source of truth for scope, so a file it
  leaves out (generated code, l10n output) is not scanned (`stats.skipped_out_of_scope`).
- **Per class, not per file.** ERR-008 and ERR-010 look at the enclosing class:
  a Widget/State class is UI, a Bloc/Cubit/Notifier/ChangeNotifier/`extends _$X`
  class is logic, whatever the file's role says. A file that declares a
  codegen notifier next to a `ConsumerWidget` is graded class by class.
- **Types are followed.** Typedefs (`typedef Action<T> = Future<Result<T>> Function()`,
  `typedef Attempt<T> = Future<Result<T>>`, old-style `typedef Future<X> F();`),
  field and parameter types, and project classes (and their implementors) are
  resolved, so an awaited call's return type is known when it is declared in
  the project.
- **Grading.** Some rules grade each hit by its context, and the JSON `note`
  says why. A comment inside a catch block (or on its line) counts as
  documentation, because it records that the swallow is deliberate. A try
  body that only calls `dispose`/`cancel`/`close`/`remove*`/`delete*`/
  `stop`/`release` counts as best-effort cleanup.
- **One finding per catch.** ERR-007 takes priority over ERR-001, and ERR-001
  over ERR-002, so a catch is reported once. ERR-003 and ERR-011 are
  independent and can appear alongside them.
- **Suppression.** `// err-ignore: ERR-001 <reason>` silences a hit when it sits
  on the reported line, the line above, or the line below (so a comment as the
  first line inside the catch block works). `// err-ignore-file: ERR-005
  <reason>` silences a rule anywhere in the file. List several IDs with commas.
  Suppressed hits go to `suppressed` with their reason. Question a suppression
  only when its reason is wrong.
- **`--files`.** The whole project is still analysed, because ERR-004 has to
  know whether the sources a repository imports map their own errors. Only
  findings in the listed files are reported. ERR-012 is reported only when a
  `lib/main*.dart` is in the list.

## ERR-001 swallowed-catch

**High** (graded) · applies: all · detect: script (catch body, plus
`.catchError(...)` / `onError:` callbacks)

**Problem.** A catch block, or a `catchError`/`onError` callback, discards the
error. Its body is empty, holds only comments, only prints, or only does
`return <default>;`, where the default is `null`, `false`, `0`, `''`, `[]`,
`{}`, `const []`, `Duration.zero`, `X.empty()` or a bare `return;`.

**Why.** Effective Dart: "DON'T discard errors from catches without `on`
clauses." The user sees an empty screen or stale data, nothing is reported,
and the bug is invisible in crash dashboards.

**Grading** (the first match wins):

| Context | Severity |
|---|---|
| cleanup-only try body **and** a comment | Info |
| cleanup-only try body | Low |
| a comment inside the catch, or on its line | Info |
| a best-effort UI call in the try (`jumpTo`, `animateTo`, `ensureVisible`, haptics, `SystemChrome`) | Low |
| `return null;` in a function named `xOrNull` / `tryX` with a nullable return type (its contract is "null on failure") | Info |
| `return false;` in a `bool`/`Future<bool>` probe (`is*`/`has*`/`can*`/`check*`/`supports*`, or a try that ends in `return true`) | Low |
| a collection lookup with no I/O (`firstWhere`, `singleWhere`, `.first` …) | Low (use `firstWhereOrNull`) |
| a `print`/`debugPrint`-only body | Medium |
| `on FormatException` returning a default in a parser (the `tryParse` idiom) | Low |
| a typed `on X` (not `Object`/`Exception`) | Medium |
| a catch-all returning a default around `jsonDecode`/`parse`/`fromJson` | Medium |
| `unawaited(f.catchError((_) {}))` (fire-and-forget) | Medium |
| anything else (an undocumented catch-all) | High |

```dart
// Bad: the user sees "no orders", and nobody ever learns the API is down
Future<List<Order>> orders() async {
  try {
    return await _api.orders();
  } catch (_) {
    return [];
  }
}
```

```dart
// Good: map it, so the caller can show "You're offline" and a retry button
Future<List<Order>> orders() async {
  try {
    return await _api.orders();
  } on DioException catch (e, st) {
    Error.throwWithStackTrace(NetworkFailure.fromDio(e), st);
  }
}

// Good: deliberate and documented best-effort cleanup (graded Info)
try {
  await tempFile.delete();
} on FileSystemException {
  // Best effort: the OS clears the temp dir.
}
```

**Fix.** Report it (`log`, `FirebaseCrashlytics.instance.recordError`,
`Sentry.captureException`), rethrow it, or map it to a typed failure. If
dropping it really is right, catch the narrowest type and write the reason in a
comment, which turns the finding into Info. For fire-and-forget calls,
`future.ignore()` states the intent.

**False positives.** Teardown code in `dispose()` that catches "already
closed" errors. Documented ones grade as Info, and undocumented ones should
gain a comment. Platform probes (`on MissingPluginException { return false; }`
in tests or on unsupported platforms) are Medium until documented.
Calibration (phase 3) graded down the `xOrNull`/`tryX` contract (41 false
Highs on lichess), bool capability probes, best-effort scrolls and
collection lookups; see the grading table.

## ERR-002 untyped-catch-unmapped

**Medium** (Low for a fallback attempt, Info if documented) · applies: data and
domain layers, all profiles · detect: script

**Problem.** A catch-all (`catch (e)`, `catch (_)`, `on Object`, `on dynamic`)
in a data or domain file does none of these things: uses the error value,
rethrows, throws, builds a `*Failure`/`*Error`/`*Exception`/`*Failed`/
`Result.*`/`Left`/`Err` value, or calls a logger or reporter. The rule only
looks at catches ERR-001 didn't already report, such as a catch that assigns a
fallback and carries on.

**Why.** Effective Dart: "AVOID catches without `on` clauses." A catch-all
also catches *bugs*: a `TypeError` from a bad cast silently takes the fallback
path. In the data layer, that turns a programming error into wrong data.

```dart
// Bad
String? token;
try {
  token = await _prefs.read('token');
} catch (_) {
  token = null;
}
```

```dart
// Good
try {
  token = await _prefs.read('token');
} on PlatformException catch (e, st) {
  _log.warning('secure storage unavailable', e, st);
  token = null;
}
```

**Grading.** A catch that tries another way (its body calls something, for
example a retry with an inexact alarm) is **Low**. A documented one is
**Info**.

**False positives.** Isolate entry points and worker loops that forward the
error elsewhere (`Isolate.exit(port, Failed('$e'))`). Those use the error value,
so they aren't reported. The rule never applies to presentation logic: an MVN
notifier or MVVM view model catching everything into error state is the
sanctioned boundary.

## ERR-003 catches-error

**Medium** · applies: all · detect: script (the `on` type is `Error` or a
dart:core `Error` subtype)

**Problem.** `on Error`, `on StateError`, `on TypeError`, `on ArgumentError`,
`on RangeError`, `on NoSuchMethodError`, `on UnimplementedError`,
`on UnsupportedError`, `on AssertionError`, `on LateInitializationError` …

**Why.** Effective Dart: "DON'T explicitly catch `Error` or types that
implement it" (lint `avoid_catching_errors`). An `Error` is a bug in the
program. Catching it hides the bug instead of fixing it.

```dart
// Bad
try {
  return items.first;
} on StateError {
  return null;
}
```

```dart
// Good
return items.firstOrNull;      // Dart 3 core iterable extension
```

**Fix.** Validate before the call (`tryParse`, `firstOrNull`, bounds checks),
or fix the cast (`json['id'] as String?`).

**False positives.** A third-party API documented to throw `ArgumentError` or
`UnsupportedError` for an *expected* condition (some platform plugins on web).
Suppress the hit with the API named in the reason.

## ERR-004 repository-leaks-transport-exception

**Medium** · applies: any project with repositories · detect: script
(cross-file)

**Problem.** A public method of a concrete repository either awaits or returns
a call that can throw a network exception, with no `try`/`catch` around it. Or
it calls `jsonDecode` outside a `try`. The network case counts when the
repository:

- imports a network package itself (`dio`, `http`, `retrofit`, `chopper`,
  `graphql`, `web_socket_channel`, `grpc`, `supabase`, `cloud_firestore`,
  `firebase_*`, …, or `dart:io` sockets/`HttpClient`), or
- imports a source, service or core file that does network I/O and doesn't map
  its own exceptions. A file maps its exceptions when a catch in it throws a
  *new* object or builds a `Result`/failure, or when it returns `Result`. This
  is followed up to 3 imports deep.

The rule also fires when a repository catch `rethrow`s a transport or catch-all
exception without mapping it. It reports **once per repository**, listing the
unguarded methods.

Calibration notes (phase 3):
- An awaited call on a field or parameter whose type is a project class that
  reaches no network I/O (for example a `NetworkInfo` connectivity checker or
  a `shared_preferences` cache) is not counted as risky.
- When every risky await sits inside a try whose clauses catch only narrow,
  non-transport types (`on ServerException`, `on CacheException`), the finding
  says so: "N public method(s) catch only ServerException". The typed catch
  doesn't cover the `ClientException`/`SocketException`/`FormatException` the
  source throws (ResoCoder's clean-architecture course).
- Under plain Riverpod, a repository read by a `FutureProvider`,
  `StreamProvider`, `AsyncNotifier` or `AsyncValue.guard` is graded **Low**.
  The provider catches into `AsyncValue.error`, so the remaining issue is the
  wording in the view (ERR-008). MVN keeps Medium, because its notifiers are
  meant to receive mapped failures.

**Why.** Exceptions that cross layers unmapped couple every caller to the
transport (`AP-exceptions-across-layers`, `AP-leaky-repository` in
`flutter-architecture`). One forgotten `try` in the UI is a crash.

```dart
// Bad
@override
Future<List<Movie>> trending() async {
  final rows = await _api.trending();      // DioException, FormatException escape
  return rows.map(Movie.fromJson).toList();
}
```

```dart
// Good (Result style)
@override
Future<Result<List<Movie>>> trending() async {
  try {
    final rows = await _api.trending();
    return Result.ok(rows.map(Movie.fromJson).toList());
  } on DioException catch (e) {
    return Result.error(NetworkFailure.fromDio(e));
  } on FormatException {
    return const Result.error(ParseFailure());
  }
}
```

**Not counted as unguarded:**
- calls inside a `try` that has a non-`Error` catch
- methods that switch on a `Result` (`case Ok`, `is Error`, `.fold(`, `.when(ok:`)
- calls through a guard helper. A guard helper is any function in the project
  whose body catches and whose parameters take a function (`safeCall(() =>
  ...)`, `_guard(...)`, `runCatching`), or a well-known guard name
  (`AsyncValue.guard`, `TaskEither.tryCatch`, …)
- calls to private methods in the same file that are themselves guarded

**Local persistence (drift, sqflite, hive, shared_preferences, path_provider)
is deliberately not counted.** Those failures are rare and usually fatal, and
mapping every DB call is ceremony. Flag them by reading only when the product
needs a "storage full" message.

**False positives.** A Dio interceptor that converts errors still delivers a
`DioException` (with your object in `.error`), so it doesn't make the
repository safe. When the project's convention is "logic catches everything"
(MVN with `catch (e)` in every notifier), this is a Medium design finding, not
a crash. Report it once.

## ERR-005 throws-non-exception

**Medium** · applies: all · detect: script

**Problem.** `throw 'message'`, `throw {...}`, `throw [...]`, `throw 42`,
`throw e.toString()`, `Future.error('message')`, `completer.completeError('message')`.

**Why.** Effective Dart: "DO throw objects that implement `Error` only for
programmatic errors", and lint `only_throw_errors` (opt-in). Callers can't
`on` a string, and string throws carry no type, no fields and no useful
`toString`.

```dart
// Bad
if (page < 1 || page > 604) throw 'Invalid page number';
```

```dart
// Good: a caller bug is an Error; a runtime failure is a typed Exception
if (page < 1 || page > 604) throw RangeError.range(page, 1, 604, 'page');
```

**Fix.** Use `ArgumentError`/`RangeError`/`StateError` for misuse, or a typed
`Exception`/`Failure` subclass for runtime failures.

**False positives.** None that are real. Legacy code whose callers match on the
string can use `err-ignore-file` with that reason.

## ERR-006 domain-throws-transport

**High** for `throw`, **Medium** for `on`/`is` · applies: wherever a domain
layer exists · detect: script

**Problem.** A domain-layer file (entities, use cases, repository contracts)
throws, catches or type-tests a transport type: `DioException`, `DioError`,
`SocketException`, `HttpException`, `ClientException`, `HandshakeException`,
`TlsException`, `FirebaseException`, `FirebaseAuthException`,
`PlatformException`, `MissingPluginException`, `DatabaseException`,
`PostgrestException`, `GrpcError`, `FileSystemException`, `HiveError`,
`IsarError`. (`FormatException` is dart:core and allowed in the domain.)

**Why.** The domain's core guarantee is that it knows nothing about data or
frameworks (ARCH-001/003). Once it throws a transport type, every layer above
it knows about the transport too.

```dart
// Bad (domain/usecases/get_trending.dart)
} on SocketException catch (e) {
  throw HttpException('offline: ${e.message}');
}
```

```dart
// Good: the repository already mapped it; the use case speaks domain
Future<Result<List<Movie>>> call() => _repo.trending();
```

**Fix.** Map in the repository implementation. Give the domain its own
`sealed class Failure`.

**False positives.** A domain-level class *named* like a transport type. Rename
it.

## ERR-007 repository-null-on-failure

**Medium** · applies: repository implementations · detect: script

**Problem.** A repository catch contains `return null;` and its try does I/O
(an `await`, or a call on some receiver other than a collection), or a
`catchError`/`onError` callback in a repository yields `null`. A try that only
does a collection lookup (`list.firstWhere(...)`) is not ERR-007: it's an
ERR-001 Low that suggests `firstWhereOrNull`.

**Why.** `null` already means "not found". Using it for "network down" makes
the two indistinguishable, so the UI shows an empty state instead of an error
and a retry. The `Future<T?>` signature hides the failure from the type system.

```dart
// Bad
Future<User?> me() async {
  try {
    return await _api.me();
  } catch (e) {
    log('me failed', error: e);
    return null;
  }
}
```

```dart
// Good
Future<Result<User?>> me() async { /* Ok(null) = no user; Error(...) = failed */ }
```

**Fix.** Return `Result<T?>` (or `Result<Option<T>>`), or throw a typed
failure. Keep `null` for absence only.

**False positives.** A cache read where *any* failure honestly means "not
cached". Document it and suppress the hit with that reason.

## ERR-008 raw-error-shown-to-user

**Medium** in views and widgets, **Low** in logic and state · applies: all ·
detect: script (presentation-layer files)

**Problem.** These expressions reach a widget or UI state: `e.toString()`,
`'$e'`, `'${e.toString()}'`, `error.toString()`, `snapshot.error.toString()`
and `'${state.error}'`. Here `e` is a catch variable, an `AsyncError`
pattern variable, the first parameter of an `onError:` callback or of a
two-parameter `error:` callback (`AsyncValue.when(error: (e, st) => ...)`), or
one of `error`, `err`, `exception`, `failure`, or the first parameter of a
`catchError((e) ...)` callback. A catch or callback variable only counts inside
its own block, so an unrelated `.map((e) => e.toString())` elsewhere in the file
is ignored. Lines that log (any callee or receiver named like a logger:
`loggy.error`, `_log.warning`, `appLogger.e`, `logError(`, `dPrint(`), assert,
throw, build keys, or sit behind `kDebugMode` are skipped. So is a `toString()`
consumed by a comparison (`.contains(`, `.startsWith(`, `.endsWith(`, `==`).
Each catch block is reported once.

Grading is by enclosing class: a Widget/State class is Medium, a logic class is
Low. A logic class that shows the text directly through a UI sink
(`Get.snackbar`, `Get.dialog`, `Get.defaultDialog`, `*Toast*`, `showSnackBar`,
`SnackBar(`) is Medium.

**Why.** Users see `DioException [bad response]: This exception was thrown
because the response has a status code of 500…`. That text is not localized, it
leaks internals (URLs, SQL), and it changes whenever a package changes.

```dart
// Bad
error: (e, st) => Center(child: Text(e.toString())),
```

```dart
// Good: the logic keeps a typed failure; the UI owns the wording and the l10n
error: (e, st) => ErrorView(message: failureText(context, e), onRetry: retry),

String failureText(BuildContext context, Object e) {
  final l = AppLocalizations.of(context);
  return switch (e) {
    NetworkFailure() => l.errorOffline,
    ServerFailure() => l.errorServer,
    _ => l.errorGeneric,
  };
}
```

**MVN note.** The MVN spec's own example does
`state = MovieError(e.toString())` in the notifier. That's acceptable only
when every failure that reaches the notifier is already a user-safe domain
failure, which is why logic-layer hits are Low. Prefer
`MovieError(failure)` and let the view word it.

**False positives.** A `toString()` overridden on a sealed `Failure` to return
user-safe text. Suppress the hit with that reason. Debug-only error screens
behind `kDebugMode` are already skipped.

## ERR-009 mixed-result-and-throw

**Medium** (a throw in a `Result` method) / **Low** (a signature mix) ·
applies: repositories · detect: script

**Problem.** Either of two things:
- A method returning `Result`/`Either`/`TaskEither` contains `throw` or
  `rethrow` outside a local guarded `try`. Programmer-error throws
  (`UnimplementedError`, `UnsupportedError`, `StateError`, `ArgumentError`,
  `AssertionError`) don't count.
- One repository exposes both `Future<Result<T>>` methods and plain throwing
  `Future<T>` methods (`void` doesn't count). This is reported on the contract
  when it has one.

**Why.** A `Result` signature promises "I don't throw", so callers drop their
`try`. A throw inside it is a guaranteed uncaught exception. A mixed API
forces every caller to remember which style each method uses.

```dart
// Bad
Future<Result<String>> token() async {
  final t = await _api.token();
  if (t.isEmpty) throw const FormatException('empty token');
  return Result.ok(t);
}
```

```dart
// Good
Future<Result<String>> token() async {
  try {
    final t = await _api.token();
    return t.isEmpty ? const Result.error(AuthFailure.noToken()) : Result.ok(t);
  } on DioException catch (e) {
    return Result.error(NetworkFailure.fromDio(e));
  }
}
```

**False positives.** A deliberate migration to `Result`, one repository at a
time. Report it once for the codebase, as Info, and point at the migration
plan rather than at each method.

## ERR-010 loading-without-error-path

**High** · applies: all logic (notifiers, view models, blocs, cubits,
controllers) · detect: script

**Problem.** An async function in a logic file sets a loading state, then
`await`s outside any `try` that has a catch, and doesn't handle a `Result`
(`switch`/`case Ok`/`.fold`) or use a guard (`AsyncValue.guard`). The loading
states it recognises are:
- `state = (const) XLoading(...)`, `state = const AsyncLoading()`,
  `state = AsyncValue.loading()`
- `emit(XLoading())`, `emit(XInProgress())`,
  `emit(state.copyWith(status: S.loading))`
- `_isLoading = true`, `loading = true`, `busy`/`running`/`submitting` flags,
  including `.value = true` on GetX observables

Bloc `on<E>((event, emit) async { ... })` handlers are included, and so is
bloclibrary's `emit(state.copyWith(status: () => S.loading))` /
`emit(XState(status: S.loading))`. So are **State classes** (`extends State<…>`)
that do the work themselves: `setState(() => _isLoading = true)` followed by an
unguarded `await` (setState, Provider and MVC apps, where the State class is
the logic). The note then carries the setState idiom.

An `await` is not counted when:
- it's inside a try whose `finally` resets the same flag (or emits / assigns
  `state` / calls `notifyListeners`): Compass's `Command._execute`;
- the awaited callee returns a `Result`/`Either`, resolved through the field,
  parameter or method type and through typedefs;
- the callee is a project method that can't fail (no throw, no I/O import, only
  pure calls or other infallible project functions, e.g. a fake repository
  that awaits `Future.delayed`);
- it's `emit.forEach(...)` / `emit.onEach(...)` with an `onError:`;
- the awaited chain has `.catchError(handler)` or `.then(..., onError: handler)`
  whose handler emits, assigns state or builds a failure. A handler that does
  none of that is reported as **Medium**: the error is caught but loading never
  ends.

The class that implements `Command*` is skipped: it is the error path.

**Why.** On failure the UI stays loading forever. In a Bloc, the exception goes
to `onError`, and the state never leaves `Loading`. In a Riverpod notifier
method, it escapes to whoever called `notifier.load()`, usually an
`onPressed`, and ends up in `PlatformDispatcher.onError`. In a view model, the
flag never resets. This is the classic "spinner never stops, error not shown"
bug.

```dart
// Bad (Riverpod)
Future<void> refresh() async {
  state = const AsyncLoading();
  state = AsyncData(await _repo.fetch());
}
```

```dart
// Good (Riverpod)
Future<void> refresh() async {
  state = const AsyncLoading();
  state = await AsyncValue.guard(_repo.fetch);
}

// Good (Bloc)
on<TodosRequested>((event, emit) async {
  emit(const TodoLoading());
  try {
    emit(TodoLoaded(await _repo.fetch()));
  } on TodoFailure catch (f) {
    emit(TodoError(f));
  }
});
```

**Fix.** The JSON `note` carries the profile's idiom. MVN: try/catch → XError.
Riverpod: `AsyncValue.guard`. Bloc: emit a failure. MVVM: `Result` + `Command`.
Provider: catch, then `notifyListeners()` in `finally`. GetX: catch, then set
an error observable.

**False positives:**
- A private helper whose call sites are all inside a `try`, or that is wrapped
  by `Command(_load)`, is skipped.
- An `await` on something that truly can't throw (`Future.delayed` is already
  skipped). Suppress the hit with the reason.
- A `try/finally` with no catch is **not** counted when the `finally` resets
  the loading state (changed in phase 3; Compass's `Command` is the canonical
  case). The error still propagates to the caller, which in MVVM receives a
  `Result` anyway.

## ERR-011 rethrow-loses-stack

**Low** · applies: all · detect: script (also lint `use_rethrow_when_possible`,
in the recommended set)

**Problem.** `catch (e) { …; throw e; }`.

**Why.** Effective Dart: "DO use `rethrow` to rethrow a caught exception."
`throw e` starts a new stack trace at the catch, so the crash report points at
the wrong place.

```dart
// Bad
} catch (e) {
  _log(e);
  throw e;
}
```

```dart
// Good
} catch (e, st) {
  _log(e, st);
  rethrow;
}
// or, when mapping:  Error.throwWithStackTrace(NetworkFailure.fromDio(e), st);
```

**False positives.** None.

## ERR-012 missing-global-error-handler

**Medium** when the app depends on a crash reporter (`firebase_crashlytics`,
`sentry_flutter`, `sentry`, `bugsnag_flutter`, `datadog_flutter_plugin`,
`instabug_flutter`, `newrelic_mobile`, …), otherwise **Low** · applies: Flutter
apps with a `lib/main*.dart` that calls `runApp` · detect: script (once per
project)

**Problem.** Somewhere in `lib/`, one or both of these is missing:
- `FlutterError.onError =`, for errors in build, layout, paint and framework
  callbacks
- `PlatformDispatcher.instance.onError =` or `runZonedGuarded(...)`, for
  async errors outside Flutter callbacks

`SentryFlutter.init` and `Bugsnag.start` install both handlers, so they count
for both.

**Why.** The Flutter docs: errors that don't occur within Flutter's callbacks
can't be caught by the framework, and the `PlatformDispatcher` error callback
"by default … only prints errors and does nothing else". Release builds lose
them.

**Fix.** See `references/global-handlers.md` for the full `main()` with
Crashlytics or Sentry.

**False positives.** Handlers installed by a package the checker doesn't know.
Suppress the hit with the package named. Pure Dart packages and plugins without
a `main.dart` aren't checked.

## ERR-013 zone-mismatch

**Medium** · applies: apps using `runZonedGuarded` · detect: script

**Problem.** `WidgetsFlutterBinding.ensureInitialized()` (or
`SentryWidgetsFlutterBinding.ensureInitialized()`) runs in `main` *before*
`runZonedGuarded(() { … runApp(…) … })`.

**Why.** The binding records the zone it was initialized in. Calling `runApp`
from a different zone makes Flutter report a "Zone mismatch" error, and errors
inside the app's zone can then miss the handler you set up.

```dart
// Bad
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runZonedGuarded(() => runApp(const App()), reportError);
}
```

```dart
// Good: everything inside one zone (or drop the zone; see global-handlers.md)
void main() {
  runZonedGuarded(() {
    WidgetsFlutterBinding.ensureInitialized();
    runApp(const App());
  }, reportError);
}
```

**False positives.** None that matter. Most apps today don't need a zone at all,
and `PlatformDispatcher.instance.onError` is the simpler choice.

## ERR-014 unguarded-io-in-ui

**Medium** · applies: all (most common in setState apps) · detect: script

**Problem.** A method or callback of a Widget or State class awaits a network
call (`client.post(`, `widget.httpClient!.get(`, `_dio.get(`, `http.post(`) with
no try/catch and no handled `catchError`, in a file that imports a network
package. When the function also sets a loading flag, ERR-010 reports it
instead.

**Why.** Offline, timeout and TLS errors become uncaught async errors. The
user gets no message, and only the zone or `PlatformDispatcher.onError` sees
the failure (flutter/samples `form_app` shape).

```dart
// Bad
onPressed: () async {
  final res = await widget.httpClient!.post(uri, body: body);
  _showDialog('${res.statusCode}');
},
```

```dart
// Good
onPressed: () async {
  try {
    final res = await widget.httpClient!.post(uri, body: body);
    if (!mounted) return;
    _showDialog(res.statusCode == 200 ? 'Signed in' : 'Unable to sign in');
  } on http.ClientException {
    if (!mounted) return;
    _showDialog('Network problem, try again');
  }
},
```

**Fix.** Catch the transport exception and show a user-safe message, or move
the call into logic (a view model, notifier or bloc) that owns the error state.
See also ARCH-101 (I/O in widgets) in flutter-architecture.

**False positives.** A demo whose client is always a mock. Suppress the hit
with that reason.

## Reading-level findings (ERR-<slug>)

The script can't see these. Look for them when you read the code.

### ERR-result-unguarded-await (High)

A `Future<Result<T>>` method awaits a call that throws, such as a source that
throws `DioException`, outside a `try`. The `Result` signature promises
safety, so the caller has no `try`, and the exception crashes. Wrap the body,
or make the source return `Result` too (the Compass app does that).

### ERR-return-without-await (High)

```dart
Future<User> me() async {
  try {
    return _api.me();          // returns the Future; its error skips this catch
  } on DioException catch (e) {
    throw NetworkFailure.fromDio(e);
  }
}
```

Write `return await _api.me();`. Inside a `try`, the `await` is what routes the
error into the `catch`.

### ERR-unawaited-future (Medium)

`_repo.save(x);` in a sync callback, with no `await` and no `.catchError`, sends
its failure to the zone as an uncaught error. Enable `unawaited_futures` /
`discarded_futures`, then `await` the call, or use `unawaited(f.catchError(report))`
on purpose.

### ERR-error-replaces-data (Medium)

A pull-to-refresh failure replaces the list the user was reading with a
full-screen error. Keep the previous data: Riverpod's `AsyncValue` keeps
`value` across `AsyncLoading`/`AsyncError` (use `.when(skipLoadingOnRefresh:
...)` or check `hasValue`). In Bloc, use the status-enum state with
`status: failure` plus the old `items`. Then show the failure as a snackbar.

### ERR-stringly-failure (Low)

`XError(String message)` built in logic from `e.toString()` or hard-coded
English. Carry a typed `Failure` (or an error code), and word it in the UI with
l10n.

### ERR-effect-in-build (Medium)

`ScaffoldMessenger.of(context).showSnackBar(...)` inside `build()` (or inside a
`BlocBuilder` builder) fires on every rebuild. Move it to `ref.listen`,
`BlocListener`, or a `Command`/view-model listener.

### ERR-context-after-await (High)

A `catch` that uses `context` after an `await`. Check `if (!context.mounted)
return;` first. The `flutter-ui-practices` skill owns this as
`UI-context-after-await`, so report it once, under that ID, when both passes
run.

### ERR-retry-non-idempotent (Medium)

An automatic retry interceptor (for example `dio_smart_retry`) on POST,
payment or "send" calls, or a retry on 4xx and parse failures. Retry only
idempotent requests and only on transient failures: connection errors,
timeouts, 5xx, and 429 with `Retry-After`.

### ERR-double-report (Low)

The repository logs, the notifier logs, and the global handler reports, so one
failure becomes three crash-dashboard entries. Report once: at the boundary
that swallows or maps the error, or in the global handler for what escapes.

### ERR-provider-exception (Low)

Riverpod 3 wraps errors you read through providers (`ref.read(p.future)`,
`requireValue`) in `ProviderException`, so `on DioException` around them no
longer matches. `AsyncValue.error`, `ref.listen(onError:)` and observers still
get the original error. Catch `ProviderException` and switch on `e.exception`,
or, better, keep catching at the repository.
