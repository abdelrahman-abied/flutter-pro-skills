---
name: dart-naming
description: Choose and review names in Dart and Flutter code - classes, methods, variables, booleans, constants, enums, type parameters, files, folders, callbacks, widgets, providers, blocs, events and states. Covers Effective Dart naming rules (casing, acronyms, no get/k/I/Hungarian prefixes, verbs for actions and nouns for values, toX vs asX), Flutter conventions (onFoo, _handleFoo, FooCallback) and role names per architecture (MVN, MVVM, Bloc/Cubit, Clean Architecture, GetX, Riverpod providers). Use it for every naming question, even a quick one like "isOnboarded or hasOnboarded?" or "what do I call this provider", whenever you name or rename anything in a .dart file, pick a file or folder name, name a bloc event, state or provider, or review a diff for naming, even if nobody says "naming convention". Reports NAME-* findings. The project's own consistent conventions win.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.5.0"
  suite: flutter-pro-skills
---

# Dart naming

Names are the most permanent part of the code. A formatter can re-indent a
file and `dart fix` can rewrite an expression, but renaming a public member
breaks every caller, and a misleading name keeps misleading every reader until
someone renames it. This skill helps you pick names that say what the thing is
or does, that match the project around them, and that follow Effective Dart
where the project hasn't decided otherwise.

## Precedence: who wins when sources disagree

1. **The project's own decisions.** Its lint config (`analysis_options.yaml`),
   its project instructions file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
   `.cursor/rules/…`, `.github/copilot-instructions.md`), its declared
   architecture, and the conventions used *consistently* in its code. If the
   whole codebase writes `userId`, `kDefaultPadding` or `IUserRepository`, new
   code follows suit and none of it is a finding. Effective Dart's first theme
   is *be consistent*. A "correct" rule applied to half a codebase makes it worse.
2. **The pattern's canonical source**: the `mvn` spec, bloclibrary.dev,
   riverpod.dev, the docs.flutter.dev architecture guide (MVVM).
3. **Effective Dart**, then 4. **Flutter team guidance for apps**, then
   5. **the Flutter framework's style guide**, only where the project follows it.

"Consistent" means most neighbouring files, not one. If the project is split
(half `fetch`, half `get`), follow the feature's majority and mention the split once.

## Before you name: read the project

- Open two or three neighbouring files. Note the role suffixes
  (`Screen`/`Page`/`View`, `ViewModel`/`Notifier`/`Bloc`/`Cubit`/`Controller`),
  the verb used for loading data (`fetch`/`load`/`get`), `userId` vs `userID`,
  and whether constants use `k`.
- Check `analysis_options.yaml` for disabled naming lints
  (`constant_identifier_names`, `non_constant_identifier_names`, `file_names`).
  A disabled lint is a project decision.
