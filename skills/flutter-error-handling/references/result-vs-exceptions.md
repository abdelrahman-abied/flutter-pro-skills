# Result or exceptions?

Both styles work. What breaks an app is the absence of a decision: some
repositories throw, some return `null`, some return `Result`, and every caller
guesses. Pick one style per codebase (precedence rule 1: an existing,
consistent project style wins), then apply it the same way everywhere.

## Contents

- The decision
- A minimal Result (the Flutter docs' shape)
- Typed failures
- Mapping transport exceptions (Dio, http, platform, parsing)
- Error vs Exception, and what to catch
- When exceptions are fine
- Retry
- Migrating from exceptions to Result

## The decision

| Question | Points to `Result` | Points to exceptions |
|---|---|---|
| Does the project already use one consistently? | It uses `Result`/`Either` | It throws typed failures and catches them in logic |
| Architecture | Flutter MVVM with `Command` (the Compass app pairs them); Clean Architecture with `Either` | MVN (the spec's notifier does `try/catch` → `XError`); Bloc samples (repositories throw, blocs catch); Riverpod `AsyncValue.guard` |
| Team discipline | Forgetting a `try` keeps happening | Everyone knows which layer catches |
| Expected failures (offline, 404, validation) | They are part of the API, so make them visible in the type | They are rare, and handled at one boundary |
| Composition | Fallback chains (`api` else `cache` else `temp`) read linearly | One call per action |

The Flutter guide on `Result`: Dart exceptions are unchecked, so "developers
might forget to catch exceptions". `Result` "forces the calling method to check
for errors" and "helps improve control flow compared to try-catch blocks". The
guide presents it as a recommendation, not a requirement.

**Rule of thumb.** Use `Result` when failures are part of normal operation and
many callers consume the same repository. Use typed exceptions when one logic
layer catches everything anyway, as in MVN, Bloc and Riverpod with
`AsyncValue.guard`. Never use `null` to mean failure (ERR-007).

## A minimal Result (the Flutter docs' shape)

This is the `Result` from the Flutter architecture guide's design patterns
page, as used in the Compass app. Keep the `Ok`/`Error` names if the project
follows the guide.

```dart
/// Ok holds a value, Error holds an Exception. Evaluate with a switch:
///   switch (result) { case Ok(:final value): ...; case Error(:final error): ... }
sealed class Result<T> {
  const Result();

  /// Creates a successful [Result], completed with the specified [value].
  const factory Result.ok(T value) = Ok._;

  /// Creates an error [Result], completed with the specified [error].
  const factory Result.error(Exception error) = Error._;
}

final class Ok<T> extends Result<T> {
  const Ok._(this.value);
  final T value;

  @override
  String toString() => 'Result<$T>.ok($value)';
}

final class Error<T> extends Result<T> {
  const Error._(this.error);
  final Exception error;

  @override
  String toString() => 'Result<$T>.error($error)';
}
```

Notes:
- `Error` shadows `dart:core`'s `Error` inside files that import it. That's the
  docs' choice, and harmless, because you shouldn't catch `Error` anyway
  (ERR-003). Projects that dislike the clash use `Failure`/`Err` or a package
  (`result_dart`, `multiple_result`, `fpdart`'s `Either`). Whatever you
  choose, don't mix two.
- `Error` holds `Exception`, not `Object`. That keeps programming errors
  (`Error` subtypes) out of results, so they crash and get fixed.
- Unwrap with an exhaustive `switch`. Never use `as Ok` or `(result as
  Ok).value`.

```dart
// Fallback chains read linearly with Result (from the Flutter guide)
Future<Result<UserProfile>> getUserProfile() async {
  final apiResult = await _apiClientService.getUserProfile();
  if (apiResult is Ok) return apiResult;

  final databaseResult = await _databaseService.createTemporaryUser();
  if (databaseResult is Ok) return databaseResult;

  return Result.error(Exception('Failed to get user profile'));
}
```

Optional helpers, if the project wants them (keep them tiny):

```dart
extension ResultX<T> on Result<T> {
  T? get valueOrNull => switch (this) { Ok(:final value) => value, Error() => null };
  Result<R> map<R>(R Function(T) f) => switch (this) {
        Ok(:final value) => Result.ok(f(value)),
        Error(:final error) => Result.error(error),
      };
}
```

## Typed failures

Map every transport exception to a small, sealed set of domain failures. The
UI can then `switch` on them exhaustively and pick the wording.

```dart
// domain/failures.dart (or core/error/failure.dart): no Flutter, no Dio imports
sealed class Failure implements Exception {
  const Failure({this.cause, this.stackTrace});
  final Object? cause;          // keep it for logging and crash reports
  final StackTrace? stackTrace;
}

final class NetworkFailure extends Failure {     // offline, DNS, timeouts
  const NetworkFailure({super.cause, super.stackTrace});
}

final class ServerFailure extends Failure {      // 5xx, unexpected status
  const ServerFailure(this.statusCode, {super.cause, super.stackTrace});
  final int? statusCode;
}

final class UnauthorizedFailure extends Failure { // 401/403: sign the user out
  const UnauthorizedFailure({super.cause, super.stackTrace});
}

final class NotFoundFailure extends Failure {
  const NotFoundFailure({super.cause, super.stackTrace});
}

final class ValidationFailure extends Failure {  // 400/422 with field errors
  const ValidationFailure(this.fields, {super.cause, super.stackTrace});
  final Map<String, String> fields;
}

final class ParseFailure extends Failure {       // FormatException, bad JSON shape
  const ParseFailure({super.cause, super.stackTrace});
}
```

Guidelines:
- Keep the set small (5–8 kinds), and add a kind only when the UI reacts to it
  differently.
- Failures `implements Exception`. They work with `on Failure catch` and with
  `Result.error`.
- Failures carry *data* (status code, field errors), not user-facing English.
  The presentation layer maps kind to localized text, because that's where
  `BuildContext` and l10n live:

```dart
// presentation/failure_text.dart
String failureText(AppLocalizations l, Object error) => switch (error) {
      NetworkFailure() => l.errorOffline,
      UnauthorizedFailure() => l.errorSessionExpired,
      NotFoundFailure() => l.errorNotFound,
      ValidationFailure() => l.errorCheckFields,
      ServerFailure() || ParseFailure() => l.errorServer,
      _ => l.errorGeneric,                    // never '$error'
    };
```

## Mapping transport exceptions

Do it once, in the data layer: a helper beside the repositories, or in the
repository itself.

### Dio (5.x)

```dart
Failure mapDio(DioException e, StackTrace st) {
  switch (e.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.connectionError:
      return NetworkFailure(cause: e, stackTrace: st);
    case DioExceptionType.badCertificate:
      return ServerFailure(null, cause: e, stackTrace: st);   // report: maybe pinning or MITM
    case DioExceptionType.badResponse:
      final code = e.response?.statusCode;
      return switch (code) {
        401 || 403 => UnauthorizedFailure(cause: e, stackTrace: st),
        404 => NotFoundFailure(cause: e, stackTrace: st),
        400 || 422 => ValidationFailure(_fields(e.response?.data), cause: e, stackTrace: st),
        _ => ServerFailure(code, cause: e, stackTrace: st),
      };
    case DioExceptionType.cancel:
      throw e;   // a cancelled request is not a failure to show; let the caller ignore it
    case DioExceptionType.unknown:
      return e.error is SocketException
          ? NetworkFailure(cause: e, stackTrace: st)
          : ServerFailure(null, cause: e, stackTrace: st);
  }
}
```

### package:http

`http` does **not** throw on 4xx or 5xx, so check the status yourself. It
throws `ClientException` (and `SocketException` on `dart:io`) for transport
failures. A `.timeout(...)` throws `TimeoutException`.

```dart
Future<Result<User>> me() async {
  try {
    final res = await _client.get(_uri('/me')).timeout(const Duration(seconds: 10));
    if (res.statusCode == 401) return const Result.error(UnauthorizedFailure());
    if (res.statusCode != 200) return Result.error(ServerFailure(res.statusCode));
    return Result.ok(User.fromJson(jsonDecode(res.body) as Map<String, dynamic>));
  } on TimeoutException catch (e, st) {
    return Result.error(NetworkFailure(cause: e, stackTrace: st));
  } on http.ClientException catch (e, st) {
    return Result.error(NetworkFailure(cause: e, stackTrace: st));
  } on FormatException catch (e, st) {
    return Result.error(ParseFailure(cause: e, stackTrace: st));
  }
}
```

### Others

| Thrown by | Type | Usually maps to |
|---|---|---|
| plugins / method channels | `PlatformException` (`code`, `message`), `MissingPluginException` | a feature-specific failure; "unsupported" on `MissingPluginException` |
| `jsonDecode`, `int.parse`, `Uri.parse` | `FormatException` | `ParseFailure` (or prefer `tryParse`) |
| a bad JSON *shape* (`json['id'] as String`) | `TypeError` (an `Error`) | fix the DTO (`as String?` plus validation). Don't catch `TypeError` (ERR-003); validate in `fromJson` and throw `FormatException` |
| Firebase | `FirebaseException` (`plugin`, `code`), `FirebaseAuthException` | switch on `code` |
| `dart:io` files | `FileSystemException`, `PathNotFoundException` | a storage failure, or "not found" |
| sqflite / drift | `DatabaseException` / `SqliteException` | usually fatal: report it, don't map every call |

## Error vs Exception, and what to catch

From Effective Dart:
- **DO throw `Error` subtypes only for programmatic errors**: `ArgumentError`,
  `RangeError`, `StateError`, `UnimplementedError`. They mean "the caller has
  a bug". Runtime failures that a correct program can still hit (network, IO,
  bad input from outside) are `Exception`s.
- **DON'T explicitly catch `Error`** or its subtypes (`avoid_catching_errors`).
- **AVOID catches without `on` clauses** (`avoid_catches_without_on_clauses`,
  opt-in). Catch-alls belong at boundaries: the logic layer, global handlers,
  isolate entries. Even there, **DON'T discard** what they catch.
- **DO use `rethrow`** (`use_rethrow_when_possible`). To map and keep the
  original trace, use `Error.throwWithStackTrace(mapped, st)`.
- **Never throw strings or maps** (`only_throw_errors`, ERR-005).

## When exceptions are fine

- **One boundary catches everything**: MVN notifiers, Bloc event handlers, and
  Riverpod's `AsyncValue.guard`. Repositories throw *typed* failures, and the
  logic layer has a single `try/catch` or a guard per action. This is the MVN
  spec's own style. Don't demand `Result` there (see `AP-exceptions-across-layers`
  in `flutter-architecture`: "Don't demand `Result` where the project
  consistently uses exceptions *and* catches them").
- **Programming errors** (`StateError`, `ArgumentError`) should *always* throw.
  Never wrap them in `Result`.
- **Inside the data layer**, between a source and its repository. The source
  throws and the repository maps. `Result` only has to start at the
  repository boundary.
- **Streams**: errors travel as stream error events. Handle them with
  `onError:`, `handleError`, `emit.forEach(onError:)`, or let `StreamProvider`
  turn them into `AsyncError`.

## Retry

- **What**: only transient failures (`NetworkFailure`, `ServerFailure` with
  5xx, and 429 with `Retry-After`). Never retry 4xx, `ParseFailure` or
  `ValidationFailure`. They fail the same way again.
- **Which requests**: GET and other idempotent calls. Retry a POST, a payment
  or a "send" only with an idempotency key the backend honours.
- **How**: exponential backoff with jitter and a cap (for example 0.5s, 1s, 2s,
  then stop), only while the screen still needs the result (check `ref.mounted`,
  `isClosed`, or the `mounted` State).
- **User retry beats silent retry**: render the error state with a Retry
  button that re-runs the action. Examples: `ref.invalidate(provider)`,
  `notifier.load()`, `bloc.add(Requested())`, `command.execute()`.
- **Riverpod 3** retries *providers* that fail during initialization
  automatically, with exponential backoff (200ms doubling, up to 6.4s). It
  doesn't retry `ProviderException`s. Configure it with `retry:` on the
  provider or on `ProviderScope`, and return `null` to stop. Don't stack your
  own retry loop on top for the same provider.

## Migrating from exceptions to Result

1. Add `Result` and the `Failure` set, but keep the old APIs.
2. Convert one repository *contract* at a time, so the whole repository returns
   `Result` at once (no ERR-009 mix within a repository).
3. Update its callers: the logic switches on the `Result`, and its `try/catch`
   goes away.
4. Record the plan in your agent's project instructions file (`AGENTS.md`,
   `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
   `.github/copilot-instructions.md`) so reviewers report the mix once, as
   Info, during the migration.
