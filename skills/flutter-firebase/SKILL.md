---
name: flutter-firebase
description: Write and review Firebase in Flutter, secure by default and placed by the app's architecture (MVN, MVVM, Bloc, Clean, Provider, GetX, Riverpod). Covers awaited Firebase.initializeApp before runApp, FirebaseAuth behind a repository (authStateChanges as a domain stream), Firestore sources (withConverter, limit and pagination, listeners cancelled with the owner, transactions), security rules (deny by default, no test mode, signed-in is not authorised, emulator tests), App Check, FCM background handlers, Remote Config, debug-only emulators. Ships a FIRE checker for Dart and rules. Use it whenever code imports a Firebase package or edits firestore.rules or firebase.json. For tokens and logs load flutter-secure-defaults, crash reports flutter-error-handling, other APIs flutter-networking, caches flutter-persistence, permissions flutter-platform-integration, flavors flutter-release.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.0"
  suite: flutter-pro-skills
---

# Flutter + Firebase

Firebase moves the backend into the client: the app talks to Firestore,
Storage and Functions directly, with a config that ships in every install.
That makes two kinds of mistake cheap to write and expensive to ship. The
first kind is security: rules left in test mode, `allow write: if
request.auth != null` on everything, roles the client writes for itself, a
secret in Remote Config, an emulator wired into the release build. The second
is architecture and cost: `FirebaseFirestore.instance` in widgets, snapshots
leaking to the UI, a listener that outlives its screen and keeps billing
reads, a collection fetched without a limit. This skill writes Firebase code
that is safe without a later hardening pass, and puts each piece where the
project's architecture expects it.

The core split holds in every pattern:

- **The Firebase SDK is a data source.** A class in `data/sources/` (or a
  data-client package) wraps `FirebaseAuth`, `FirebaseFirestore`,
  `FirebaseStorage`, `FirebaseFunctions` and `FirebaseMessaging`, and gets the
  instance through its constructor.
- **The repository translates.** It maps `FirebaseException` and
  `FirebaseAuthException` (switch on `code`) to the app's typed failures, maps
  snapshots to entities (`withConverter` or DTOs), and exposes
  `authStateChanges()` as a stream of the app's own `User`.
- **Logic never imports a Firebase package.** MVN notifiers go through use
  cases, MVVM view models and blocs through repositories, GetX controllers
  through services. **Views never call `.instance`.**
- **The server decides.** Security rules (and Cloud Functions) are the only
  enforcement. The client config, Remote Config and anything the client
  writes are public and changeable. The `firebase_options.dart` API keys are
  identifiers, not secrets: protect the data with rules and App Check, not by
  hiding the key.

## Workflow

### 1. Detect the architecture and what the app uses

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern and conventions; a declared convention wins. Then run the
checker. It is read-only, uses only the Python standard library, and needs
neither `pub get` nor the Firebase CLI:

```bash
python3 -I <skill-dir>/scripts/check_firebase.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_firebase.py <project-root> --json              # schema flutter-pro-skills/firebase@1
python3 -I <skill-dir>/scripts/check_firebase.py <project-root> --files changed.txt # diff review
python3 -I <skill-dir>/scripts/check_firebase.py <project-root> --profile bloc      # declared pattern wins
```

The CLI is `check_firebase.py <project-root> [--json] [--files
<list-file-or-comma-list>] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
[--max n]`. It exits `0` whenever a report is produced and `2` on a usage
error. It reads Dart under `lib/` (skipping generated files and
`firebase_options*.dart`), `pubspec.yaml`, `firebase.json`, and the rules
files it names or that sit at the project or repository root
(`firestore.rules`, `storage.rules`, `database.rules.json`; files outside the
project are reported with `../` paths). A project with no Firebase
dependency gets no findings. Roles and the profile come from the
`flutter-architecture` checker (`../flutter-architecture/scripts/arch_check.py
--json`, or `$FPS_ARCH_JSON` when a review already ran it); without that
sibling it falls back to path-based detection and says so.

```text
== FIREBASE
  profile: mvn + clean (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 84 files (3 generated skipped); packages: cloud_firestore, firebase_auth, ...; rules: firestore.rules; ...
  [FIRE-001] rules-open-access (high) x1 — A security rule grants access to everyone ...
      firestore.rules:8  allow write: if true;   [anyone can write /databases/{database}/documents/posts/{postId} ...]
```

### 2. Place each piece by the pattern

