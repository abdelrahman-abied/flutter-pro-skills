# Finding format (every reviewer pass returns this)

Every judgment pass returns its findings as Markdown text in this exact shape,
whether a parallel sub-agent runs it or you run it yourself. The lead then
merges, dedupes and ranks findings mechanically, so a pass that invents its
own layout makes the merge guesswork. The final report the user sees is a
different, friendlier layout (see `references/review-guide.md` › Report
template). This format is the hand-off between passes.

## The shape

```markdown
### [HIGH] AnimationController never disposed
- id: UI-lifecycle            # ARCH-0xx | AP- | NAME- | UI- | ED- | TEST- | ERR-0xx | ERR- | SEC-0xx | SEC- | NAV-0xx | NAV- | FORM-0xx | FORM- | I18N-0xx | I18N- | LINT:<code>
- where: lib/ui/home/home_screen.dart:31, lib/ui/cart/cart_screen.dart:12
- evidence: `late final _c = AnimationController(vsync: this);` with no dispose() override
- rule: Flutter: dispose what you create (flutter-ui-practices › flutter-ui.md §1)
- why: keeps ticking and retains the State after pop → memory/CPU leak per visit
- fix: |
    @override
    void dispose() { _c.dispose(); super.dispose(); }
- confidence: confirmed       # confirmed (read the code) | likely (strong signal, not fully traced)
```

