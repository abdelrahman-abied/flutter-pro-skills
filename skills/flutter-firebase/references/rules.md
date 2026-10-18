# FIRE rules: what the checker reports, and why

`scripts/check_firebase.py` is static and read-only. It needs only the Python
standard library: no Flutter SDK, Firebase CLI or `pub get`. Every hit is a
candidate, so read the code or the rules before you call a finding
`confirmed`. Each rule lists the false positives it knows about and how to
suppress a deliberate case.

The checker judges what no other checker in the suite sees: the security
rules that actually protect the data, how Firebase is initialised and wired
to emulators and App Check, background message handlers, listener lifetimes,
unbounded queries, and the client trusting itself with secrets and roles.
Where a concern already has an owner, FIRE cross-references it instead
(section 4).

## Contents

1. How the checker reads the project
2. FIRE-001 … FIRE-012
3. Reading-level findings (FIRE-<slug>)
4. Not checked here (cross-references)
5. Calibration

## 1. How the checker reads the project

- **Firebase or nothing.** The checker looks at `dependencies:` in
  `pubspec.yaml`. With no `firebase_*`, `cloud_firestore`, `cloud_functions`
  or `flutterfire_*` package it reports nothing, says so on the `scanned:`
  line, and reads no other file, so a stray `firestore.rules` or a look-alike
  method name in a non-Firebase app is never reported.
- **Dart.** Every `.dart` file under `lib/` that `arch_check` lists in
  `files[]`, minus barrels, `di` files and generated files (`*.g.dart`,
  `*.freezed.dart`, generated banners). `firebase_options*.dart` is always
  skipped: its values are FlutterFire CLI output, and its API keys are
  identifiers, not secrets (SEC-008 already grades them info).
- **Rules files.** `firebase.json` at the project root and at the repository
  root (the nearest folder with `.git`) names the rules files
  (`firestore.rules`, `storage.rules`, `database.rules.json`, also as lists
  for several databases or buckets). The default names are read at both
  roots too. Files outside the project are reported with a `../` path, and
  `--files` accepts that path. `firestore.indexes.json` is listed in
  `stats.index_files` but not judged.
- **Rules parsing.** `.rules` files: comments and strings are masked, every
  `match` block is followed (paths like `/{document=**}` included), and
  every `allow <ops>: if <condition>;` gets its full path. Zero-argument
  helper functions (`function isSignedIn() { return request.auth != null; }`)
  are inlined up to three levels. `database.rules.json` is read with a small
  JSON reader that allows `//` comments and keeps key positions for line
  numbers. A file it can't parse is skipped, never reported.
- **Guards** (FIRE-004, FIRE-012). A call is guarded when it sits in:
  a `main_dev*.dart`, `main_development*`, `main_local*`, `main_emulator*`,
  `main_debug*`, `main_test*`, `main_e2e*`, `main_mock*` or `main_fake*`
  entry point; the `then` branch of an `if` whose condition reads
  `kDebugMode`, `kProfileMode` or `!kReleaseMode`, a `--dart-define`
  (`bool.fromEnvironment`, `String.fromEnvironment`, `appFlavor`) or a
  flavor/environment value; the `else` of `if (kReleaseMode)`; after an
  early `if (kReleaseMode) return;`; an `assert(...)`; or a `kDebugMode ? … :
  …` ternary in the same argument. A flag defined elsewhere in `lib/` is
  resolved: `const x = true` is a hand-flipped toggle (not a guard),
  `const x = bool.fromEnvironment(…)` is a guard, and a parameter or field
  is trusted as injected configuration. A helper whose every caller is
  guarded is guarded; a helper with no visible caller is not reported by
  FIRE-004.
- **Samples.** A project inside an `example/`, `examples/`, `sample/` or
  `samples/` folder is a sample. FIRE-004, FIRE-011 and FIRE-012 are graded
  **info** there, with the reason in the note: an example app wires the
  emulator or a debug provider on purpose. The rules-file rules and the
  correctness rules keep their severity in samples, because the rules file is
  what `firebase deploy` ships and a dropped listener leaks in any app.