| Piece | MVN | MVVM | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| `initializeApp`, App Check, emulators | `main_<flavor>.dart` before `ProviderScope` | `main_<flavor>.dart` before the providers | `bootstrap()` / `main_<flavor>.dart` | composition root | `main()` | `main()` / initial `Bindings` | `main()`, or a `firestoreProvider` override |
| SDK calls | `data/sources/*_remote_source.dart` | `data/services/` | data-client package or `data/` provider | `data/datasources/` | `services/` | `GetxService` / provider class | source provider |
| exception → failure, snapshot → entity | repository impl | repository | repository | repository impl | repository / service | repository | repository provider |
| auth state | `Stream<User>` from the repository, read by a use case and a `StreamNotifier` | repository stream, view model listens | `AuthenticationRepository.user` + `AppBloc` (`emit.forEach`) | as MVN | `ChangeNotifier` listening to the repository | `Rx<User>` bound in a `GetxService` | `StreamProvider<User>` |
| listener lifetime | `build()` returns the stream, or `ref.onDispose(sub.cancel)` | cancel in `dispose()` | `emit.forEach`, or cancel in `close()` | as MVN | cancel in `dispose()` | cancel in `onClose()` | `StreamProvider` / `ref.onDispose` |
| route guard on auth | `flutter-navigation` (`redirect` + `refreshListenable` from the auth notifier) | same | `BlocListener` / redirect | same | same | `GetMiddleware` | same |

Read `references/placement-by-architecture.md` before writing a source,
repository or auth flow, `references/firestore-data.md` for converters,
queries, pagination, listeners, transactions, offline and cost,
`references/security-rules-and-app-check.md` before touching any rules file
or App Check, `references/setup-messaging-config.md` for initialisation,
flavors, emulators, FCM, Crashlytics, Analytics, Remote Config and callables,
and `references/testing-firebase.md` for fakes, the emulator suite and rules
tests.

For step-by-step setup (the FlutterFire CLI, platform files, console
settings), defer to firebase.google.com/docs/flutter and the FlutterFire
docs, and, if your agent has them installed, the official
`flutter/agent-plugins` or `dart-lang/skills` recipes. This skill adds the
architecture placement, the secure defaults and the review checks.

### 3. Write with the checklist below, then run the checker

Read the code (or the rules) behind every hit before calling it
`confirmed`. `references/rules.md` lists each rule's detection and its known
false positives. Suppress a deliberate case with a reason, in Dart or in a
`.rules` file: `// fire-ignore: FIRE-001 public, read-only announcements`
(on the reported line or the line above) or `// fire-ignore-file: FIRE-007
<reason>`. In `pubspec.yaml` use `# fire-ignore: FIRE-011 <reason>` above the
dependency.

## WRITE checklist

**Setup**
1. DO call `WidgetsFlutterBinding.ensureInitialized()`, then
   `await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform)`,
   then `runApp`, once, in the composition root (FIRE-005). With flavors,
   generate one options file per Firebase project and pick it in
   `main_<flavor>.dart` (`flutter-release`).
2. DO connect emulators (`useFirestoreEmulator`, `useAuthEmulator`,
   `useFunctionsEmulator`, `useStorageEmulator`) only under `kDebugMode`, in
   a dev flavor's entry point, or behind `bool.fromEnvironment`, and before
   the first call to that product (FIRE-004). A hand-flipped `const
   useEmulator = true` ships one day.
3. DO activate App Check right after `initializeApp` for any app that uses
   Firestore, Functions, Storage, the Realtime Database or AI Logic (FIRE-011):
   Play Integrity on Android, App Attest (with DeviceCheck fallback) on Apple,
   reCAPTCHA on the web, and the debug provider only under `kDebugMode`
   (FIRE-012). Enforce it in the console once metrics look right.

**Auth**
4. DO expose auth as the app's own stream: the repository maps
   `authStateChanges()` (or `userChanges()` when profile fields matter) to a
   `User` entity with an `unauthenticated` value. Read it at start-up instead
   of `currentUser`, which is `null` until the SDK restores the session.
5. AVOID `currentUser!` (FIRE-current-user-force-unwrap): it throws after
   sign-out or before restore. Take the user from the auth stream or the
   state that proves sign-in.
6. DO map `FirebaseAuthException.code` (`invalid-credential`,
   `user-disabled`, `too-many-requests`, `network-request-failed`, …) to typed
   failures in the repository, and show user-safe messages
   (`flutter-error-handling`, ERR-004/ERR-008). On sign-out, also clear local
   caches and tokens (`flutter-secure-defaults`).

