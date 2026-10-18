# Placing Firebase in each architecture

The same three pieces exist in every pattern: a **source** that talks to the
SDK, a **repository** that translates, and **logic** that only sees the
app's own types. What changes is the name of each piece and how it is
injected. Detect the pattern first (`../flutter-architecture/scripts/arch_check.py
--json`, or the project instructions file) and follow the project's own
conventions where they are consistent.

## Contents

1. The shared shape (any pattern)
2. MVN (Riverpod codegen + use cases)
3. MVVM (Flutter architecture guide)
4. Bloc / Cubit
5. Clean Architecture (without MVN)
6. Provider
7. GetX
8. Plain Riverpod
9. Where the composition root lives

## 1. The shared shape (any pattern)

```dart
// data/sources/profile_remote_source.dart: the only file that touches the SDK
class ProfileRemoteSource {
  ProfileRemoteSource(this._db, this._auth);

  final FirebaseFirestore _db;
  final FirebaseAuth _auth;

  CollectionReference<ProfileDto> get _profiles => _db.collection('profiles').withConverter<ProfileDto>(
        fromFirestore: (snap, _) => ProfileDto.fromFirestore(snap),
        toFirestore: (dto, _) => dto.toFirestore(),
      );

  Stream<User?> authChanges() => _auth.authStateChanges();

  Stream<ProfileDto?> watch(String uid) => _profiles.doc(uid).snapshots().map((s) => s.data());

  Future<void> save(String uid, ProfileDto dto) => _profiles.doc(uid).set(dto, SetOptions(merge: true));
}

// data/repositories/profile_repository_impl.dart: translates types and errors
class ProfileRepositoryImpl implements ProfileRepository {
  ProfileRepositoryImpl(this._source);

  final ProfileRemoteSource _source;

  @override
  Stream<AppUser> get user => _source.authChanges().map((u) => u == null ? AppUser.anonymous : AppUser(id: u.uid));

  @override
  Stream<Profile?> watch(String uid) => _source.watch(uid).map((dto) => dto?.toEntity()).handleError(
        (Object e, StackTrace s) => throw _map(e),
        test: (e) => e is FirebaseException,
      );

  @override
  Future<Result<void>> save(Profile p) async {
    try {
      await _source.save(p.id, ProfileDto.fromEntity(p));
      return const Result.ok(null);
    } on FirebaseException catch (e) {
      return Result.error(_map(e));
    }
  }

  Failure _map(Object e) => switch (e) {
        FirebaseException(code: 'permission-denied') => const Failure.forbidden(),
        FirebaseException(code: 'unavailable') => const Failure.offline(),
        FirebaseException(code: 'not-found') => const Failure.notFound(),
        _ => const Failure.unknown(),
      };
}
```

Rules that hold everywhere:

- The source receives `FirebaseFirestore`/`FirebaseAuth` through its
  constructor. That is what makes `fake_cloud_firestore` and
  `firebase_auth_mocks` usable in tests, and what lets the composition root
  connect emulators once.
- The repository contract (domain or data, by pattern) mentions no Firebase
  type: no `DocumentSnapshot`, `Timestamp`, `User` from `firebase_auth`, or
  `FirebaseException`. Convert `Timestamp` to `DateTime` in the DTO.
- Error mapping switches on `FirebaseException.code` (and
  `FirebaseAuthException.code`, `FirebaseFunctionsException.code`); the
  failure carries no raw message, so the UI can't leak it (ERR-008).
- Streams leave the repository already mapped. Whoever subscribes owns the
  subscription (section per pattern below).

## 2. MVN (Riverpod codegen + use cases)

```
lib/features/profile/
  data/sources/profile_remote_source.dart
  data/models/profile_dto.dart
  data/repositories/profile_repository_impl.dart
  domain/entities/profile.dart
  domain/repositories/profile_repository.dart
  domain/usecases/watch_profile_usecase.dart
  presentation/notifier/profile_notifier.dart
  presentation/view/profile_view.dart
lib/core/firebase/firebase_providers.dart        // firestoreProvider, firebaseAuthProvider
```