- If the architecture isn't obvious, the `flutter-architecture` skill detects
  it (if your agent doesn't auto-load skills, read `../flutter-architecture/SKILL.md`).

## Quick reference

| Kind | Style | Examples |
|---|---|---|
| Classes, enums, typedefs, extensions, mixins, type parameters | `UpperCamelCase` | `HttpRequest`, `UserRepository`, `typedef Predicate<T> = bool Function(T)` |
| Variables, parameters, members, **constants**, enum values, named params | `lowerCamelCase` | `itemCount`, `const defaultTimeout = Duration(seconds: 5)`, `Status.inProgress` |
| Packages, directories, files, import prefixes | `lowercase_with_underscores` | `user_repository.dart`, `import 'dart:math' as math;` |
| Acronyms longer than 2 letters | Capitalise like a word | `HttpClient`, `parseJson`, `Uri`, `htmlElement` |
| 2-letter acronyms capitalised in English | Keep both caps (lowercase at the start of a lowerCamel name) | `ID`, `UI`, `TV` → `userID`, `UIConfig`, `idToken` |
| Private | Leading `_` **only** for library-private declarations | `_cache`, `_HeaderTile`, never `_localVar` or `_param` |
| Unused callback params (Dart ≥3.7) | `_` wildcard, repeatable | `.then((_) => …)`, `onError((_, _) => …)` |
| Flutter callbacks | property `onFoo`, handler `_handleFoo`, typedef `FooCallback` | `onTap`, `_handleTap`, `typedef ItemSelectedCallback = void Function(Item)` |
| Files | snake_case of the main declaration | `class OrderSummaryCard` → `order_summary_card.dart` |

## The semantic rules that matter most

- **Booleans** read as non-imperative verb phrases: `isEnabled`, `hasError`,
  `canSubmit`, `shouldRetry`. Use the positive form (`isVisible`, not
  `isHidden`). A **named bool parameter** drops the verb: `growable: true`,
  `enabled: false`. Don't use positional bools (`render(true)` says nothing).
- **Side-effect methods** are imperative verbs: `save()`, `refresh()`, `close()`.
  **Value-returning members** are nouns or non-imperative phrases:
  `elementAt()`, `toJson()`, `user.fullName`.
- **Don't start a method with `get`.** A cheap, argument-free, side-effect-free
  accessor is a getter (`breakfastOrder`). An expensive or async one names its
  work: `fetchUser()`, `loadSettings()`, `calculateTotal()`. (`getX` is fine
  when it mirrors a platform API you wrap.)
- `toX()` returns a **copy**. `asX()` returns a **view** of the same object.
- Put the most descriptive noun **last**: `pageCount`, not `numPages`.
- **One word per concept** across the API: don't mix `fetch`/`load`/`get`/`retrieve`
  for the same operation. Use the platform's word (`length`, `add`).
- **No prefix letters**: no `kTimeout`, `strName`, `mValue` or `IUserRepository`.
  No `Async` suffix either: the `Future` already says it.
- **No noise words** (`Manager`, `Helper`, `Util(s)`, `Data`, `Info`) where a
  precise word exists. `Impl` is fine where the architecture prescribes it.
- **Never name a method `onFoo`.** `onFoo` is a function-typed property. (Bloc's
  private `_onEventName` handlers are that pattern's own convention.)
- **Units go in types**: `Duration timeout`, not `int timeoutMs`. If a
  primitive is forced on you (JSON, FFI), name the unit: `timeoutMillis`.
- **Pluralise collections, name maps by the lookup**: `users`, `usersById`.
  Name enums and sealed types in the singular: `PaymentMethod.card`.

## Role names per architecture (summary)

Name a class for the role it plays in the project's architecture, using the
project's vocabulary. Full details, file trees and the reasons are in
`references/naming.md` §12.

| Pattern | Logic holder | State | Input | Data |
|---|---|---|---|---|
| MVN | `XNotifier` (never ViewModel/Controller/VM); singular folders `notifier/ state/ view/ widget/` | sealed `XState`: `XInitial/XLoading/XSuccess/XError` | notifier methods | `XEntity`, `XRepository` + `XRepositoryImpl`, `XRequest`/`XResponse`, `XSource`; use cases named for one intent (`FetchTrendingMovies`) |
| MVVM (Flutter guide) | `XViewModel`, used by `XScreen` | view-model fields | `Command0`/`Command1` fields (`load`, `deleteBooking`) | `XRepository` (abstract) + `XRepositoryRemote`/`XRepositoryLocal`, `XApiClient`/`XService` |
| Bloc / Cubit | `XBloc` / `XCubit` | `XInitial/XInProgress/XSuccess/XFailure`, or one `XState` + `XStatus` enum | `XEvent` subclasses in the **past tense** (`XStarted`, `CounterIncrementPressed`) | `XRepository` over data providers (`XApiClient`) |
| Clean Architecture | (per presentation pattern) | | use cases as verb phrases (`SignInWithEmail`) | entity, `XRepository` contract + impl, `XRemoteDataSource`/`XLocalDataSource`, mappers (`toEntity()`) |
| MVC / GetX | `XController` (`extends GetxController` in GetX) | `XModel` / `.obs` fields | controller methods | GetX: `XBinding`, `XService` |
| Riverpod | provider names derive from the function or class: `currentUser` → `currentUserProvider` | | | families: `userProvider(id)`; check the `.g.dart` for the exact name |

## When to load `references/naming.md`

It's about 520 lines with a Contents list. Read only the sections you need
(`grep -n '^##' references/naming.md`):

| You are… | Read |
|---|---|
| Unsure about casing, acronyms, `_`, prefixes, `I`/`Impl`, wildcards | §1–§2 |
| Naming a public API, a getter vs a method, a boolean, a generic | §3–§6 |
| Naming callbacks, widgets, files, folders, tests, fakes | §7–§8 |
| Settling a judgment call ("is `UserData` OK?"), or renaming | §9–§10 |
| Reviewing names | §11 checklist |
| Naming a notifier, view model, bloc event or state, use case, repository, data source, controller, binding or provider | §12 |

## Naming something new ("what should I call this?")

1. **What role does it play?** If it's an architectural role, take the
   project's suffix (§12). Otherwise name what it *is* (noun) or what it *does*
   (verb).
2. **Does it act or answer?** It acts (side effect): imperative verb. It
   answers cheaply: getter, noun phrase. It answers expensively: name the work.
3. **How far does it travel?** Make the length proportional to scope: `i` in a
   loop, `selectedPaymentMethod` across a feature, the most care for a public
   package API.
4. **Which words?** Use the domain's vocabulary ("subscriber", not "customer",
   if that's what the business says) and the verb the project already uses.
5. **Read the call site aloud.** `if (cart.isEmpty)`, `repository.save(order)`,
   `OrderCard(onSelected: …)` should read like a sentence.

Offer one recommended name with a one-line reason. Add an alternative only when
the choice really depends on something you can't see.

## Renaming safely

- **Private or app-internal code**: use the IDE or analyzer rename, so every
  reference is updated, then run `dart analyze`.
- **Public API of a published package**: renaming breaks callers. Add the new
  name and keep the old one as a forwarding member
  (`@Deprecated('Use fetchUser instead.') Future<User> getUser() => fetchUser();`)
  for at least one minor version, and note it in `CHANGELOG.md`.
- **Wire names stay.** JSON keys, `@JsonKey`, Firestore fields, route paths,
  shared-preferences keys and analytics event names are contracts. Rename the
  Dart identifier and keep the wire name
  (`@JsonKey(name: 'user_id') final String userID;`). Flag any wire-level change
  as a migration.
- **Generated names** (Riverpod providers, `freezed` classes, `.g.dart`) change
  when their source changes. Rename the source and rerun the code generator,
  never the generated file.

## Reporting naming findings

Use the suite finding format, with `NAME-<slug>` IDs. Keep slugs stable so
findings from several reviewers can be merged:

```markdown
### [LOW] Method that returns a value is named like a getter call
- id: NAME-get-prefix
- where: lib/data/user_repository.dart:18
- evidence: `Future<User> getUser(String id)` performs an HTTP request
- rule: Effective Dart: AVOID starting a method name with `get` (dart-naming › naming.md §5)
- why: `get` hides that this is async network work; the repository already uses `fetch` elsewhere
- fix: |
    Future<User> fetchUser(String id)   // rename with the IDE; app-internal, no deprecation needed
- confidence: confirmed
```

Common slugs: `NAME-get-prefix`, `NAME-async-suffix`, `NAME-prefix-letters`
(k/m/Hungarian), `NAME-i-prefix`, `NAME-negative-bool`, `NAME-positional-bool`,
`NAME-imperative-bool`, `NAME-noise-word`, `NAME-abbreviation`,
`NAME-inconsistent-term`, `NAME-misleading`, `NAME-on-method`,
`NAME-callback-tense`, `NAME-file-mismatch`, `NAME-grab-bag-file`,
`NAME-unit-in-name`, `NAME-role-vocabulary` (two vocabularies for one role),
`NAME-bloc-event-tense`, `NAME-bloc-state-not-noun`, `NAME-provider-verb`.

**Severity.** Most naming findings are **Low**. Make it **Medium** when the
name is misleading (it says one thing and does another), when it's on a public
API that will be costly to change, or when one role has two vocabularies across
the project. Naming is never **High** on its own. Casing problems that a lint
already reports (`camel_case_types`, `non_constant_identifier_names`,
`file_names`) are `LINT:<code>` findings from the analyzer, not `NAME-*`
duplicates. MVN's forbidden suffixes are reported by `ARCH-112` when the
`flutter-architecture` checker runs, so don't report them twice.

**Don't report** conventions the project uses consistently, generated code,
names that mirror a wire format or a wrapped platform API, framework-style
names in a project that follows the framework style guide, or (in a diff
review) untouched names that aren't actively misleading.

The `dart-flutter-review` skill's script (`../dart-flutter-review/scripts/review.sh`)
lists naming *candidates* (`get`-prefixed methods, `Async` suffixes, prefix
letters, `I`-prefixed types, noise words, negative booleans, public `onX`
methods). Confirm each one by reading before you report it. Without that
skill, check the §11 checklist by reading.

## Related skills

Sibling skills (if your agent doesn't auto-load skills, read `../<name>/SKILL.md`):
`dart-flutter-best-practices` (the hub: WRITE workflow, Effective Dart, lints),
`flutter-ui-practices` (widgets, lifecycle, performance), `flutter-architecture`
(detecting and judging the architecture whose role names you follow), and
`dart-flutter-review` (full reviews that merge `NAME-*` findings with the rest).
The `mvn` skill, if installed, is the canonical MVN spec. If a sibling is
missing, this skill still stands on its own. Say which check you couldn't run.