**Firestore**
7. DO type documents at the source boundary: `withConverter<T>` or a DTO
   with a validating `fromFirestore`. Snapshots, `DocumentReference`s and
   `Map<String, dynamic>` stop at the repository.
8. DO bound every list query: `limit(n)` plus `startAfterDocument(last)` for
   the next page, or `FirestoreListView` / `FirestoreQueryBuilder`
   (FIRE-007). Use `count()` for counts and `limit(1)` for "the first match".
9. DO tie every listener to its owner's lifetime (FIRE-008): return the
   stream to a `StreamProvider` / `emit.forEach`, or keep the
   `StreamSubscription` and cancel it in `dispose()` / `close()` /
   `onClose()` / `ref.onDispose`. A listener bills reads for as long as it
   lives.
10. DO use a transaction for read-modify-write and a `WriteBatch` for
    multi-document writes (at most 500 operations). Keep transaction bodies
    free of side effects: they retry.
11. CONSIDER offline behaviour: Firestore caches by default on mobile, so a
    write resolves locally and a read can come from cache
    (`metadata.isFromCache`). Decide what the UI shows for pending writes;
    cache policy beyond Firestore's own belongs to `flutter-persistence`.
12. DO commit `firestore.indexes.json` with the composite indexes your
    queries need, so they deploy with the rules instead of failing in
    production with `failed-precondition`.

**Security rules**
13. DO deny by default and open each path for its owner:
    `allow read, update: if request.auth != null && request.auth.uid == userId`.
    Never ship `if true` writes or the test-mode `request.time < timestamp.date(...)`
    template (FIRE-001, FIRE-002).
14. DON'T treat signed-in as authorised (FIRE-003). Anonymous auth gives
    anyone an account. Check ownership and validate `request.resource.data`
    (types, sizes, allowed keys with `keys().hasOnly([...])`).
15. DON'T let the client write its own role (FIRE-010). Set roles with
    custom claims from the Admin SDK (a Cloud Function), check
    `request.auth.token.role` in rules, and reject client writes that touch
    privilege fields.
16. DO test the rules with the emulator and `@firebase/rules-unit-testing`
    (`assertFails` / `assertSucceeds`) in CI (FIRE-rules-untested).

**Messaging, config and functions**
17. DO register `FirebaseMessaging.onBackgroundMessage` with a top-level or
    static function annotated `@pragma('vm:entry-point')` that calls
    `Firebase.initializeApp` itself (FIRE-006).
18. DO request notification permission when the user turns notifications on,
    not at launch (PLAT-011, `flutter-platform-integration`), handle
    `onTokenRefresh`, send the token to your backend, and keep PII and tokens
    out of message payloads (FIRE-pii-in-push-payload).
19. DON'T put secrets or security decisions in Remote Config (FIRE-009).
    It downloads to every client. Set in-app defaults with `setDefaults`, and
    use it for tuning and gradual rollouts only.
20. DO validate callable inputs and check `request.auth` on the server;
    on the client, map `FirebaseFunctionsException` in the repository.
21. Crashlytics and Analytics: the global handlers are
    `flutter-error-handling`'s (ERR-012), and no PII, tokens or field values
    go into events, keys or logs (SEC-004, FORM-004).

**Tests**
22. DO test repositories against `fake_cloud_firestore` and
    `firebase_auth_mocks`, and logic against fakes of the repository
    contract. Use the emulator suite for integration tests; never a real
    project (`flutter-testing`).

## REVIEW checklist

