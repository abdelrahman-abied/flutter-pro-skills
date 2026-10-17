---
name: flutter-testing
description: Plan, write and review Dart and Flutter tests the way the project's architecture needs them - which layer to test first and how (MVN use cases and notifiers with ProviderContainer overrides, MVVM view models over fake repositories, bloc_test for Bloc/Cubit, Clean Architecture use cases and repositories over fake sources), fakes vs mocks, widget tests, pump vs pumpAndSettle, fake_async, golden and integration tests. A bundled read-only script maps lib/ units to their tests, ranks untested code and flags smells (no assertions, real delays, real network, mocking the class under test). Use it whenever someone writes, reviews or audits tests (prefer it over a general code review when the code is tests), asks "what should I test", wants coverage or untested code found, tests a router redirect or a bloc, fights flaky tests, or asks about mocks, goldens, bloc_test or ProviderContainer.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.0.0"
  suite: flutter-pro-skills
---

# Flutter testing

Good tests follow the architecture. Each pattern puts its logic in a different
class and its seams in different places. A test plan that ignores the pattern
ends up pumping whole screens to check one `if`, or mocking the very notifier
it means to test. This skill gives the **strategy** (which layer to test first,
which seam to fake), **reviews** tests for smells (`TEST-*` findings), and finds
**gaps** with a bundled script. It doesn't repeat the mechanical recipes; the
Flutter and Dart teams publish those (see "Official recipe skills" below).

## Workflow

### 1. Detect the profile

A declared architecture beats inference. Look in your agent's project
instructions file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
`.github/copilot-instructions.md`), the README and any ADRs. Then read
`pubspec.yaml` `dev_dependencies` to see which tools are already in use:
`mocktail` or `mockito`, `bloc_test`, `fake_async`, `alchemist`/goldens,
`integration_test`, `patrol`. **Use what the project uses.** Don't add mockito
to a mocktail codebase. The gap script prints the detected profile on its
first lines.

### 2. Pick the strategy

| Profile | Test first (most value per test) | Fake at | Then |
|---|---|---|---|
| **MVN** | use cases (pure Dart), then notifiers through `ProviderContainer` | the **repository or source provider** (`overrideWithValue(FakeX())`); run the real use case | views with `ProviderScope(overrides:)`, one test per sealed state |
| **MVVM** (Flutter guide) | view models over **fake repositories** (Strong) | repositories (fakes implement the contract) | repositories over fake services; views reuse the same fakes |
| **Bloc / Cubit** | `blocTest` per event: `build`, `seed`, `act`, `expect`, `errors` | repositories (mocktail or fakes) | views with `MockBloc` plus `whenListen`, or a real bloc over a fake repository |
| **Clean Architecture** | use cases over fake repositories; repository impl over fake sources (mapping, errors) | contracts in `domain/` | DTO `fromJson`/`toEntity` against recorded JSON fixtures |
| **Provider / ChangeNotifier** | the notifier class, including notification counts | its constructor dependencies | `ChangeNotifierProvider.value` in widget tests |
| **GetX** | controllers as plain classes (`onInit`, `.obs` values) | `Get.put<Repo>(FakeRepo())` in `setUp`, `Get.reset()` in `tearDown` | views with `Get.testMode = true` |
| **setState** | extracted pure functions and services | constructor-injected services | widget tests carry most of the weight, so keep the logic extractable |

The playbook, with a good test per pattern, is in
`references/strategy-by-architecture.md`. Read your profile's section.

**The pyramid.** Many fast unit tests for logic, use cases and repositories;
fewer widget tests (one per view state, plus the interactions that matter); a
handful of integration tests for critical flows. If most of the suite is
widget or integration tests, logic is probably living in widgets: an
architecture finding for the `flutter-architecture` skill.

### 3. Write or review

Write with the WRITE checklist, review with the REVIEW checklist (both below).

### 4. Find gaps with the bundled script

Read-only, stdlib-only Python; no `pub get` needed:

