# Security rules, roles and App Check

The Firebase config in `firebase_options.dart` is public: the API key and
project id identify the project, they don't protect it. Anyone can call
Firestore, Storage, the Realtime Database and callable functions directly.
Security rules decide every request, and App Check decides which clients may
ask at all. Nothing in the Flutter app is a security boundary.

## Contents

1. Principles
2. Firestore rules patterns
3. Storage rules patterns
4. Realtime Database rules patterns
5. Roles: custom claims, not client fields
6. Testing rules with the emulator
7. App Check
8. Review checklist

## 1. Principles

- **Deny by default.** No `match /{document=**}` that grants anything. Each
  collection gets its own `match` with explicit operations
  (`get`, `list`, `create`, `update`, `delete` when `read`/`write` are too
  broad).
- **Signed-in is not authorised.** `request.auth != null` only proves an
  account exists; anonymous auth gives anyone one. Compare
  `request.auth.uid` with the path (`/users/{userId}`) or an owner field
  (FIRE-003).
- **Validate the data.** Check types, sizes and allowed keys of
  `request.resource.data`, and that server-owned fields (`role`,
  `createdAt`, counters) don't change (FIRE-rules-no-validation).
- **No time bombs.** The console's test mode (`request.time <
  timestamp.date(...)`) is either open or broken (FIRE-002).
- **Test them.** Rules are code that guards all of your data: write tests
  for each path and role and run them in CI (section 6).

## 2. Firestore rules patterns

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    function signedIn() { return request.auth != null; }
    function isUser(uid) { return signedIn() && request.auth.uid == uid; }
    function isAdmin() { return signedIn() && request.auth.token.role == 'admin'; }
    function unchanged(keys) { return !request.resource.data.diff(resource.data).affectedKeys().hasAny(keys); }

    match /users/{userId} {
      allow get: if isUser(userId) || isAdmin();
      allow create: if isUser(userId)
        && request.resource.data.keys().hasOnly(['name', 'photoUrl', 'createdAt'])
        && request.resource.data.name is string && request.resource.data.name.size() <= 80
        && request.resource.data.createdAt == request.time;
      allow update: if isUser(userId) && unchanged(['role', 'createdAt']);
      allow delete: if false;   // done by a Cloud Function that also cleans up
    }

    match /posts/{postId} {
      allow get, list: if signedIn();
      allow create: if signedIn()
        && request.resource.data.authorId == request.auth.uid
        && request.resource.data.text is string && request.resource.data.text.size() <= 2000;
      allow update, delete: if signedIn() && resource.data.authorId == request.auth.uid;
    }

    match /public/{doc} {
      allow read: if true;    // public on purpose, one path, read only
      allow write: if isAdmin();
    }
  }
}
```

- `list` rules must hold for every document the query could return:
  Firestore rejects a query the rules can't prove safe, so the client query
  has to filter on what the rule checks (`where('authorId', isEqualTo:
  uid)`). Rules are not filters.
- `get()`/`exists()` lookups in rules cost a read each and are capped per
  request; prefer claims for roles.
- Keep `rules_version = '2'` (needed for recursive wildcards in collection
  group queries).

## 3. Storage rules patterns

```
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /avatars/{userId}/{fileName} {
      allow read: if request.auth != null;
      allow write: if request.auth != null && request.auth.uid == userId
        && request.resource.size < 2 * 1024 * 1024
        && request.resource.contentType.matches('image/.*');
    }
    match /public/{fileName} {
      allow read: if true;
    }
  }
}
```

- `read` includes `list`: `allow read: if true` on `/{allPaths=**}` lets
  anyone enumerate the whole bucket (FIRE-001 medium).
- Limit size and content type on every write, or one user can fill the
  bucket (and your bill).
- Storage rules can read Firestore with `firestore.get(...)`, which costs a
  read; claims are cheaper.

## 4. Realtime Database rules patterns

```json
{
  "rules": {
    ".read": false,
    ".write": false,
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid",
        "name": { ".validate": "newData.isString() && newData.val().length <= 80" },
        "$other": { ".validate": false }
      }
    }
  }
}
```

- Rules cascade: a `.read`/`.write` granted at a parent can't be revoked by
  a child. Never grant at the root (FIRE-001, FIRE-003).