Script rules (`FIRE-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| FIRE-001 | rules-open-access | High (Medium for a read-only rule on a recursive wildcard) | `allow ...: if true`, an `allow` with no condition, Realtime Database `".read"` at the root or any `".write"` set to `true` |
| FIRE-002 | rules-test-mode-expiry | High | `request.time < timestamp.date(...)` or Realtime Database `now < <ms>`; the note says whether it already expired |
| FIRE-003 | rules-auth-only | Medium on `{x=**}` or the root, Low on one path | writes allowed by `request.auth != null` alone (or a helper that only checks that) |
| FIRE-004 | emulator-outside-debug | High (Low behind a constant that is false; Info in samples) | `use*Emulator` not under `kDebugMode`, `assert`, a flavor/env check or a dev entry point |
| FIRE-005 | initialize-app-order | High (Medium for the binding) | `initializeApp` not awaited before `runApp`, or after it; `main()` without `ensureInitialized()` first (not on web-only apps) |
| FIRE-006 | background-handler-not-entry-point | High | `onBackgroundMessage` given a closure, an instance method, or a function without `@pragma('vm:entry-point')` |
| FIRE-007 | unbounded-query | Low | `collection(...)…snapshots()` / `.get()` with no `limit` (references resolved one hop) |
| FIRE-008 | listener-dropped | Medium | a Firebase stream `.listen(...)` whose subscription is discarded inside a State, bloc, controller, auto-dispose notifier or class with `dispose()` |
| FIRE-009 | remote-config-secret-or-gate | Medium | Remote Config keys named like secrets (`api_key`, `secret`, `token`) or privileges (`is_admin`, `role`) |
| FIRE-010 | client-writes-privilege-field | Medium | `set`/`update`/`add` (or a transaction/batch write) with a `role`, `isAdmin`, `permissions` or `claims` key |
| FIRE-011 | app-check-missing | Low, once (Info in samples) | Firestore, Functions, Storage, RTDB, AI Logic or Data Connect used with no `FirebaseAppCheck…activate` |
| FIRE-012 | app-check-debug-provider | Medium (Info in samples) | `AndroidProvider.debug`, `AndroidDebugProvider()`, `AppleDebugProvider()` outside `kDebugMode` |

Reading-level findings (`FIRE-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| FIRE-rules-untested | Medium | rules files with no emulator tests in the repo or CI |
| FIRE-rules-no-validation | Medium | write rules that check who but never what (`request.resource.data` types, sizes, `keys().hasOnly`) |
| FIRE-role-trusted-from-client | High | the app reads a role from a document the user can write, or from Remote Config, and the server trusts it too |
| FIRE-current-user-force-unwrap | Medium | `FirebaseAuth.instance.currentUser!` or `auth.currentUser!.uid` outside a path that proves sign-in |
| FIRE-auth-state-polled | Low | `currentUser` read once at start-up (or in `build`) instead of `authStateChanges()` |
| FIRE-snapshot-leaks | Medium | `DocumentSnapshot`, `QuerySnapshot`, `DocumentReference` or `Timestamp` in entities, state or widgets |
| FIRE-transaction-side-effects | Medium | navigation, analytics, `setState` or non-Firestore writes inside `runTransaction` |
| FIRE-batch-over-limit | Low | a `WriteBatch` filled in a loop with no 500-operation split |
| FIRE-index-not-committed | Low | composite queries (`where` + `orderBy` on different fields) with no `firestore.indexes.json` |
| FIRE-token-refresh-ignored | Low | `getToken()` sent once, no `onTokenRefresh` handler |
| FIRE-pii-in-push-payload | Medium | emails, names, tokens or message bodies in FCM `data` built by your backend |
| FIRE-remote-config-no-defaults | Low | `getX` with no `setDefaults`, so the first launch offline behaves differently |
| FIRE-callable-trusts-client | High | a callable or HTTPS function that trusts `data.uid` or a client role instead of `request.auth` |
| FIRE-app-check-not-enforced | Low | App Check activated but the console still allows unverified requests (ask, or check deploy scripts) |
| FIRE-tests-hit-real-project | Medium | tests that call `Firebase.initializeApp` against a real project instead of fakes or the emulator |

**Don't report here (cross-reference instead):**
- `FirebaseFirestore.instance` in widgets: ARCH-101. Firebase imports in
  views, widgets or logic: ARCH-005 / ARCH-007 / ARCH-012
  (`flutter-architecture`).
- `FirebaseException` / `FirebaseAuthException` escaping a repository or
  shown raw: ERR-004 / ERR-006 / ERR-008. Swallowed catches: ERR-001. Global
  handlers (Crashlytics wiring): ERR-012 (`flutter-error-handling`).
- PII or tokens in logs, Analytics events or crash keys: SEC-004. Tokens in
  plain storage: SEC-001. Hard-coded secrets: SEC-008, which grades a
  `firebase_options.dart` `apiKey` as info on purpose
  (`flutter-secure-defaults`).
- Permission prompts at launch and permanent denial: PLAT-011 / PLAT-012.
  Flavors, signing and the options file per flavor: REL. Cache policy beyond
  Firestore's own: PERSIST. Eager lists built from query results: PERF-001.
- An assigned subscription never cancelled: the `undisposed-resource`
  candidate and UI-lifecycle. FIRE-008 owns only the discarded result of a
  Firebase stream.

**When not to flag:**
- A public, read-only path (`match /public/{doc} { allow read: if true; }`)
  is deliberate; FIRE-001 reports public reads only on recursive wildcards.
- Emulators in `main_dev.dart`, `main_local.dart` or another dev entry point,
  behind `kDebugMode`, `assert`, a flavor or `--dart-define` value, or in a
  helper whose every caller is guarded.
- A listener in an app-lifetime holder (a root `ChangeNotifier` with no
  `dispose()`, a keep-alive provider, `main()`), or a stream returned to a
  `StreamBuilder` / `StreamProvider`.
- Examples and samples (`example/`, `samples/` folders) wiring emulators or
  debug providers on purpose: those are graded info.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] Posts collection is writable by anyone