- **Placement notes.** Notes end with the fix for the detected profile
  (`MVN: …`, `MVVM: …`, `Bloc: …`, `Riverpod: …`, `Provider: …`, `GetX: …`):
  where initialisation and App Check go, how a listener is tied to its owner,
  where paging lives, and where a role is read. `--profile` overrides the
  detected pattern.
- **Suppression.** `// fire-ignore: FIRE-00x <reason>` on the reported line
  or the line above, or `// fire-ignore-file: FIRE-00x <reason>` anywhere in
  the file, in Dart and in `.rules` files (and `//` comments in
  `database.rules.json`). In `pubspec.yaml`, `# fire-ignore: FIRE-011
  <reason>` on the line above the reported dependency. The reason is kept in
  `suppressed[]`.

## 2. Rules

### FIRE-001 rules-open-access

**High** for writes · **Medium** for a read-only rule on a recursive
wildcard · rules files

**Detects:** an `allow` whose operations include `write`, `create`, `update`
or `delete` with the condition `true` (also `if x || true`, a helper that
returns `true`, or no condition at all: `allow write;`). A read-only `allow
read: if true` is reported only on a recursive match (`{path=**}`), where it
opens everything below. In `database.rules.json`, any `".write": true` and a
root `".read": true`.

**Why:** the Firebase config (project id, API key) is in every install and
in the web bundle. Rules are the only thing between the internet and the
data: with `if true`, anyone can script writes and deletes without your app.

```
// BAD
match /posts/{postId} { allow write: if true; }

// GOOD
match /posts/{postId} {
  allow create: if request.auth != null
    && request.resource.data.authorId == request.auth.uid
    && request.resource.data.keys().hasOnly(['authorId', 'text', 'createdAt']);
  allow update, delete: if request.auth != null && resource.data.authorId == request.auth.uid;
}
```

**Not reported:** `allow read: if true` on one path (`/public/{doc}`), a
public read on purpose; `allow ...: if false`.
**False positives:** a bucket or collection that is public by product
decision (a CDN of shared images). Scope it to that path, or suppress with
the reason.

### FIRE-002 rules-test-mode-expiry

**High** · rules files

**Detects:** the console's test-mode template, `request.time <
timestamp.date(Y, M, D)` (also inside a helper), and the Realtime Database
version, `"now < <milliseconds>"`. The note gives the date and whether it has
passed.

**Why:** until the date, the path is open to everyone (FIRE-001 in
disguise). After it, every request is denied and the app breaks in
production on a day nobody remembers. Both states are wrong, and the
template is easy to forget because it worked during development.

```
// BAD: test mode
match /{document=**} { allow read, write: if request.time < timestamp.date(2025, 8, 23); }

// GOOD: per path, deny by default (nothing matches /{document=**})
match /users/{userId} { allow read, write: if request.auth != null && request.auth.uid == userId; }
```

**False positives:** none known. A rule that is meant to expire (an event
window) should compare `request.time` against a field stored in the
document, not a date in the rules.

### FIRE-003 rules-auth-only

**Medium** on a recursive wildcard or the root · **Low** on a single path ·
rules files

**Detects:** an `allow` for write operations whose whole condition is
`request.auth != null` (or `request.auth.uid != null`, or zero-argument
helpers that only check that). A read-only rule of that shape is reported
only on a recursive wildcard, as low. In `database.rules.json`,
`"auth != null"` for `.write` (medium) or `.read` (low) at the root or under
wildcard-only paths (`$uid`).

**Why:** signing in proves who someone is, not what they may touch.
Anonymous auth gives anyone an account, so `request.auth != null` on
`/{document=**}` is nearly as open as `true`: any user can overwrite other
users' documents, and in Storage upload anything anywhere.

```
// BAD
match /b/{bucket}/o { match /{allPaths=**} { allow write: if request.auth != null; } }