- `.validate` is not cascading and doesn't apply to deletes.
- The RTDB test mode is `"now < 1700000000000"` (FIRE-002).

## 5. Roles: custom claims, not client fields

```js
// Cloud Function (Admin SDK): only trusted code sets roles
const { getAuth } = require('firebase-admin/auth');
exports.grantModerator = onCall(async (request) => {
  if (request.auth?.token.role !== 'admin') throw new HttpsError('permission-denied', 'admins only');
  await getAuth().setCustomUserClaims(request.data.uid, { role: 'moderator' });
});
```

```dart
// Client: read the claim for display only; the rules enforce it
final token = await FirebaseAuth.instance.currentUser?.getIdTokenResult(true);
final role = token?.claims?['role'] as String?;
```

- The client never writes `role`, `isAdmin`, `permissions` or `claims`
  (FIRE-010), and the rules reject writes that touch them.
- A role stored in a user-writable document, or in Remote Config, is a role
  any user can grant themselves (FIRE-role-trusted-from-client, FIRE-009).
- Claims refresh when the ID token refreshes (at most an hour); force it
  with `getIdTokenResult(true)` after a change.

## 6. Testing rules with the emulator

```js
// test/firestore.rules.test.js  (npm i -D @firebase/rules-unit-testing firebase mocha)
const { initializeTestEnvironment, assertFails, assertSucceeds } = require('@firebase/rules-unit-testing');
const { doc, getDoc, setDoc } = require('firebase/firestore');
const fs = require('fs');

let env;
before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-rules',
    firestore: { rules: fs.readFileSync('firestore.rules', 'utf8') },
  });
});
after(() => env.cleanup());

it('a user reads only their own profile', async () => {
  const alice = env.authenticatedContext('alice').firestore();
  await assertSucceeds(getDoc(doc(alice, 'users/alice')));
  await assertFails(getDoc(doc(alice, 'users/bob')));
});

it('a user cannot make themselves admin', async () => {
  const alice = env.authenticatedContext('alice').firestore();
  await assertFails(setDoc(doc(alice, 'users/alice'), { name: 'A', role: 'admin' }, { merge: true }));
});
```

Run with `firebase emulators:exec --only firestore "npx mocha"` locally and
in CI. Use a `demo-*` project id so nothing can reach a real project. Cover
each collection, each role (anonymous, signed in, owner, admin), and the
validation edges (missing field, wrong type, oversize).

## 7. App Check

```dart
await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
await FirebaseAppCheck.instance.activate(
  providerAndroid: kDebugMode ? const AndroidDebugProvider() : const AndroidPlayIntegrityProvider(),
  providerApple: kDebugMode ? const AppleDebugProvider() : const AppleAppAttestWithDeviceCheckFallbackProvider(),
  providerWeb: ReCaptchaEnterpriseProvider('your-recaptcha-enterprise-site-key'),
);
// Older firebase_app_check versions:
// activate(androidProvider: kDebugMode ? AndroidProvider.debug : AndroidProvider.playIntegrity,
//          appleProvider: kDebugMode ? AppleProvider.debug : AppleProvider.appAttestWithDeviceCheckFallback,
//          webProvider: ReCaptchaV3Provider('site-key'));
```

- Activate right after `initializeApp`, before the first Firestore,
  Storage, Functions or Realtime Database call (FIRE-011).
- Debug providers only under `kDebugMode` (FIRE-012). Register each
  developer's debug token in the console; never commit one.
- Watch the App Check metrics, then **enforce** per product in the console
  (FIRE-app-check-not-enforced). Callables enforce with
  `enforceAppCheck: true` in the function options.
- App Check raises the cost of abuse; it doesn't replace rules. A user of
  the genuine app can still send any request the rules allow.

## 8. Review checklist

- [ ] No `if true` write, no test-mode date, no grant at the root (FIRE-001/002).
- [ ] No auth-only write on a recursive wildcard (FIRE-003).
- [ ] Every write validates `request.resource.data` and protects server-owned fields.
- [ ] Roles come from custom claims; clients can't write them (FIRE-010).
- [ ] Storage writes limit size and content type.
- [ ] Rules tests exist and run in CI against the emulator.
- [ ] App Check activated with production providers and enforced (FIRE-011/012).
- [ ] `firebase.json` names the rules and indexes files that are reviewed.
