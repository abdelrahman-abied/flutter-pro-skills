# Secure scaffold checklist

The rules every generated feature follows, so code from
`flutter-feature-scaffold` is secure by default without a later pass. This
file is the contract for the scaffold templates
(`../flutter-feature-scaffold/assets/templates/**`) and for anyone writing a
feature by hand. Each rule names the template role it applies to and the
check that verifies it.

**Acceptance test for the templates:** for every profile (mvn, mvvm, bloc,
cubit, getx, provider, riverpod, each with and without `--clean`), the
scaffold output gives **zero findings** from
`python3 -I ../flutter-secure-defaults/scripts/check_secure_defaults.py <project>`
and zero ERR-008 from `check_errors.py`, plus the architecture checks the
scaffold already runs.

## Contents

1. All generated files
2. Source / data source / service
3. Repository implementation
4. DTOs (request / response models)
5. Logic (notifier, view model, bloc, cubit, controller)
6. State
7. View and widgets
8. Shared network setup (when the scaffold creates or extends it)
9. Tests
10. TODO markers the scaffold prints

## 1. All generated files

| # | Rule | Verified by |
|---|---|---|
| S-1 | No `print`, `debugPrint` or `stdout`. Generated code logs through nothing, or through the project's existing logger if one is detected | `avoid_print` lint; SEC-004 |
| S-2 | No string literal that looks like a credential, and no `http://` URL. Placeholders are `TODO` comments, never fake keys like `'YOUR_API_KEY'` in code | SEC-008, SEC-003 |
| S-3 | No top-level or `static` mutable fields | SEC-010, ARCH-105 |
| S-4 | No `String.fromEnvironment` reads in feature code. Config comes from the injected client or `AppConfig` | SEC-009, `AP-hardcoded-config-in-sources` |

## 2. Source / data source / service

| # | Rule | Verified by |
|---|---|---|
| S-5 | The source receives the **configured** HTTP client (Dio, `http.Client`, `GetConnect`) through its constructor or provider. It never constructs `Dio()` or sets `BaseOptions`, so it can't skip the app's auth interceptor, timeouts or pinning | ARCH-101; reading |
| S-6 | The source **never sets `Authorization`** or any auth header. The TODO says: "auth headers are added by the shared client's interceptor" | SEC-002 |
| S-7 | Request bodies are built from a typed request DTO (`toJson`), never from widget values or maps assembled in the UI | reading |
| S-8 | The source never logs requests or responses (no `response.data`, no bodies) | SEC-011 |
| S-9 | Paths are relative (`'/orders'`). The base URL lives in the shared client | SEC-003 |

```dart
final class OrderRemoteSource implements OrderSource {
  const OrderRemoteSource(this._dio); // the app's configured client: base URL, auth interceptor, timeouts
  final Dio _dio;

  @override
  Future<List<OrderResponse>> fetchOrders() async {
    final res = await _dio.get<List<Object?>>('/orders');
    return [for (final row in res.data ?? const []) OrderResponse.fromJson(row)];
  }
}
```

## 3. Repository implementation

| # | Rule | Verified by |
|---|---|---|
| S-10 | The repository **never logs request or response bodies**, and never logs exceptions with their payload (`'$e'` on a `DioException` includes the request) | SEC-011, SEC-004 |
| S-11 | Transport exceptions are mapped to typed domain failures. The failure carries no server message, URL or headers | ERR-004, ERR-008 |
| S-12 | Public methods return entities, never DTOs, `Response` or raw maps | ARCH-107 |
| S-13 | If the feature stores anything locally, the TODO points to secure storage for anything sensitive and SharedPreferences only for preferences | SEC-001 |

## 4. DTOs (request / response models)