```dart
// core/firebase/firebase_providers.dart
@Riverpod(keepAlive: true)
FirebaseFirestore firestore(Ref ref) => FirebaseFirestore.instance;   // overridden per flavor or in tests

@riverpod
ProfileRemoteSource profileRemoteSource(Ref ref) =>
    ProfileRemoteSource(ref.watch(firestoreProvider), ref.watch(firebaseAuthProvider));

// domain/usecases/watch_profile_usecase.dart
@riverpod
WatchProfileUseCase watchProfileUseCase(Ref ref) => WatchProfileUseCase(ref.watch(profileRepositoryProvider));

// presentation/notifier/profile_notifier.dart: a StreamNotifier, so Riverpod cancels the listener
@riverpod
class ProfileNotifier extends _$ProfileNotifier {
  @override
  Stream<Profile?> build(String uid) => ref.watch(watchProfileUseCaseProvider).call(uid);
}
```

- The notifier never imports `cloud_firestore` (ARCH-012 / ARCH-007).
- A listener the notifier must hold itself: `final sub = stream.listen(...);
  ref.onDispose(sub.cancel);` (FIRE-008).
- Auth for the router: an auth notifier watching the repository's `user`
  stream feeds go_router's `redirect` and `refreshListenable`
  (`flutter-navigation`).

## 3. MVVM (Flutter architecture guide)

```
lib/data/services/firestore_profile_service.dart   // the source
lib/data/repositories/profile_repository.dart      // abstract + _remote impl
lib/ui/profile/view_models/profile_view_model.dart
lib/ui/profile/widgets/profile_screen.dart
```

```dart
class ProfileViewModel extends ChangeNotifier {
  ProfileViewModel({required ProfileRepository repository}) : _repository = repository {
    _sub = _repository.watch(_uid).listen((p) {
      _profile = p;
      notifyListeners();
    });
    save = Command1<void, Profile>(_save);
  }

  final ProfileRepository _repository;
  late final StreamSubscription<Profile?> _sub;
  late final Command1<void, Profile> save;
  Profile? _profile;
  Profile? get profile => _profile;

  Future<Result<void>> _save(Profile p) => _repository.save(p);

  @override
  void dispose() {
    _sub.cancel();
    super.dispose();
  }
}
```