```bash
python3 -I <skill-dir>/scripts/test_gaps.py <project-root>              # text report
python3 -I <skill-dir>/scripts/test_gaps.py <project-root> --json       # units, gaps, smells, stats
python3 -I <skill-dir>/scripts/test_gaps.py <project-root> --profile bloc --max 10
```

Full CLI: `test_gaps.py <project-root> [--json] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
Exit `0` = report produced; `2` = usage error (e.g. no `pubspec.yaml`).

- **Classification.** It uses `../flutter-architecture/scripts/arch_check.py`
  when installed, and its own path-based roles otherwise (the `classifier:` line says which).
- **Mapping.** A unit (repository-impl / repository, usecase, logic, source,
  service, view, widget) is *tested* when a test file mirrors its path
  (`test/<same path>_test.dart`, `test/unit/…` too, and `lib/src/` dropped),
  matches its name (`x_test.dart` or `x_widget_test.dart` anywhere), or
  imports it **and** uses it. Using it means
  constructing one of its concrete classes, calling one of its functions,
  reading one of its providers, or, for widgets, `find.byType(X)`. An import
  that only overrides or fakes a unit doesn't count. Files of only
  exceptions or value types, contract-only bases, dev stubs, factories and
  provider-only files aren't units (`stats.skipped`). ChangeNotifier and
  classic notifiers are logic in every profile. Local `path:` packages
  aren't scanned; the header lists them.
- **Ranking.** Gaps are ranked by architecture tier: repositories and use cases,
  then logic, then sources and services, then views, then widgets. Within a
  tier, units with branches come before trivial ones, and direct gaps before
  units that are probably exercised indirectly through a tested caller.

```text
== TEST GAPS
  profile: mvn + clean architecture (confidence high)
  classifier: arch_check (../flutter-architecture/scripts/arch_check.py)
  coverage by role: repository-impl 3/5 60%, usecase 15/30 50%, logic 16/28 57%, ...
  [TEST-untested-repository] (medium) x2 — Repository implementation with no test; ...
      #1 lib/features/orders/data/repositories/orders_repository_impl.dart  (repository-impl, 184 lines, 6 branches)  — its provider is overridden with a fake in 3 test file(s)
== TEST SMELLS
  [TEST-real-delay] (medium) x7 — Real wall-clock wait in a test (sleep / Future.delayed); ...
```

**Confirm each line by reading the code** before you report it: the script
sees names and imports, not intent. "Likely exercised indirectly" and
"pass-through" are notes, not findings, and `TEST-preview-only` usually marks
deliberate screenshot generators. The script measures *which units have a
test*, not line coverage; for that, run `flutter test --coverage`.

## WRITE checklist

- [ ] **Test the behaviour the user or caller sees**, through the unit's public
      API. Don't test private methods or call order unless the order is the contract.
- [ ] **Fake at the pattern's seam** (table above). Prefer **fakes to mocks**
      (Strong in the Flutter guide): an in-memory `FakeTodoRepository` survives
      refactors that break `when/verify` chains. Mock what you can't fake cheaply
      (a router, platform channels) or when the call *is* the behaviour.
- [ ] **Never mock the class under test.** Never mock a Riverpod `Notifier` to
      test its own logic. The Riverpod docs say to mock the repository it uses.
- [ ] **One fresh container, bloc or view model per test**, made in the test or
      `setUp` (never `main`/`setUpAll`) and disposed with
      `addTearDown(container.dispose)`, or `ProviderContainer.test()` on Riverpod 3.
- [ ] **Cover every state and the failure path.** Every sealed variant or status
      a unit can emit gets an assertion: loading, empty, success, and each
      error mapping. A notifier test with only the happy path misses most bugs.
- [ ] **Control time.** Use `fakeAsync` plus `elapse` in unit tests, and
      `tester.pump(duration)` in widget tests. Inject a clock
      (`DateTime Function() now`) instead of calling `DateTime.now()` in logic.
      Never use `sleep` or a real `Future.delayed` to "wait a bit".
- [ ] **No real network or disk in unit tests.** Use a fake source, a
      `MockClient` (`package:http/testing.dart`), a Dio `httpClientAdapter`, or
      an in-memory database. Tag the deliberate real tests (`@Tags(['real'])`) and
      keep them out of the default run.
- [ ] **Assert precisely.** Compare against a value (`equals`, a full state
      object with `==`) or use `isA<X>().having(...)`. A bare `isNotNull` or
      `isA<Success>()` passes on the wrong data. Await every `expectLater`.
- [ ] **Widget tests:** wrap the widget in the app's theme, l10n delegates and
      DI (`ProviderScope`, `BlocProvider.value`, `ChangeNotifierProvider.value`)
      with fakes. Find widgets by meaning: text, semantics label, or a `ValueKey`
      you added. Use `pump` for endless animations and `pumpAndSettle` only when
      the UI really settles. See `references/widget-and-golden.md`.
- [ ] **Name tests as sentences** (`'emits [Loading, Error] when the repository
      throws'`), grouped by unit (`group('CartNotifier', …)`).
