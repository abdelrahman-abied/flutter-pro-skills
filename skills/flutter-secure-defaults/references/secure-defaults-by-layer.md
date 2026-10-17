# Secure defaults by layer and architecture

Where each security default lives, per pattern, with Dart 3 code. One rule
sits under every section: **the credential is a data-layer detail**. A source
reads it from secure storage, the HTTP client attaches it, and an interceptor
refreshes it. Logic and UI see the *session* (`SignedIn(user)`), never the
token. This keeps the token out of state, logs, observers, DevTools, widget
tests and `toString()`, and it gives you exactly one place to change when
the auth scheme changes.

Pattern rules come from each pattern's canonical source (the MVN spec,
docs.flutter.dev's architecture guide and the Compass app, bloclibrary.dev,
riverpod.dev, the GetX docs). Read `../flutter-architecture/references/<pattern>.md`
for the layering itself. This file adds only the security placement.

## Contents

1. The shared building blocks (token storage, interceptor, session, logout)
2. MVN (Riverpod codegen + use cases)
3. MVVM (Flutter guide, Compass)
4. Bloc / Cubit
5. Clean Architecture (use cases + get_it)
6. Provider (ChangeNotifier)
7. GetX
8. Plain Riverpod
9. Placement checklist for reviews

## 1. The shared building blocks

These four pieces are the same in every pattern. Only the folder and the DI
wiring change.

### 1.1 Token storage: one source, platform secure storage

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The only class that knows where credentials live.
final class TokenStorage {
  const TokenStorage(this._secure);

  static const _accessKey = 'access_token';   // a key *name*, not a secret
  static const _refreshKey = 'refresh_token';

  final FlutterSecureStorage _secure;

  Future<String?> readAccess() => _secure.read(key: _accessKey);
  Future<String?> readRefresh() => _secure.read(key: _refreshKey);

  Future<void> save({required String access, required String refresh}) async {
    await _secure.write(key: _accessKey, value: access);
    await _secure.write(key: _refreshKey, value: refresh);
  }

  Future<void> clear() => _secure.deleteAll();
}

const secureStorage = FlutterSecureStorage(
  // Off iCloud Keychain sync and not readable before the first unlock.
  iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
);
```

- Keep the storage behind a small interface if you need a fake in tests (the
  Flutter guide's "interface only when there's a second implementation"
  applies: the fake is the second implementation).
- Read the token **when a request needs it**, not once into a field. If you
  cache it in memory for speed, keep the cache private to this class and
  clear it in `clear()` (SEC-010 grades a private cache Low).

### 1.2 The auth interceptor: header plus single-flight refresh

```dart
import 'package:dio/dio.dart';

final class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor(this._tokens, {required Dio refreshClient, required this.onSignedOut})
      : _refreshClient = refreshClient;

  final TokenStorage _tokens;
  final Dio _refreshClient;              // a second Dio WITHOUT this interceptor
  final Future<void> Function() onSignedOut;

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final access = await _tokens.readAccess();
    if (access != null) options.headers['Authorization'] = 'Bearer $access';
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final retried = err.requestOptions.extra['auth_retried'] == true;
    if (err.response?.statusCode != 401 || retried) return handler.next(err);
    final refresh = await _tokens.readRefresh();
    if (refresh == null) return handler.next(err);
    try {
      final res = await _refreshClient.post<Map<String, dynamic>>(
        '/auth/refresh',
        data: {'refresh_token': refresh},
      );
      final (access, next) = _parseTokens(res.data);
      await _tokens.save(access: access, refresh: next);
      final retry = err.requestOptions
        ..extra['auth_retried'] = true
        ..headers['Authorization'] = 'Bearer $access';
      handler.resolve(await _refreshClient.fetch<Object?>(retry));
    } on DioException {
      await onSignedOut();               // refresh failed: the session is over
      handler.next(err);
    }
  }

  (String, String) _parseTokens(Map<String, dynamic>? body) => switch (body) {
        {'access_token': final String a, 'refresh_token': final String r} => (a, r),
        _ => throw const FormatException('refresh response without tokens'),
      };
}
```

Why each detail matters:
- **`QueuedInterceptor`** runs the handlers one at a time. Five parallel
  requests that all get 401 cause *one* refresh. Then the rest read the new
  token. With a plain `Interceptor`, rotating refresh tokens log the user out
  (the second refresh uses a token the first one already revoked).
- **A second client for the refresh call.** If the refresh call itself goes
  through `AuthInterceptor`, a 401 on refresh recurses.
- **One retry** (`auth_retried`). A server that keeps answering 401 must not
  loop.
- **Sign-out on refresh failure**, through a callback the session owner
  provides. The interceptor doesn't know about UI.
- The pattern-matched `_parseTokens` validates the response shape at the
  boundary instead of `as String` casts that throw `TypeError` deep inside.

### 1.3 Session state: who, not how

```dart
sealed class Session {
  const Session();
}