- id: FIRE-001
- where: firestore.rules:8
- evidence: `match /posts/{postId} { allow write: if true; }`
- rule: deny by default, scope writes to the owner (flutter-firebase › rules.md FIRE-001)
- why: the Firebase config is public, so any script can overwrite or delete every post without the app
- fix: |
    allow create: if request.auth != null && request.resource.data.authorId == request.auth.uid
      && request.resource.data.keys().hasOnly(['authorId', 'text', 'createdAt']);
    allow update, delete: if request.auth != null && resource.data.authorId == request.auth.uid;
- confidence: confirmed

### [MEDIUM] Feed notifier never cancels its Firestore listener
- id: FIRE-008
- where: lib/features/feed/presentation/notifier/feed_notifier.dart:10
- evidence: `FirebaseFirestore.instance.collection('posts').limit(20).snapshots().listen(...)` in `build()` of an auto-dispose notifier
- rule: tie listeners to their owner's lifetime (flutter-firebase › rules.md FIRE-008)
- why: every visit adds a listener that keeps billing reads and writes `state` after dispose
- fix: |
    // data source: Stream<List<PostDto>> watchPosts() => _db.collection('posts').limit(20).snapshots().map(...);
    @riverpod
    Stream<List<Post>> feed(Ref ref) => ref.watch(watchFeedUseCaseProvider).call();
- confidence: confirmed
```

Open the report with one line naming the profile, the Firebase products and
the rules files found (`bloc, firestore + auth + messaging, firestore.rules`).
Report a pattern-wide issue (every source building queries without `limit`)
**once**, with a few locations and the shared fix.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-architecture`** for detecting the pattern and the layer rules
  (ARCH-005/007/012/101). Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-secure-defaults`** for tokens, logging, PII and secrets
  (SEC-*). Fallback: `../flutter-secure-defaults/SKILL.md`.
- **`flutter-error-handling`** for mapping Firebase exceptions to failures
  and wiring Crashlytics (ERR-*). Fallback: `../flutter-error-handling/SKILL.md`.
- **`flutter-release`** for flavors, one Firebase project per environment
  and signing (REL-*). Fallback: `../flutter-release/SKILL.md`.
- **`flutter-platform-integration`** for the notification permission flow
  (PLAT-011/012). Fallback: `../flutter-platform-integration/SKILL.md`.
- **`flutter-persistence`** for caches beyond Firestore's own and offline
  sync (PERSIST-*). Fallback: `../flutter-persistence/SKILL.md`.
- **`flutter-networking`** for non-Firebase HTTP APIs, including your own
  backend that receives FCM tokens (NET-*). Fallback:
  `../flutter-networking/SKILL.md`.
- **`flutter-navigation`** for auth-guarded routes fed by the auth stream
  (NAV-*). Fallback: `../flutter-navigation/SKILL.md`.
- **`flutter-testing`** for test strategy and fakes. Fallback:
  `../flutter-testing/SKILL.md`.
- **`dart-flutter-review`** merges FIRE findings into its report.

## References

| File | Read it when |
|---|---|
| `references/placement-by-architecture.md` | writing the Firebase source, the repository, the auth stream and the logic around them in MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX or Riverpod |
| `references/firestore-data.md` | converters and DTOs, queries, pagination, listeners, transactions and batches, offline cache, indexes, read cost |
| `references/security-rules-and-app-check.md` | writing or reviewing `firestore.rules`, `storage.rules` or `database.rules.json`, roles and custom claims, rules tests, App Check |
| `references/setup-messaging-config.md` | `initializeApp`, flavors, emulators, FCM, Crashlytics and Analytics, Remote Config, Cloud Functions callables |
| `references/testing-firebase.md` | fakes (`fake_cloud_firestore`, `firebase_auth_mocks`), the emulator suite, rules unit tests, what to test per layer |
| `references/rules.md` | every FIRE rule: detection, why, fix, false positives; reading-level slugs; what's checked elsewhere; calibration |