- [ ] **Mirror `lib/` in `test/`** (`test/features/cart/…/cart_notifier_test.dart`);
      keep shared fakes in `test/helpers/` or `testing/fakes/` (Flutter samples layout).
- [ ] **Skip with a reason**: `skip: 'flaky on CI until #123'`, never `skip: true`.
- [ ] **Run it**: `flutter test` (`dart test` for pure Dart), and once more with
      `--test-randomize-ordering-seed random` to catch order dependence.

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

## When not to flag

- **Deliberate real tests**: `test/real/`, `integration_test/`, tags `real`/`integration`.
- **MVN pass-through use cases** covered by a notifier test over a fake repository (Info, once).
- **Thin widgets** without branches that a view's widget test already renders.
- **Preview or screenshot suites** kept on purpose (Info, once; suggest goldens).
- **Small apps**: a two-screen `setState` app needs a few widget tests and
  tests of the extracted logic, not a test per layer.
- **The project's own conventions** (mockito, a `test/unit` + `test/widget` split).

## Official recipe skills (if installed)

For step-by-step mechanics, defer to the official BSD-3-Clause skills from the
Flutter team (`flutter/agent-plugins`: `flutter-add-widget-test`,
`flutter-add-integration-test`) and the Dart team (`dart-lang/skills`:
`dart-add-unit-test`, `dart-generate-test-mocks`, `dart-collect-coverage`).
If they aren't installed, `references/widget-and-golden.md` and the examples
in `references/strategy-by-architecture.md` are enough to write the test by hand.

## Related skills

Sibling skills (if your agent doesn't auto-load skills, read the path given;
if one is missing, carry on and say which check you skipped):

- **`flutter-architecture`** (`../flutter-architecture/SKILL.md`): the checker
  this script uses for roles. Hard-to-write tests usually have a structural
  cause (I/O in widgets, no repository seam). Report that there.
- **`flutter-ui-practices`** (`../flutter-ui-practices/references/flutter-ui.md` §8):
  widget lifecycle, async and context, widget-test basics.
- **`dart-flutter-review`** (`../dart-flutter-review/SKILL.md`): full reviews.
  Its testing pass loads this skill and runs `test_gaps.py`.
- **`dart-naming`** (`../dart-naming/SKILL.md`): names of tests, fakes and mocks.
- **`mvn`** (the MVN author's skill, sometimes listed as `mvn-architect:mvn`):
  the MVN layout that the MVN test layout mirrors.

## References

| File | Read it when |
|---|---|
| `references/strategy-by-architecture.md` | planning or writing tests for MVN, MVVM, Bloc/Cubit, Clean, Provider, GetX or setState code |
| `references/test-smells.md` | reviewing tests: every `TEST-*` slug with why, bad/good code and fix |
| `references/widget-and-golden.md` | widget tests, finders, pump vs pumpAndSettle, fake_async, goldens, text scale and RTL, integration_test |
| `scripts/test_gaps.py` | finding untested units and test smells (read-only); regression tests in `tests/run.sh` |