// GOOD
match /b/{bucket}/o {
  match /avatars/{userId}/{file} {
    allow write: if request.auth != null && request.auth.uid == userId
      && request.resource.size < 2 * 1024 * 1024
      && request.resource.contentType.matches('image/.*');
  }
}
```

**False positives:** a collection every signed-in user may append to (a
shared chat) is a product decision: keep the rule for `create`, validate
`request.resource.data` (author field equals `request.auth.uid`, size, keys),
and the rule no longer matches.

### FIRE-004 emulator-outside-debug

**High** · **Low** behind a hand-set constant that is `false` · **Info** in
samples · all profiles

**Detects:** `useFirestoreEmulator`, `useAuthEmulator`,
`useFunctionsEmulator`, `useStorageEmulator`, `useDatabaseEmulator`,
`useDataConnectEmulator` (and the `connect*Emulator` names) with no guard
(section 1). A guard that is only a hand-set constant `true` stays high.

**Why:** a release build that connects to `localhost` fails for every user
(nothing listens there on a phone), and one that points at a shared dev
host silently writes production users' data into a test backend. A constant
someone has to remember to flip is not a guard.

```dart
// BAD
await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
FirebaseFirestore.instance.useFirestoreEmulator('localhost', 8080);

// GOOD: debug builds only, or a dev flavor's entry point
const useEmulators = bool.fromEnvironment('USE_EMULATORS');
if (kDebugMode && useEmulators) {
  final host = defaultTargetPlatform == TargetPlatform.android ? '10.0.2.2' : 'localhost';
  FirebaseFirestore.instance.useFirestoreEmulator(host, 8080);
  await FirebaseAuth.instance.useAuthEmulator(host, 9099);
}
```

**Profile notes:** connect in the composition root before any provider,
bloc or service reads an instance; data sources receive the configured
instance (a `firestoreProvider` override in Riverpod and MVN, a constructor
argument elsewhere).
**False positives:** an entry point for integration tests whose name the
checker doesn't know (`main_it.dart`). Rename it, guard it, or suppress with
the reason.

### FIRE-005 initialize-app-order

**High** when `runApp` can run first · **Medium** for a missing
`ensureInitialized()` · all profiles

**Detects**, in a function that calls both `Firebase.initializeApp` and
`runApp`:
- `initializeApp(...)` not awaited (no `await`, not inside an awaited
  `Future.wait`, no `.then(...)` that contains `runApp`) and `runApp` after
  it: high.
- `runApp` before `initializeApp`: high.
- `main()` calling `initializeApp` before
  `WidgetsFlutterBinding.ensureInitialized()` (or a binding's
  `ensureInitialized()`), in an app with a mobile or desktop target: medium.
  A function other than `main` that initialises and calls `runApp` is
  reported when neither it nor `main()` calls `ensureInitialized()`.

**Why:** the first frame builds widgets that read `FirebaseAuth.instance`
or `FirebaseFirestore.instance`; if the default app doesn't exist yet they
throw `[core/no-app]`. On Android, iOS and desktop, `initializeApp` uses a
platform channel, which throws "Binding has not yet been initialized" before
`ensureInitialized()`.

```dart
// BAD
void main() {
  Firebase.initializeApp();
  runApp(const App());
}

// GOOD
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(const App());
}
```

**Not reported:** `runApp(FutureBuilder(future: Firebase.initializeApp(),
…))` and `final init = Firebase.initializeApp(); runApp(App(init))`, which
wait in the widget tree; `initializeApp` inside a class method (an app state
object that initialises itself before its first Firebase call); web-only
apps (a `web/` folder and no mobile or desktop folder), where the binding
isn't needed.
**False positives:** a custom binding initialised in another function that
`main()` calls first. Suppress with the reason.

### FIRE-006 background-handler-not-entry-point

**High** · all profiles

**Detects:** `FirebaseMessaging.onBackgroundMessage(x)` where `x` is a
closure, an instance method, or a top-level or static function (resolved
across `lib/`, `Class.method` included) whose declaration has no
`@pragma('vm:entry-point')`. A handler passed in as a parameter (a binding
wrapper) is resolved by its caller and not reported.

**Why:** the handler runs in a separate background isolate that finds it by
name. A closure or an instance method can't be looked up (registration
fails). Since Flutter 3.3, release builds tree-shake a function nothing in
Dart calls, unless it carries `@pragma('vm:entry-point')`, so background
messages work in debug and are silently dropped in release.

```dart
// GOOD
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  // no UI here: update local storage or show a local notification
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  runApp(const App());
}
```

**False positives:** none known.

### FIRE-007 unbounded-query

**Low** · all profiles

**Detects:** `.snapshots()` or `.get()` (with no arguments or `GetOptions`)
at the end of a chain that starts at `collection(...)` or
`collectionGroup(...)` and has no `limit`, `limitToLast`, `count()` or
`aggregate` after the last collection. A chain that starts from a variable
or getter is resolved one hop in the same file (`final postsRef =
db.collection('posts')`). A chain with `.doc(...)` after the collection, or
a reference returned by `.add(...)`, is a single document and not reported.
The note suggests `limit(1)` when only `docs.first` is used.

**Why:** every document a query returns is a billed read, every time: a
listener re-reads changed documents and, after a disconnect longer than 30
minutes, the whole result. An unbounded query grows with the collection, in
cost, memory and time to first frame.

```dart
// BAD
Stream<QuerySnapshot<Post>> watchPosts() => _posts.orderBy('createdAt', descending: true).snapshots();

