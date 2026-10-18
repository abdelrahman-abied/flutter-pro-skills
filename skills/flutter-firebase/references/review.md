# flutter-firebase: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

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