final class SignedOut extends Session {
  const SignedOut();
}

final class SignedIn extends Session {
  const SignedIn(this.user);
  final User user;                       // id, display name, roles for *display*
}
```

Roles in `User` are for showing or hiding UI. The server re-checks every
action (`SEC-client-side-authz`).

### 1.4 Logout: wipe, in this order

```dart
Future<void> signOut() async {
  await _api.revoke().catchError((Object _) {});  // best effort: the server forgets the refresh token
  await _tokens.clear();                          // 1. credentials
  await _db.clearUserData();                      // 2. user databases, Hive boxes, caches
  await _prefs.remove('last_user_id');            // 3. user-scoped preferences (keep device settings)
  await WebViewCookieManager().clearCookies();    // 4. WebView sessions
  await _firebaseAuth.signOut();                  // 5. third-party SDK sessions
  _cancelToken.cancel('signed out');              // 6. in-flight requests
  // 7. reset session state through the pattern's mechanism (see each section)
}
```

The order matters. Credentials go first, so a crash halfway through still
leaves the user signed out. The `catchError` on `revoke()` is a documented
best-effort call: an offline logout must still log out.

**First launch after install (iOS).** The Keychain survives uninstall, so a
reinstalled app (or a second-hand phone) starts signed in. Store a
non-secret marker in SharedPreferences, which *is* wiped on uninstall:

```dart
Future<void> clearKeychainOnFreshInstall(SharedPreferences prefs, TokenStorage tokens) async {
  if (prefs.getBool('installed') ?? false) return;
  await tokens.clear();
  await prefs.setBool('installed', true);
}
```

## 2. MVN (Riverpod codegen + use cases)

The MVN spec: View → Notifier → UseCase → Repository → Source. The token
lives at the Source end. Sources are leaves that "never read or watch UI
state".

```text
lib/
├── core/network/
│   ├── dio_provider.dart          # Dio + AuthInterceptor (+ LogInterceptor only in kDebugMode)
│   └── auth_interceptor.dart
└── features/auth/
    ├── domain/
    │   ├── entities/user.dart
    │   ├── repositories/auth_repository.dart     # abstract interface class
    │   └── usecases/sign_in.dart, sign_out.dart  # + their @riverpod providers (the DI seam)
    ├── data/
    │   ├── sources/auth_remote_source.dart       # login/refresh/revoke calls
    │   ├── sources/token_source.dart             # FlutterSecureStorage + @riverpod
    │   └── repositories/auth_repository_impl.dart
    └── presentation/
        ├── notifier/auth_notifier.dart           # holds AuthState (user), no token
        ├── state/auth_state.dart
        └── view/sign_in_view.dart
```

```dart
// data/sources/token_source.dart
@riverpod
TokenStorage tokenSource(Ref ref) => const TokenStorage(secureStorage);

// core/network/dio_provider.dart
@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final options = BaseOptions(baseUrl: AppConfig.apiBaseUrl);
  final dio = Dio(options);
  dio.interceptors.add(AuthInterceptor(
    ref.watch(tokenSourceProvider),
    refreshClient: Dio(options),
    onSignedOut: () async => ref.read(authProvider.notifier).signedOutRemotely(),
  ));
  if (kDebugMode) dio.interceptors.add(LogInterceptor(requestHeader: false));
  return dio;
}

// presentation/notifier/auth_notifier.dart
@riverpod
class AuthNotifier extends _$AuthNotifier {
  @override
  AuthState build() => const AuthSignedOut();

  Future<void> signIn(Credentials c) async {
    state = const AuthLoading();
    try {
      final user = await ref.read(signInProvider)(c);   // the use case; the token never comes back up
      state = AuthSignedIn(user);
    } on AuthFailure catch (f) {
      state = AuthError(f);
    }
  }

  Future<void> signOut() async {
    await ref.read(signOutProvider)();                  // repository wipes storage, db, cookies
    ref.invalidate(profileProvider);                    // drop every user-scoped provider
    state = const AuthSignedOut();
  }

