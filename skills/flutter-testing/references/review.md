# flutter-testing: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Top to bottom. In a diff, read the changed tests and the units that changed
without a test change. Every slug is in `references/test-smells.md` (why,
bad/good code, fix).

| ID | Default severity | What to look for |
|---|---|---|
| `TEST-unawaited-async-expect` | High | `expectLater(...)`/`expect(future, completion…)` not awaited, so the test can end before the assertion runs |
| `TEST-no-assertion` | Medium | No `expect`/`verify` (script; it follows assertion helpers) |
| `TEST-mock-of-sut` | Medium | The test mocks or fakes the class it tests (script) |
| `TEST-tests-the-mock` | Medium | Stubs `mock.m()` and then calls `mock.m()` itself; no code under test runs (script) |
| `TEST-mocked-notifier` | Medium | A Riverpod `Notifier`/Bloc is mocked to test logic that lives in it |
| `TEST-shared-state` | Medium | A container, bloc, view model or global DI registration is shared across tests, so the tests depend on their order |
| `TEST-real-delay` | Medium | `sleep`, or a real `Future.delayed`, in a test body (script) |
| `TEST-real-clock` | Medium | Logic under test reads `DateTime.now()`/`Timer` with no injected clock |
| `TEST-real-network` | Medium | `Dio()`, `http.Client()` or `HttpClient()` in a unit test with no fake adapter (script) |
| `TEST-happy-path-only` | Medium | Logic or repository with error handling, but no test of the failure state |
| `TEST-wrong-layer` | Medium | Business rules tested only through widget or integration tests, so the pyramid is inverted |
| `TEST-pump-and-settle-endless` | Medium | `pumpAndSettle` with an endless animation (spinner), which times out, or used to paper over timing |
| `TEST-interaction-only` | Low | Only `verify(...)` of calls, never the resulting state or output |
| `TEST-mock-over-fake` | Low | `when/verify` scaffolding where a small fake of the contract would do |
| `TEST-weak-matcher` | Low | `isNotNull`, `isA<X>()` or `findsWidgets` where a value would pin the behaviour |
| `TEST-implementation-finder` | Low | `byWidgetPredicate` on internals, `.at(3)`, finding private widget types |
| `TEST-visible-for-testing` | Low | `@visibleForTesting` members poked to reach internals |
| `TEST-golden-unstable` | Low | Goldens without loaded fonts, a pinned platform or a fixed surface size |
| `TEST-skip-no-reason` | Low | `skip: true` or `@Skip()` with no reason (script) |
| `TEST-giant-file` | Low | A test file over 800 lines (script) |
| `TEST-no-teardown` | Low | A container, stream controller or `tester.view` override that is never disposed or reset |
| `TEST-untested-<role>` | Medium (repository, usecase, logic), Low (source, service, view), Info (widget) | No test for the unit (script). Confirm, then report the top ranked ones, grouped |
| `TEST-preview-only` | Info | Renders and saves an image, asserts nothing (script) |

Grade by consequence in *this* code: a test that can't fail on a payment rule
is worse than one on a label. Adjust the severity and say why.

## Reporting findings

Use the suite finding format, so `dart-flutter-review` can merge the results.
Open with one line that names the profile and the classifier. Report a
pattern-wide problem **once**, with a few locations.

```markdown
### [MEDIUM] Checkout rules have no test
- id: TEST-untested-usecase
- where: lib/features/cart/domain/usecases/checkout_usecase.dart:16
- evidence: `Checkout.call` has 3 guards (terms, empty cart, limit); test_gaps.py ranks it #1 with no mirror, name or import match
- rule: MVN: use cases are pure Dart, so test them first against a fake repository (flutter-testing › strategy-by-architecture.md § MVN)
- why: a broken guard charges an empty cart or skips the terms check, and nothing would fail
- fix: |
    test/features/cart/domain/usecases/checkout_usecase_test.dart with a FakeCartRepository:
    one test per guard (throwsA(isA<CheckoutException>().having((e) => e.reason, 'reason', 'empty')))
    plus the success path (verify the fake recorded pay(total)).
- confidence: confirmed

### [MEDIUM] Debounce tests wait on the wall clock
- id: TEST-real-delay
- where: test/features/search/presentation/search_notifier_test.dart:42, test/features/search/presentation/search_notifier_test.dart:97
- evidence: `await Future<void>.delayed(SearchNotifier.debounce * 2);` inside `test(...)` (script hit, read and confirmed)
- rule: control time in tests (flutter-testing › test-smells.md § TEST-real-delay)
- why: each run sleeps for real; on a loaded CI runner the debounce window and the wait drift apart, so the test flakes
- fix: wrap the body in `fakeAsync((async) { ...; async.elapse(SearchNotifier.debounce * 2); expect(...); })`
- confidence: confirmed
```

If nothing is worth reporting, return `NO FINDINGS (testing): <what was checked>`.