// GOOD
Future<QuerySnapshot<Post>> page({DocumentSnapshot<Post>? after}) {
  var q = _posts.orderBy('createdAt', descending: true).limit(20);
  if (after != null) q = q.startAfterDocument(after);
  return q.get();
}
```

**Profile notes:** paging lives in the data source; the repository keeps the
cursor; MVN asks for the next page through a use case, Bloc through a
`FetchNextPage` event with a `droppable` transformer, MVVM through a
load-more command.
**False positives:** a small, fixed collection (a dozen categories, a
config collection). Suppress the file with the reason. A query built
across several statements (`var q = …; q = q.limit(n);`) is not followed
past one hop, so the limit is missed; suppress or build the query in one
expression.

### FIRE-008 listener-dropped

**Medium** · all profiles

**Detects:** a statement `<firebase stream>.listen(...);` whose
`StreamSubscription` is discarded, where the stream is a Firestore
`snapshots()`, `authStateChanges()`, `idTokenChanges()`, `userChanges()`,
a Realtime Database `onValue` / `onChild*`, `FirebaseMessaging.onMessage` /
`onMessageOpenedApp`, `onTokenRefresh` or Remote Config `onConfigUpdated`,
in a file that imports a Firebase package, and the enclosing class has a
lifetime: a `State`, a `Bloc`/`Cubit`, a `GetxController`, a Riverpod codegen
notifier that isn't `keepAlive: true`, or any class that declares
`dispose()`, `close()` or `onClose()`.

**Why:** the listener outlives its owner. Firestore keeps billing reads for
it, and the callback keeps running after the owner is gone: `setState` on a
disposed `State`, `emit` after `close()`, `state =` on a disposed notifier,
`Navigator` on a dead `context`. Every visit to the screen adds another one.

```dart
// BAD (an auto-dispose notifier)
@override
int build() {
  FirebaseFirestore.instance.collection('posts').limit(20).snapshots().listen((s) => state = s.size);
  return 0;
}

// GOOD: Riverpod owns the stream
@riverpod
Stream<int> postCount(Ref ref) => ref.watch(postsRepositoryProvider).watchCount();

// GOOD: Bloc owns the stream
on<PostsSubscribed>((event, emit) => emit.forEach(_repository.watchPosts(), onData: PostsState.loaded));
```

**Profile notes:** MVN/Riverpod return the stream from a `StreamNotifier` /
`StreamProvider`, or `ref.onDispose(sub.cancel)`; Bloc uses `emit.forEach`
or cancels in `close()`; MVVM, Provider and plain `State` cancel in
`dispose()`; GetX in `onClose()`.
**Not reported:** a subscription stored in a field or a list (the
`undisposed-resource` candidate and UI-lifecycle check whether it is
cancelled); listeners in `main()`, top-level functions or app-lifetime
holders (a root `ChangeNotifier` without `dispose()`, a keep-alive provider);
streams handed to `StreamBuilder`.
**False positives:** a `State` that lives as long as the app (the root
page). It's still better to cancel; suppress with the reason if you
disagree.

### FIRE-009 remote-config-secret-or-gate

**Medium** · all profiles

**Detects:** `getString`/`getBool`/`getInt`/`getDouble`/`getValue` with a
literal key on a Remote Config receiver (`FirebaseRemoteConfig.instance`,
or a variable named like `remoteConfig`, `config`, `rc`) in a file that
imports `firebase_remote_config`, and literal keys in `setDefaults({...})`,
when the key looks like a secret (`api_key`, `secret`, `token`, `password`,
`private_key`, `credential`, `access_key`) or a security decision (`admin`,
`role`, `permission`, `privilege`, `superuser`, `moderator`, `staff`,
`allowlist`, `bypass`, `can_access`, `is_authorized`).

**Why:** Remote Config is fetched by every client and stored on the device:
anyone can read every value, and a proxy or a patched app can change what
the client sees. A secret there is public; a privilege there can be granted
by the user.

```dart
// BAD
final stripeKey = remoteConfig.getString('stripe_secret_key');
if (remoteConfig.getBool('is_admin')) showAdminPanel();