  void signedOutRemotely() => state = const AuthSignedOut();
}
```

- The repository's `signIn` returns a `User`, not a token. The repository
  impl saves the tokens through `TokenStorage`.
- A `@riverpod String? token(Ref ref)` provider is a smell (SEC-010 reports
  token providers): any widget can `ref.watch` it.
- In a `ProviderObserver` that logs updates, never log values of auth
  providers.

## 3. MVVM (Flutter guide, Compass)

The guide: views call view-model commands, view models call repositories,
and repositories own services. In the Compass app, the API client takes an
**auth-header provider** that the auth repository sets. That keeps the
header in the data layer.

```dart
// data/services/api_client.dart
typedef AuthHeaderProvider = String? Function();

final class ApiClient {
  ApiClient(this._http, {required Uri baseUrl}) : _baseUrl = baseUrl;
  final HttpClient _http;
  final Uri _baseUrl;
  AuthHeaderProvider? _authHeaderProvider;
  set authHeaderProvider(AuthHeaderProvider p) => _authHeaderProvider = p;

  Future<HttpClientRequest> _open(String method, String path) async {
    final req = await _http.openUrl(method, _baseUrl.resolve(path));
    final header = _authHeaderProvider?.call();
    if (header != null) req.headers.set(HttpHeaders.authorizationHeader, header);
    return req;
  }
}

// data/repositories/auth/auth_repository_remote.dart
final class AuthRepositoryRemote extends AuthRepository {   // AuthRepository extends ChangeNotifier
  AuthRepositoryRemote(this._api, this._authApi, this._tokens) {
    _api.authHeaderProvider = () => _cachedToken == null ? null : 'Bearer $_cachedToken';
  }
  final ApiClient _api;
  final AuthApiClient _authApi;
  final TokenStorage _tokens;
  String? _cachedToken;                  // private to the repository: the session owner

  @override
  Future<bool> get isAuthenticated async => (_cachedToken ??= await _tokens.readAccess()) != null;

  @override
  Future<Result<void>> logout() async {
    _cachedToken = null;
    await _tokens.clear();
    notifyListeners();                   // the router's refreshListenable redirects to /login
    return const Result.ok(null);
  }
}
```

- The Compass sample keeps its demo token in a `SharedPreferencesService`.
  That's fine for a sample, but in a real app make that service wrap
  `flutter_secure_storage` (SEC-001). Nothing else changes.
- View models expose `isAuthenticated` and the `User`. A `LogoutViewModel`
  runs `logout` through a `Command0`. The view never touches the repository.

## 4. Bloc / Cubit

bloclibrary's login tutorial uses an `AuthenticationRepository` that exposes a
`Stream<AuthenticationStatus>`, a `UserRepository`, and an
`AuthenticationBloc` that holds the status and the `User`. The token belongs
inside the repository's data provider.

```dart
enum AuthenticationStatus { unknown, authenticated, unauthenticated }

final class AuthenticationRepository {
  AuthenticationRepository(this._api, this._tokens);
  final AuthApi _api;                    // data provider
  final TokenStorage _tokens;            // data provider
  final _controller = StreamController<AuthenticationStatus>();

  Stream<AuthenticationStatus> get status async* {
    yield await _tokens.readAccess() == null
        ? AuthenticationStatus.unauthenticated
        : AuthenticationStatus.authenticated;
    yield* _controller.stream;
  }

  Future<void> logIn({required String username, required String password}) async {
    final t = await _api.login(username, password);
    await _tokens.save(access: t.access, refresh: t.refresh);
    _controller.add(AuthenticationStatus.authenticated);
  }

  Future<void> logOut() async {
    await _tokens.clear();
    _controller.add(AuthenticationStatus.unauthenticated);
  }