| Field | Rules |
|---|---|
| heading | `### [SEVERITY] <one-line title>`. SEVERITY is `HIGH`, `MEDIUM`, `LOW` or `INFO`. Mechanical items are not findings here (see below). The title names the problem, not the fix |
| `id` | One ID from the prefixes below. Use the most specific one that applies |
| `where` | `path:line` relative to the project root, comma-separated. One finding covers the **same root cause** in every location. Don't list it twelve times |
| `evidence` | The quoted code, or a precise description of it ("no `dispose` override in `_CartState`"). If the script found it, say so and still quote what you read |
| `rule` | The rule and its source: `Effective Dart: AVOID …`, `ARCH-005 ui-depends-on-data-source (flutter-architecture › anti-patterns.md)`, `Flutter: …`, `MVN spec: …` |
| `why` | The concrete consequence *in this code* (crash, leak, untestable, breaking API), not the general principle |
| `fix` | The change, as a short code block or a precise instruction. For a public API rename, add the `@Deprecated` forwarding member |
| `confidence` | `confirmed`: you read the code and traced it (the dispose isn't in a base class, mixin or `ref.onDispose`). `likely`: there's a strong signal you couldn't fully trace. Never report a `[CANDIDATE]` line you haven't opened |

### ID prefixes

| Prefix | Use for |
|---|---|
| `ARCH-0xx` | Import-graph rules, e.g. `ARCH-005`. Use the ID that `arch_check.py` printed, or the catalog rule you confirmed by reading |
| `ARCH-1xx` | Code-pattern rules, e.g. `ARCH-101` io-in-widget |
| `AP-<slug>` | Documented anti-patterns with no automated check: `AP-god-viewmodel`, `AP-boolean-soup-state`, `AP-passthrough-usecase` |
| `NAME-<slug>` | Naming: `NAME-get-prefix`, `NAME-negative-bool`, `NAME-i-prefix` |
| `UI-<slug>` | Flutter UI and lifecycle: `UI-undisposed-controller`, `UI-context-after-await`, `UI-future-in-build` |
| `ED-<slug>` | An Effective Dart guideline: `ED-future-void`, `ED-swallowed-catch`, `ED-late-check` |
| `TEST-<slug>` | Testing (the optional testing pass, `flutter-testing`): an untested unit or a test smell. Use the slug `test_gaps.py` printed (`TEST-untested-repository`, `TEST-no-assertion`), or a stable one you name when reading (`TEST-tests-implementation-details`) |
| `ERR-0xx` | Error-handling rules found by `check_errors.py` (the optional errors pass, `flutter-error-handling`), e.g. `ERR-001` swallowed catch. Use the number the script printed |
| `ERR-<slug>` | Error-handling findings from reading the code, with no script rule: `ERR-result-and-throw-mixed`, `ERR-error-shown-raw` |
| `SEC-0xx` | Security-default rules found by `check_secure_defaults.py` (`flutter-secure-defaults`), e.g. `SEC-001` token-in-plain-storage. Use the number the script printed |
| `SEC-<slug>` | Security findings from reading the code, and `flutter-security-audit` `scan.sh` hits with no SEC-0xx counterpart: lower-case the scan id (`NET-NO-PINNING` → `SEC-net-no-pinning`) and keep its MASVS/CWE tags in `rule:` |
| `NAV-0xx` / `NAV-<slug>` | Navigation and deep links (`flutter-navigation`): `check_navigation.py` rules (`NAV-003` unvalidated-route-param) or reading-level slugs (`NAV-deep-link-skips-guard`) |
| `FORM-0xx` / `FORM-<slug>` | Forms and input (`flutter-forms`): `check_forms.py` rules (`FORM-005` submit-without-busy-guard) or slugs (`FORM-client-only-validation`) |
| `I18N-0xx` / `I18N-<slug>` | Localisation, RTL and formatting (`flutter-i18n`): `check_i18n.py` rules (`I18N-010` hardcoded-ui-string) or slugs (`I18N-overflow-when-translated`) |
| `PERF-0xx` / `PERF-<slug>` | Performance (`flutter-performance`): `check_performance.py` rules (`PERF-001` eager-list-over-data) or slugs (`PERF-rebuild-whole-screen`) |
| `PERSIST-0xx` / `PERSIST-<slug>` | Local storage, caching and migrations (`flutter-persistence`): `check_persistence.py` rules (`PERSIST-001` sql-built-from-strings) or slugs (`PERSIST-no-cache-policy`) |
| `DS-0xx` / `DS-<slug>` | Design system and theming (`flutter-design-system`): `check_design_system.py` rules (`DS-005` theme-extension-not-registered) or slugs (`DS-no-component-layer`) |
| `A11Y-0xx` / `A11Y-<slug>` | Accessibility (`flutter-accessibility`): `check_accessibility.py` rules (`A11Y-001` icon-button-without-label) or slugs (`A11Y-focus-order`) |
| `LINT:<code>` | An analyzer diagnostic with no better home: `LINT:unused_field`. When a lint is the symptom of a judgment finding, fold it into that finding's evidence |

Slugs for NAME/UI/ED/TEST/ERR/SEC/NAV/FORM/I18N/PERF/PERSIST/DS/A11Y are free-form but stable: lower-kebab-case,
named after the problem. Reuse one slug for one problem across the whole report.

**Overlaps.** An empty or default-returning `catch` can surface three ways: the
`swallowed-catch` candidate, `ERR-001` from `check_errors.py`, and
`ED-swallowed-catch` from the idioms pass. Report it **once**. When the errors
pass ran, the `ERR-` ID leads (it is the most specific) and the others go in
`rule:`. Without it, use `ED-swallowed-catch`. Likewise an untested unit that is
also untestable because of its architecture (I/O in a widget) is one finding
under the `ARCH-` ID, with the testing consequence in `why:`.

**Checker IDs beat reading-level slugs** for the same file and line, because
they're stable and the sibling skill documents them:

| When this ran | Keep | Drop (cite it in `rule:`) |
|---|---|---|
| `check_i18n.py` | `I18N-010` hardcoded-ui-string | `UI-l10n` |
| `check_i18n.py` | `I18N-012` physical-direction-geometry | `UI-rtl` |
| `check_secure_defaults.py` | `SEC-0xx` | the `scan.sh` id for the same line (e.g. `SEC-001` over `STO-TOKEN-PREFS`) |
| `check_forms.py` | `FORM-008` controller-created-inline | the `undisposed-resource` candidate / `UI-lifecycle` on that controller |
| `check_navigation.py` | `NAV-0xx` | a `UI-` slug about the same route or link |
| `check_performance.py` | `PERF-001/002/003` (eager, shrinkWrap, intrinsic lists) | `UI-eager-list`, the `eager-children-map` candidate |
| `check_performance.py` | `PERF-005/006` (animated Opacity, saveLayer in list items) | `UI-opacity`, the `opacity-widget` candidate |
| `check_performance.py` | `PERF-004` / `PERF-008/009` / `PERF-010` / `PERF-011` | `UI-image-decode-size` / `UI-rebuild-scope` / `UI-build-side-effect` (sort in build) / `UI-blocking-ui-isolate` |
| `check_design_system.py` | `DS-001/002` (raw colour, raw text style) | `UI-hardcoded-style`, the `hardcoded-color` candidate |
| `check_accessibility.py` | `A11Y-0xx` | `UI-a11y` |

Some overlaps go the other way, because the suite already owns them: navigation
or `BuildContext` inside a logic class stays `ARCH-102`, `context` after
`await` stays `UI-context-after-await`, and controllers held in providers stay
`ARCH-109`. Tokens and credentials in SharedPreferences or Hive stay `SEC-001`
(not `PERSIST-`), storage I/O in widgets stays `ARCH-101`, a hard-coded label
stays `I18N-010` (A11Y reports only a *missing* label), obscured fields and
autofill stay `FORM-001/002/003`, and physical left/right geometry stays
`I18N-012` (DS judges only magic numbers). The checker ID, if any, goes in `rule:`.

### Severity

High means a bug now or under ordinary use, or an architecture violation that
defeats the pattern's core guarantee. Medium hurts maintainability,
testability or performance, or is a costly API to change later. Low is an
idiom or consistency issue with an easy, local fix. Info is an observation or
trade-off, not a defect. The full rubric with examples is in
`references/review-guide.md` › Severity rubric.

### Mechanical output

Passes don't return Mechanical items. The lead writes **one** collapsed
Mechanical line from the AUTO-FIXABLE and FORMAT sections. Analyzer output that
`dart fix` can't apply is *not* Mechanical: it belongs in a judgment finding.

### No findings

If a pass finds nothing worth reporting, it returns exactly
`NO FINDINGS (<dimension>): <one line on what was checked>`.

## Examples

### Architecture (ARCH)

```markdown
### [HIGH] Cart view talks to the network directly
- id: ARCH-101
- where: lib/features/cart/presentation/view/cart_view.dart:35, lib/features/cart/presentation/view/cart_view.dart:7
- evidence: `await Dio().get<int>('https://example.com/cart/count')` inside `_CartViewState.fetchCount`, called from `FutureBuilder(future: fetchCount())`; the file imports `package:dio/dio.dart` (ARCH-005 on L7)
- rule: ARCH-101 io-in-widget, ARCH-005 ui-depends-on-data-source (flutter-architecture › anti-patterns.md); profile: mvn (declared in AGENTS.md)
- why: the request can't be faked in a widget test, its errors bypass the notifier's state, and it refires on every rebuild
- fix: |
    Move the call into CartApi/CartRepositoryImpl, expose it through a use case,
    and read it in a CartNotifier; the view does `ref.watch(cartNotifierProvider)`.
- confidence: confirmed
```

ARCH-005 and ARCH-101 share a root cause here, so they merge into one finding.
The more specific ID (ARCH-101) leads, and the other is cited in `rule`.

### Flutter UI (UI)

```markdown
### [HIGH] Polling Timer and ScrollController are never released
- id: UI-undisposed-resource
- where: lib/features/cart/presentation/view/cart_view.dart:20, lib/features/cart/presentation/view/cart_view.dart:27
- evidence: `final _scroll = ScrollController();` and `_poll = Timer.periodic(...)` in `_CartViewState`; there's no `dispose()` override, and `State` has no mixin that releases them (analyzer: `unused_field` on `_poll`)
- rule: Flutter: dispose what you create (flutter-ui-practices › flutter-ui.md §1)
- why: after the screen pops, the timer keeps firing `setState` on a defunct State ("setState() called after dispose()") and both objects leak per visit
- fix: |
    @override
    void dispose() {
      _poll?.cancel();
      _scroll.dispose();
      super.dispose();
    }
- confidence: confirmed
```

### Naming (NAME)

```markdown
### [MEDIUM] Async fetch named like a getter, on a public API
- id: NAME-get-prefix
- where: lib/features/cart/data/sources/cart_api.dart:6, lib/features/cart/data/sources/cart_api.dart:19
- evidence: `Future<List<String>> getItems();` on the public `ICartApi` contract and its implementation
- rule: Effective Dart: AVOID starting a method name with `get` (dart-naming › naming.md §5)
- why: it reads as a cheap accessor, but it's a network call. Renaming it later breaks every implementer and caller
- fix: |
    Rename to `fetchItems()`. If the package is published, keep
    `@Deprecated('Use fetchItems') Future<List<String>> getItems() => fetchItems();`
    for one release.
- confidence: confirmed
```

### Testing (TEST)

```markdown
### [MEDIUM] CartRepositoryImpl has no test, and it is the only place errors are mapped
- id: TEST-untested-repository
- where: lib/features/cart/data/repositories/cart_repository_impl.dart:8
- evidence: `test_gaps.py` ranked it #1 untested unit (repository-impl); no `test/**/cart_repository_impl_test.dart`, no test imports it
- rule: test repositories against a fake source (flutter-testing; priority: repositories and use cases first)
- why: its mapping of `CartApi` results and failures is untested, so a broken mapping ships silently and every notifier above it inherits the bug
- fix: |
    Add test/features/cart/data/repositories/cart_repository_impl_test.dart with a
    FakeCartApi: one test for the success mapping, one per failure the source can throw.
- confidence: confirmed
```

### Error handling (ERR)

```markdown
### [HIGH] Network failures are swallowed and look like an empty cart
- id: ERR-001
- where: lib/features/cart/data/sources/cart_api.dart:23, lib/features/cart/data/sources/cart_api.dart:31
- evidence: `catch (e) { return const []; }` and `catch (e) {}`; `check_errors.py` ERR-001 swallowed-catch (also the `swallowed-catch` candidate, ED-swallowed-catch)
- rule: ERR-001 swallowed-catch (flutter-error-handling); Effective Dart: DON'T discard errors
- why: an offline user sees "your cart is empty" instead of an error with a retry, and nothing is logged
- fix: |
    Catch the transport type only, map it to a typed failure
    (`on DioException catch (e, st) { throw CartFailure.network(e, st); }`) or return a Result,
    and let the notifier render the error state.
- confidence: confirmed
```

### Security (SEC)

```markdown
### [HIGH] Session token stored in plain SharedPreferences
- id: SEC-001
- where: lib/data/services/shared_preferences_service.dart:38
- evidence: `await sharedPreferences.setString(_tokenKey, token);` (check_secure_defaults SEC-001; scan.sh STO-TOKEN-PREFS, MASVS-STORAGE · CWE-312)
- rule: SEC-001 token-in-plain-storage (flutter-secure-defaults); flutter-security-audit L5 key & data custody
- why: SharedPreferences is a plain file that ends up in device backups, so anyone with the backup or a rooted device can replay the session
- fix: |
    Store it with flutter_secure_storage in a data-layer `TokenStore` source;
    the AuthRepository owns the session and the API client reads the token
    through an auth interceptor. View models only see `isAuthenticated`.
- confidence: confirmed
```
