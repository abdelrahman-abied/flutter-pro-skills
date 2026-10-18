# Testing Firebase code

Test each layer against the layer below it, faked. Only the data source
meets something Firebase-shaped, and even then a fake or the emulator, never
a real project (FIRE-tests-hit-real-project). Strategy, fakes vs mocks and
the per-architecture test layout are in `flutter-testing` (fallback:
`../flutter-testing/SKILL.md`).

## Contents

1. What to test, per layer
2. Sources and repositories with `fake_cloud_firestore`
3. Auth with `firebase_auth_mocks`
4. Logic over a fake repository
5. The emulator suite for integration tests
6. Rules tests
7. Messaging, Remote Config and Functions

## 1. What to test, per layer

| Layer | Test against | Prove |
|---|---|---|
| source | `FakeFirebaseFirestore`, `MockFirebaseAuth`, or the emulator | queries (filters, order, `limit`), converters, field names |
| repository | a fake source, or the source over `FakeFirebaseFirestore` | DTO → entity mapping, malformed documents, `FirebaseException.code` → failure, auth stream mapping |
| use case / notifier / view model / bloc | a fake repository contract | states, errors, pagination, that listeners stop on dispose |
| widget | overridden providers / injected fakes | rendering per state; no Firebase in widget tests |
| rules | the emulator + `@firebase/rules-unit-testing` | each path × role × validation edge |
| end to end | the emulator suite | a few critical flows (sign-up, purchase) |

## 2. Sources and repositories with `fake_cloud_firestore`

```dart
// dev_dependencies: fake_cloud_firestore, test
void main() {
  test('watchPage returns the newest 20 posts', () async {
    final db = FakeFirebaseFirestore();
    for (var i = 0; i < 25; i++) {
      await db.collection('posts').add({'authorId': 'u1', 'text': 'p$i', 'createdAt': Timestamp.fromMillisecondsSinceEpoch(i)});
    }
    final source = PostsRemoteSource(db);

    final page = await source.page();

    expect(page.items, hasLength(20));
    expect(page.items.first.text, 'p24');
  });

  test('a malformed document becomes a failure, not a crash', () async {
    final db = FakeFirebaseFirestore();
    await db.collection('posts').doc('bad').set({'text': 42});
    final repo = PostsRepositoryImpl(PostsRemoteSource(db));

    expect(await repo.post('bad'), isA<ResultError<Post>>());
  });
}
```

- The source must take `FirebaseFirestore` in its constructor for this to
  work (`placement-by-architecture.md`).
- `fake_cloud_firestore` doesn't evaluate security rules by default and
  doesn't bill reads; it proves query shape and mapping, not security or
  cost.
- To test error mapping, give the repository a fake source that throws
  `FirebaseException(plugin: 'cloud_firestore', code: 'permission-denied')`.

## 3. Auth with `firebase_auth_mocks`

```dart
test('user stream maps sign-in and sign-out', () async {
  final auth = MockFirebaseAuth(mockUser: MockUser(uid: 'u1', email: 'a@example.com'));
  final repo = AuthenticationRepository(firebaseAuth: auth);

  final users = <AppUser>[];
  final sub = repo.user.listen(users.add);
  await auth.signInWithEmailAndPassword(email: 'a@example.com', password: 'x');
  await auth.signOut();
  await pumpEventQueue();
  await sub.cancel();

  expect(users.map((u) => u.id), [AppUser.empty.id, 'u1', AppUser.empty.id]);
});
```

- Test the `FirebaseAuthException.code` → failure mapping with a fake that
  throws (`invalid-credential`, `user-disabled`, `too-many-requests`,
  `network-request-failed`), including an unknown code.
- Sign-out tests also check the cleanup: cached data cleared, user-scoped
  listeners cancelled, tokens deleted (`flutter-secure-defaults`).

## 4. Logic over a fake repository

```dart
class FakePostsRepository implements PostsRepository {
  final controller = StreamController<List<Post>>.broadcast();
  @override
  Stream<List<Post>> watch() => controller.stream;
}

test('notifier stops listening when disposed', () async {
  final repo = FakePostsRepository();
  final container = ProviderContainer(overrides: [postsRepositoryProvider.overrideWithValue(repo)]);
  final sub = container.listen(feedProvider, (_, __) {});
  expect(repo.controller.hasListener, isTrue);

  sub.close();
  container.dispose();
  await pumpEventQueue();

  expect(repo.controller.hasListener, isFalse);   // FIRE-008 as a test
});
```

The same check works for a bloc (`await bloc.close()`), a view model
(`viewModel.dispose()`) and a GetX controller (`Get.delete<…>()`).

## 5. The emulator suite for integration tests

```dart
// integration_test/app_test.dart, run after `firebase emulators:start --project demo-app`
Future<void> main() async {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: const FirebaseOptions(
    apiKey: 'demo-key', appId: '1:000000000000:android:0000000000000000',
    messagingSenderId: '000000000000', projectId: 'demo-app',
  ));
  const host = '10.0.2.2';   // Android emulator → host machine; 'localhost' elsewhere
  FirebaseFirestore.instance.useFirestoreEmulator(host, 8080);
  await FirebaseAuth.instance.useAuthEmulator(host, 9099);
  // ...pump the app and drive it
}
```

- A `demo-*` project id can't reach a real backend.
- Reset state between tests with the emulator REST endpoints
  (`DELETE http://localhost:8080/emulator/v1/projects/demo-app/databases/(default)/documents`
  and the Auth emulator's `/emulator/v1/projects/demo-app/accounts`), or use
  a fresh project id per run.
- In CI: `firebase emulators:exec --project demo-app "flutter test integration_test"`.

## 6. Rules tests

Write them in JavaScript or TypeScript with `@firebase/rules-unit-testing`,
next to the rules, and run them with `firebase emulators:exec` in CI
(`security-rules-and-app-check.md`, section 6). They are the only tests that
prove the data is protected; Dart fakes don't evaluate rules.

## 7. Messaging, Remote Config and Functions

- Put `FirebaseMessaging`, `FirebaseRemoteConfig` and `FirebaseFunctions`
  behind small sources with interfaces, and fake those in logic tests.
- Test the background handler as a plain function: call it with a
  `RemoteMessage(data: {...})` and check what it writes locally.
- Remote Config: test that logic falls back to the in-code defaults when the
  source returns nothing or throws.
- Callables: test the server function with the Functions emulator (or its
  own unit tests); on the client, test the repository's
  `FirebaseFunctionsException` mapping with a fake source.