  void dispose() => _controller.close();
}
```

- `AuthenticationState` holds `status` and `User`. A `refreshToken` field in
  bloc state is SEC-010, and it's **Medium in a `HydratedBloc`**, which writes
  state to disk (unencrypted unless you pass `HydratedAesCipher`).
- The login form's `LoginState` holding `Password` while the user types is
  the tutorial's sanctioned pattern. It's transient, so don't flag it. Do flag
  it if it's persisted or logged (`flutter-forms` FORM-004).
- A `BlocObserver` that prints every `onChange` prints every state. With a
  token in state, that's a log leak. Keep observers to type names in release.
- On logout, blocs that hold user data reset when `AuthenticationBloc` emits
  `unauthenticated`, because the app re-creates them under the signed-in
  subtree. Don't make blocs call each other (`AP-bloc-to-bloc`).

## 5. Clean Architecture (use cases + get_it)

```text
lib/
├── core/network/{dio_client.dart, auth_interceptor.dart}
├── core/di/injection.dart                     # get_it registrations (composition root)
└── features/auth/
    ├── domain/{entities/user.dart, repositories/auth_repository.dart, usecases/{sign_in,sign_out,watch_session}.dart}
    ├── data/{datasources/{auth_remote_data_source,auth_local_data_source}.dart, repositories/auth_repository_impl.dart, models/token_model.dart}
    └── presentation/…                         # bloc, cubit or notifier per the project
```

- `AuthLocalDataSource` wraps `TokenStorage`. `AuthRemoteDataSource` uses the
  configured Dio, so it never sets headers.
- Domain entities never carry tokens: `TokenModel` is a data-layer DTO.
  `SignIn` returns `Either<Failure, User>` (or `Result<User>`).
- Register `AuthInterceptor` once in `injection.dart`:
  `sl.registerLazySingleton(() => DioClient(sl<AuthInterceptor>()))`. Don't
  `sl<TokenStorage>()` from presentation code (ARCH-104).

## 6. Provider (ChangeNotifier)

```dart
final class AuthModel extends ChangeNotifier {
  AuthModel(this._auth);
  final AuthService _auth;               // data layer: secure storage + API
  User? _user;
  User? get user => _user;
  bool get isSignedIn => _user != null;

  Future<void> signIn(String email, String password) async {
    _user = await _auth.signIn(email, password);   // tokens saved inside AuthService
    notifyListeners();
  }

  Future<void> signOut() async {
    await _auth.signOut();                          // wipes storage and caches
    _user = null;
    notifyListeners();
  }
}
```

Provide the HTTP client and `AuthService` above `AuthModel` in the
`MultiProvider` at the root. Widgets `context.watch<AuthModel>()`, and never
`context.read<AuthService>()` to fetch a token.

## 7. GetX

```dart
final class AuthService extends GetxService {
  AuthService(this._tokens);
  final TokenStorage _tokens;
  final user = Rxn<User>();

  Future<void> signOut() async {
    await _tokens.clear();
    user.value = null;
    Get.offAllNamed(Routes.login);       // navigation in GetX services/controllers is the pattern's idiom
  }
}

final class ApiProvider extends GetConnect {
  ApiProvider(this._tokens);
  final TokenStorage _tokens;

  @override
  void onInit() {
    httpClient.baseUrl = AppConfig.apiBaseUrl;
    httpClient.addRequestModifier<Object?>((request) async {
      final access = await _tokens.readAccess();
      if (access != null) request.headers['Authorization'] = 'Bearer $access';
      return request;
    });
    httpClient.addAuthenticator<Object?>((request) async {   // runs on 401
      await Get.find<AuthService>().refreshOrSignOut();
      return request;
    });
    httpClient.maxAuthRetries = 1;
  }
}
```

- Register with `Get.put(AuthService(TokenStorage(secureStorage)), permanent: true)`
  in the initial binding. Controllers depend on `AuthService.user`, not on
  the storage.
- **`GetStorage` is a plain JSON file.** It's fine for settings, never for
  tokens (SEC-001).

## 8. Plain Riverpod

Same as MVN without the use-case layer: a `tokenStorageProvider` and a
`dioProvider` with the interceptor in the data layer, and an
`AsyncNotifier<User?>` session provider that the router listens to. On
logout, `ref.invalidate` the user-scoped providers. Never declare
`final tokenProvider = StateProvider<String?>(…)` (SEC-010).

## 9. Placement checklist for reviews

- [ ] Exactly one class touches secure storage for credentials, and it's in the data layer.
- [ ] Exactly one place adds `Authorization`: an interceptor, request modifier or client wrapper.
- [ ] Refresh is single-flight, uses a client without the auth interceptor, retries once, and signs out on failure.
- [ ] No state, notifier, bloc, view model, controller or provider field holds a token.
- [ ] Logout clears credentials first, then user data, cookies, SDK sessions and user-scoped state.
- [ ] iOS clears the Keychain on the first launch after install.
- [ ] Observers and loggers (`ProviderObserver`, `BlocObserver`, Dio loggers) print nothing auth-related in release.