- The view model may call repositories (that is the MVVM guide's rule) but
  never a service or the SDK.
- Errors arrive as `Result.error(Failure)` through the `Command`.

## 4. Bloc / Cubit

bloclibrary.dev puts the Firebase SDK in a data client or repository
package (`packages/authentication_repository`, the `flutter_firebase_login`
example), injected with `RepositoryProvider`.

```dart
class AuthenticationRepository {
  AuthenticationRepository({FirebaseAuth? firebaseAuth}) : _firebaseAuth = firebaseAuth ?? FirebaseAuth.instance;

  final FirebaseAuth _firebaseAuth;

  Stream<AppUser> get user => _firebaseAuth.authStateChanges().map((u) => u == null ? AppUser.empty : u.toAppUser);

  Future<void> logInWithEmail(String email, String password) async {
    try {
      await _firebaseAuth.signInWithEmailAndPassword(email: email, password: password);
    } on FirebaseAuthException catch (e) {
      throw LogInFailure.fromCode(e.code);
    }
  }
}

class AppBloc extends Bloc<AppEvent, AppState> {
  AppBloc({required AuthenticationRepository repository}) : _repository = repository, super(const AppState()) {
    on<AppUserSubscriptionRequested>(
      (event, emit) => emit.onEach(_repository.user, onData: (user) => emit(AppState(user: user))),
    );
  }

  final AuthenticationRepository _repository;
}
```

- `emit.onEach` / `emit.forEach` cancel with the bloc. A manual
  `listen(...)` must be stored and cancelled in `close()` (FIRE-008).
- Blocs don't talk to each other; the UI connects them (ARCH-010).
- Failures are part of the state (`status: failure`, a `LogInFailure`
  message key).

## 5. Clean Architecture (without MVN)

Same layers as MVN, with whatever DI the project uses (get_it, injectable,
constructors): `data/datasources/` for the source, `data/models/` for DTOs,
`domain/` for entities, contracts and use cases. Register the Firebase
instances once in the composition root (`getIt.registerSingleton<FirebaseFirestore>(FirebaseFirestore.instance)`)
after `initializeApp` and any emulator wiring, and inject them into the data
source. The domain never sees `cloud_firestore` (ARCH-003).

## 6. Provider

```dart
MultiProvider(
  providers: [
    Provider(create: (_) => ProfileService(FirebaseFirestore.instance)),
    ProxyProvider<ProfileService, ProfileRepository>(update: (_, s, __) => ProfileRepository(s)),
    ChangeNotifierProxyProvider<ProfileRepository, ProfileModel>(
      create: (c) => ProfileModel(c.read<ProfileRepository>()),
      update: (_, r, m) => m!,
    ),
  ],
  child: const App(),
)
```

A screen-scoped `ChangeNotifier` keeps its subscription and cancels it in
`dispose()`. An app-wide one (created above `MaterialApp`, never disposed)
may listen for the app's lifetime; the Firebase "get to know Flutter"
codelab's `ApplicationState` is that case.

## 7. GetX

```dart
class FirebaseService extends GetxService {
  final db = FirebaseFirestore.instance;
}

class ProfileRepository {
  ProfileRepository(this._service);
  final FirebaseService _service;
  Stream<Profile?> watch(String uid) => ...;
}

class ProfileController extends GetxController {
  ProfileController(this._repository);
  final ProfileRepository _repository;
  final profile = Rxn<Profile>();
  StreamSubscription<Profile?>? _sub;

  @override
  void onInit() {
    super.onInit();
    _sub = _repository.watch(uid).listen(profile.call);   // or profile.bindStream(...)
  }

  @override
  void onClose() {
    _sub?.cancel();
    super.onClose();
  }
}
```

`bindStream` closes with the controller. Register the service in the initial
`Bindings` after `Firebase.initializeApp`.

## 8. Plain Riverpod

```dart
final firestoreProvider = Provider<FirebaseFirestore>((ref) => FirebaseFirestore.instance);

final profileRepositoryProvider = Provider((ref) => ProfileRepository(ref.watch(firestoreProvider)));

final profileProvider = StreamProvider.autoDispose.family<Profile?, String>(
  (ref, uid) => ref.watch(profileRepositoryProvider).watch(uid),
);
```

`StreamProvider` subscribes and cancels for you. Override
`firestoreProvider` in tests with a `FakeFirebaseFirestore()`.

## 9. Where the composition root lives

| Pattern | File | What happens there |
|---|---|---|
| MVN, Riverpod | `lib/main_<flavor>.dart` | `ensureInitialized`, `initializeApp(options: …)`, App Check, emulators under `kDebugMode`, Crashlytics handlers, then `runApp(ProviderScope(overrides: [...]))` |
| MVVM | `lib/main_<flavor>.dart` + `lib/config/dependencies.dart` | same, then the `MultiProvider` list per environment |
| Bloc | `lib/bootstrap.dart` called by `main_<flavor>.dart` | same, inside `runZonedGuarded`, then the repositories are created and passed to `App` |
| Clean (get_it) | `lib/injection.dart` | register Firebase instances after initialisation |
| Provider | `lib/main.dart` | same as MVVM |
| GetX | `lib/main.dart` + initial `Bindings` | `Get.put(FirebaseService(), permanent: true)` after initialisation |

Flavors pick their own `firebase_options_<flavor>.dart` (FlutterFire CLI
`--out` per project) in the entry point; nothing below the composition root
knows which project it talks to (`flutter-release`, REL-006).