| # | Rule | Verified by |
|---|---|---|
| S-14 | `fromJson` validates types with a pattern match (or checked casts) and throws `FormatException` on a bad shape, never a `TypeError` from `as` | reading; ERR-003 |
| S-15 | `toString()` is not overridden to print every field. If generated (freezed, equatable), the TODO notes "don't add tokens or personal data to this DTO's props" | reading |
| S-16 | DTOs never carry tokens. Auth responses are the auth feature's concern | SEC-010 |

```dart
final class OrderResponse {
  const OrderResponse({required this.id, required this.total});
  final String id;
  final int total;

  static OrderResponse fromJson(Object? json) => switch (json) {
        {'id': final String id, 'total': final int total} => OrderResponse(id: id, total: total),
        _ => throw const FormatException('unexpected order payload'),
      };
}
```

## 5. Logic (notifier, view model, bloc, cubit, controller)

| # | Rule | Verified by |
|---|---|---|
| S-17 | Logic **holds no token or credential** and never reads secure storage | SEC-010 |
| S-18 | Errors become typed failure state. Logic never stores `e.toString()` | ERR-008 |
| S-19 | No header, URL or query-string building with user data in logic. It calls a use case or repository with typed arguments | SEC-002 |
| S-20 | Bloc: no `HydratedBloc` by default. If the project uses it, the TODO warns against hydrating credentials | SEC-010 |

## 6. State

| # | Rule | Verified by |
|---|---|---|
| S-21 | State classes contain display data only: no tokens, passwords or raw server error text | SEC-010, ERR-008 |
| S-22 | The error variant holds a typed failure, which the view maps to localized, user-safe text | ERR-008 |

## 7. View and widgets

| # | Rule | Verified by |
|---|---|---|
| S-23 | No I/O, no headers, no storage access in widgets | ARCH-101, ARCH-005, SEC-002 |
| S-24 | Error UI shows a localized message chosen from the failure type, never `failure.toString()` | ERR-008 |
| S-25 | Generated text fields, if any, have `autofillHints`, and password fields use `obscureText: true` (`flutter-forms`) | FORM checks |
| S-26 | No `WebView` and no `launchUrl` in templates. If a feature needs one, the TODO links `webview-and-links.md` and NAV-005 | SEC-007, NAV-005 |

## 8. Shared network setup (when the scaffold creates or extends it)

The scaffold doesn't generate auth. If it creates a shared client (for
example plain Riverpod's `di/<feature>_providers.dart`), it follows these
rules:

| # | Rule | Verified by |
|---|---|---|
| S-27 | The client is created once, at the composition root or in `core/network`, with connect and receive timeouts | reading |
| S-28 | The base URL comes from `AppConfig` / a flavor. If one must be a literal, it's `https://` | SEC-003 |
| S-29 | HTTP logging interceptors are added only inside `if (kDebugMode)`, with `requestHeader: false` | SEC-005 |
| S-30 | No `badCertificateCallback`, `onBadCertificate` or `validateCertificate` overrides | SEC-006 |
| S-31 | When the project already has an auth interceptor, reuse that client. Never create a second, unauthenticated client for an authenticated API | reading |

## 9. Tests

| # | Rule | Verified by |
|---|---|---|
| S-32 | Fakes return fake data with obviously fake identifiers (`'order-1'`). Never put real-looking tokens or keys in test code (secret scanners and push protection block them) | SEC-008 on `test/` if scanned; CI secret scanning |
| S-33 | A repository test asserts that a transport failure maps to a typed failure with no raw message | `flutter-testing` |

## 10. TODO markers the scaffold prints

The scaffold already counts its TODOs. These are the security ones, worded so
the agent filling them in follows the defaults:

- source: `// TODO: call the backend through the injected client; auth headers come from its interceptor.`
- repository: `// TODO: map transport exceptions to typed failures; never log request or response bodies.`
- local storage (if any): `// TODO: secrets go to flutter_secure_storage via a data-layer source; SharedPreferences is for preferences only.`
- DTO: `// TODO: validate the JSON shape here; throw FormatException on a mismatch.`
- view: `// TODO: map the failure to a localized, user-safe message.`