// GOOD: the server holds the secret; the role comes from ID token claims and rules enforce it
final claims = (await user.getIdTokenResult()).claims;
final isAdmin = claims?['role'] == 'admin';   // display only
```

**False positives:** a feature flag whose name contains one of the words
(`show_admin_banner`) and gates only UI. Rename it, or suppress with the
reason.

### FIRE-010 client-writes-privilege-field

**Medium** · all profiles

**Detects:** `set`, `update`, `add`, `setData`, `updateData` on a Firestore
or Realtime Database reference (a chain with `.doc(`, `.collection(`,
`.ref(`, `.child(`, a variable named like `*Ref`/`*Doc`/`*Collection`, or a
`transaction`/`batch` write) whose map literal has a top-level key `role`,
`roles`, `userRole`, `isAdmin`, `admin`, `permissions`, `privileges`,
`claims`, `customClaims`, `isModerator`, `isStaff`, `isSuperuser` or
`accessLevel` (snake_case too), in a file that imports `cloud_firestore` or
`firebase_database`.

**Why:** whatever the client can send, any user can send with their own
value. A role written by the client is a role any user can grant
themselves, unless the rules reject it, and rules that read roles from a
user-writable document inherit the hole.

```dart
// BAD
await _db.collection('users').doc(uid).set({'name': name, 'role': 'member'});

// GOOD: a Cloud Function (Admin SDK) sets custom claims; rules forbid the field
await _db.collection('users').doc(uid).set({'name': name});
```

```
allow update: if request.auth.uid == userId
  && !request.resource.data.diff(resource.data).affectedKeys().hasAny(['role', 'isAdmin']);
```

**False positives:** an admin tool whose writes the rules restrict to
`request.auth.token.role == 'admin'`. Suppress with the reason (and keep
the rules test that proves it).

### FIRE-011 app-check-missing

**Low**, once per project · **Info** in samples

**Detects:** an app (it has `lib/main*.dart`) whose `dependencies:` include
`cloud_firestore`, `cloud_functions`, `firebase_storage`,
`firebase_database`, `firebase_data_connect`, `firebase_ai` or
`firebase_vertexai`, and no code in `lib/` calls `FirebaseAppCheck…activate`
(or `appCheck.activate`). Reported at the first such dependency in
`pubspec.yaml`. Packages without an entry point aren't reported: App Check
belongs to the app.

**Why:** the project id and API key are public, so without App Check anyone
can script calls against Firestore, Storage or Functions, and the rules are
the only defence (and the only thing limiting your bill). App Check makes
the backend accept only requests from your genuine app.

```dart
await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
await FirebaseAppCheck.instance.activate(
  providerAndroid: kDebugMode ? const AndroidDebugProvider() : const AndroidPlayIntegrityProvider(),
  providerApple: kDebugMode ? const AppleDebugProvider() : const AppleAppAttestWithDeviceCheckFallbackProvider(),
  providerWeb: ReCaptchaEnterpriseProvider('your-site-key'),
);
```

**False positives:** App Check activated in a path package or plugin the
checker doesn't scan. Suppress in `pubspec.yaml` with the reason.

### FIRE-012 app-check-debug-provider

**Medium** · **Low** behind a hand-set `false` constant · **Info** in samples

**Detects:** `AndroidProvider.debug`, `AppleProvider.debug`,
`AndroidDebugProvider(`, `AppleDebugProvider(` or `WebDebugProvider(` with no
debug guard (section 1). A `kDebugMode ? … : …` ternary guards only the
argument it sits in, so `providerWeb: kDebugMode ? … : …` doesn't cover
`providerAndroid: const AndroidDebugProvider()` next to it. Unlike FIRE-004,
a debug provider in a function with no visible caller is still reported.
`WindowsDebugProvider` is ignored: it is the only provider on Windows.

**Why:** a release build with the debug provider sends debug tokens. With
enforcement on, real users are rejected; with a debug token registered in
the console, anyone holding that token passes App Check.

**False positives:** an internal QA build type the checker can't see.
Suppress with the reason.

## 3. Reading-level findings (FIRE-<slug>)

These need judgement the checker can't make. Report them in the suite's
finding format with `confidence: likely` unless you traced the code.

| ID | Severity | Look for | Fix |
|---|---|---|---|
| FIRE-rules-untested | Medium | rules files with no `@firebase/rules-unit-testing` suite or emulator job in CI | add `assertFails`/`assertSucceeds` tests per path and role, run with `firebase emulators:exec` |
| FIRE-rules-no-validation | Medium | write rules that check the caller but never `request.resource.data` | check types, sizes and `keys().hasOnly([...])`; reject changes to server-owned fields |
| FIRE-role-trusted-from-client | High | the app or the rules read a role from a document the user can write, or from Remote Config | custom claims set by the Admin SDK; rules check `request.auth.token` |
| FIRE-current-user-force-unwrap | Medium | `currentUser!` outside a path that proves sign-in | take the user from the auth stream or the signed-in state |
| FIRE-auth-state-polled | Low | `currentUser` read once at start-up or in `build` | listen to `authStateChanges()` through the repository |
| FIRE-snapshot-leaks | Medium | `DocumentSnapshot`, `QuerySnapshot`, `DocumentReference`, `Timestamp` in entities, state or widgets | map in the repository (`withConverter` or DTO → entity) |
| FIRE-transaction-side-effects | Medium | navigation, analytics, `setState` or non-Firestore writes inside `runTransaction` | return a value from the transaction and act after it |
| FIRE-batch-over-limit | Low | a `WriteBatch` filled in a loop without splitting at 500 | chunk into batches of ≤ 500 |
| FIRE-index-not-committed | Low | `where` + `orderBy` on different fields, or several range filters, with no `firestore.indexes.json` | `firebase firestore:indexes > firestore.indexes.json` and deploy it with the rules |
| FIRE-token-refresh-ignored | Low | `getToken()` sent once, no `onTokenRefresh` | send the token on refresh and on sign-in; delete it on sign-out |
| FIRE-pii-in-push-payload | Medium | emails, names, tokens or message bodies in FCM `data` from your backend | send ids and fetch details after opening, behind auth |
| FIRE-remote-config-no-defaults | Low | `get*` without `setDefaults` | defaults in code, then `fetchAndActivate()` |
| FIRE-callable-trusts-client | High | a callable that trusts `data.uid` or a client role | use `request.auth.uid` and claims on the server; validate inputs |
| FIRE-app-check-not-enforced | Low | App Check activated but not enforced in the console | enforce per product after watching the metrics |
| FIRE-tests-hit-real-project | Medium | tests that initialise a real Firebase project | fakes for unit tests, the emulator suite for integration tests |

## 4. Not checked here (cross-references)

| Concern | Owner |
|---|---|
| `FirebaseFirestore.instance` in widgets | ARCH-101 (`flutter-architecture`) |
| Firebase package imports in views, widgets or logic | ARCH-005 / ARCH-007 / ARCH-012 |
| Repositories returning `Map<String, dynamic>` or DTOs | ARCH-107 |
| `FirebaseException` / `FirebaseAuthException` escaping a repository, in the domain, or shown raw | ERR-004 / ERR-006 / ERR-008 (`flutter-error-handling`) |
| Swallowed catches around Firebase calls | ERR-001 |
| Crashlytics and the global error handlers | ERR-012 |
| PII or tokens in logs, Analytics events, crash keys | SEC-004 (`flutter-secure-defaults`); form values: FORM-004 |
| Tokens in plain storage | SEC-001 |
| Hard-coded secrets | SEC-008 (a `firebase_options.dart` `apiKey` is info there, by design) |
| Notification permission at start-up, permanent denial | PLAT-011 / PLAT-012 (`flutter-platform-integration`) |
| One Firebase project per flavor, signing, build config | REL (`flutter-release`) |
| Cache policy beyond Firestore's own, offline sync | PERSIST (`flutter-persistence`) |
| Eager lists built from query results | PERF-001 (`flutter-performance`) |
| Assigned subscriptions never cancelled | the `undisposed-resource` candidate / UI-lifecycle; FIRE-008 owns only a discarded Firebase stream subscription and beats them on the same line |
| Non-Firebase HTTP clients | NET (`flutter-networking`) |

## 5. Calibration

Run on the suite's shared calibration pool (suite contracts §24 and §36).
Each project with its own `pubspec.yaml` was run separately (215 projects).
The codelabs checkout held the `firebase-auth-flutterfire-ui` and
`firebase-get-to-know-flutter` steps.
Projects without a Firebase dependency report nothing by design; the 47
with one were read finding by finding (every high and medium, and the lows).

| App | Commit | Projects (with Firebase) | Hits (per rule) | TP / FP |
|---|---|---|---|---|
| flutter/samples `compass_app` app + server (canonical) | flutter/samples@5541c59 | 2 (0) | none | 0 / 0 |
| flutter/samples, the other projects | flutter/samples@5541c59 | 37 (0) | none | 0 / 0 |
| felangel/bloc `examples/*` + packages (canonical) | felangel/bloc@b9be1e2 | 48 (2: `flutter_firebase_login` and its `authentication_repository`) | none | 0 / 0 |
| rrousselGit/riverpod `examples/*` + packages (canonical) | rrousselGit/riverpod@87aad84 | 31 (0) | none | 0 / 0 |
| firebase/flutterfire `packages/*/*/example` (canonical, samples) | firebase/flutterfire@569c39e | 16 (16) | FIRE-008 ×4 (medium), FIRE-007 ×2 (low), FIRE-004 ×7, FIRE-011 ×5, FIRE-012 ×5 (info) | 23 / 0 (1 low FP and 1 false negative before) |
| flutter/codelabs `firebase-auth-flutterfire-ui` steps (canonical) | flutter/codelabs@271d8e3 | 13 (12) | FIRE-002 ×12 (high) | 12 / 0 |
| flutter/codelabs `firebase-get-to-know-flutter` steps (canonical) | flutter/codelabs@271d8e3 | 6 (5) | FIRE-007 ×3, FIRE-011 ×5 (low) | 8 / 0 |
| flutter/news_toolkit `flutter_news_example` + packages | flutter/news_toolkit@6655bbc | 31 (5) | none | 0 / 0 |
| VGVentures/io_flip + packages | VGVentures/io_flip@964e511 | 26 (6) | FIRE-001 ×6, FIRE-003 ×6 (medium; the same repo-root `storage.rules` seen from 6 projects), FIRE-007 ×3 (low) | 15 / 0 (crash and 2 false negatives before) |
| lichess-org/mobile | lichess-org/mobile@99e1fb7 | 1 (1) | none | 0 / 0 |
| immich-app/immich `mobile`, hiddify/hiddify-app, gskinnerTeam/flutter-wonderous-app | immich-app/immich@188d64e, hiddify/hiddify-app@f26aadb, gskinnerTeam/flutter-wonderous-app@747b945 | 4 (0) | none (no Firebase dependency) | 0 / 0 |

**The canonical apps have no high or medium false positives.** Their highs
and mediums are true positives on reading:

- **FIRE-002 ×12 (codelab steps).** Every step of the FirebaseUI Auth
  codelab ships the console's test-mode rules, `match /{document=**} { allow
  read, write: if request.time < timestamp.date(2022, 8, 23); }`. Deployed
  as is, the database was open to anyone until that date and has denied
  every request since. That is exactly the template FIRE-002 exists for.
- **FIRE-008 ×4 (FlutterFire `firebase_auth` and `firebase_messaging`
  examples).** `State.initState` calls `auth.userChanges().listen(...)` on
  the profile page, and `FirebaseMessaging.onMessage.listen(...)` /
  `onMessageOpenedApp.listen(...)` on the home page and in a message-list
  widget, and none of them is cancelled in `dispose()`. Flutter's
  `State.dispose` contract says to cancel stream subscriptions; the profile
  page adds a listener on every visit, the message list calls `setState`
  without a `mounted` check, and the home page's callback navigates with its
  `context`.

The lows are true positives: unbounded `orderBy(...).snapshots()` on the
codelab guestbook and the FlutterFire movies list, a `where(...)` query that
counts every attendee document, io_flip's config lookups that fetch every
matching document to use `docs.first` (the note suggests `limit(1)`), and
the get-to-know codelab using Firestore without App Check. The infos are the
FlutterFire examples doing what their README says: emulators behind
hand-set `shouldUseEmulator = true` flags or unconditionally (`cloud_functions`),
and the App Check example activating the debug providers. They are graded
info because the projects sit in `example/` folders, as `flutter-release`
grades store rules in samples; the same code in an app is high or medium.

Non-canonical true positives: io_flip's `storage.rules` lets any signed-in
user (the game signs everyone in anonymously) create files anywhere in the
bucket and lets anyone list and read every file (`match /{allPaths=**} {
allow create: if request.auth != null; allow read: if true; }`). Its
`firestore.rules` is correctly silent: every write checks ownership through
`get()` lookups. io_flip's `main_production.dart` calls `initializeApp`
before `ensureInitialized()`, which is fine on the web, the only target.
news_toolkit, the bloc login example and lichess route Firebase through
repositories and clients, await initialisation after `ensureInitialized()`,
annotate their background handler and store their subscriptions, and get no
findings. lichess passes its handler through a binding wrapper, which is
correctly not reported.

**SEC-008 on `firebase_options.dart`.** `flutter-secure-defaults` reports
the FlutterFire `apiKey` values (lichess, io_flip) as **info** with the note
"a public identifier by design, not a secret", which matches this skill's
guidance. No false positive to fix there.

**Causes fixed, each with a `calib_<app>` regression fixture and a test that
the related true positive still fires:**

| Fixture | Cause | Fix |
|---|---|---|
| `calib_flutterfire` | `final docRef = await db.collection('x').add({...}); await docRef.get();` was read as an unbounded collection read (FIRE-007 low) | a reference returned by `.add(...)` is a document, like `.doc(...)`; `get()` on a top-level collection reference still fires |
| `calib_flutterfire` | `providerWeb: kDebugMode ? WebDebugProvider() : …` hid the unguarded `providerAndroid: const AndroidDebugProvider()` next to it (FIRE-012 false negative) | a ternary guard covers only the argument it sits in |
| `calib_io_flip` | `match /{allPaths=**}` wasn't parsed (braces inside the path), so the recursive storage rules were graded as single-path (FIRE-001 missed, FIRE-003 low instead of medium) | match paths with `{var}` and `{var=**}` segments are parsed |
| `calib_io_flip` | an `||` inside parentheses in a rules condition sent the condition splitter into endless recursion (crash on `firestore.rules`) | split only on top-level operators, recurse only when the split found several terms |
| `calib_io_flip` | `main_production.dart` initialises before `ensureInitialized()` in a web-only app (would be FIRE-005 medium) | web-only apps are exempt; the same file with `android/` still fires |
| `calib_codelab` | the codelab's app-wide `ApplicationState extends ChangeNotifier` listens in `init()` and is never disposed (would be FIRE-008) | only holders with a lifetime count: `State`, blocs, controllers, auto-dispose notifiers, classes that declare `dispose()`/`close()`/`onClose()`; a screen `ChangeNotifier` with `dispose()` still fires |
| `calib_lichess` | a background handler passed through a wrapper method's parameter (would be FIRE-006) | parameters are left to the caller; a static handler without the pragma still fires |

**Known limits.** Rules: functions with arguments are not inlined, `get()`
and `exists()` lookups are treated as real checks, and Storage's
`request.resource` validation isn't judged (FIRE-rules-no-validation is
reading-level). FIRE-004 resolves flags across `lib/` but not values read
from a config file at runtime. FIRE-005 looks only at functions that call
`runApp`. FIRE-007 follows a query one hop and misses limits added in a
later statement. FIRE-008 sees only the discarded subscription, not one
stored and never cancelled (the `undisposed-resource` candidate's job).
FIRE-010 sees map literals, not `toJson()` output.
