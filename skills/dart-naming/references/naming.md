# Naming conventions: Dart, Flutter, and general principles

Sources: Effective Dart *Style → Identifiers* and *Design → Names*
(dart.dev/effective-dart), the Flutter style guide's *Naming* section, the
Flutter architecture recommendations and case study (docs.flutter.dev/app-architecture),
bloclibrary.dev *Naming Conventions*, the `riverpod_generator` docs, the MVN
spec by its author, plus general naming principles that apply in every language.

Names are the most permanent part of the code. A formatter can re-indent a file
and `dart fix` can rewrite an expression, but renaming a public member breaks
every caller. Take the time to get names right when you write them.

## Contents
1. Casing (lint-enforced)
2. Underscores, prefixes, wildcards
3. Choosing the words (Effective Dart *Design*)
4. Booleans
5. Methods and functions
6. Type parameters
7. Flutter-specific naming
8. Files, directories, architecture roles
9. General principles (language-agnostic)
10. Renaming existing code safely
11. Review checklist
12. Role naming per architecture (MVN, MVVM, Bloc/Cubit, Clean Architecture, MVC, GetX, Riverpod providers)

---

## 1. Casing (lint-enforced)

| Kind | Style | Lint |
|---|---|---|
| Classes, enums, typedefs, mixins, type parameters | `UpperCamelCase` | `camel_case_types` |
| Extensions | `UpperCamelCase` | `camel_case_extensions` |
| Packages, directories, source files | `lowercase_with_underscores` | `package_names`, `file_names` |
| Import prefixes | `lowercase_with_underscores` | `library_prefixes` |
| Variables, parameters, members, top-level functions | `lowerCamelCase` | `non_constant_identifier_names` |
| Constants and enum values | `lowerCamelCase` (PREFER) | `constant_identifier_names` |

```dart
class SliderMenu {}
typedef Predicate<T> = bool Function(T value);
extension MyFancyList<T> on List<T> {}
enum ConnectionState { idle, connecting, connected }

const defaultTimeout = Duration(seconds: 30);       // not DEFAULT_TIMEOUT, not kDefaultTimeout
final urlScheme = RegExp('^([a-z]+):');

import 'package:js/js.dart' as js;
import 'package:angular_components/angular_components.dart' as angular_components;
```

Annotation-like class instances are lowerCamel too (`const deprecated = Deprecated(...)`).

**`SCREAMING_CAPS` exception.** Use it only when you add to a file that already
uses it, or when you generate code that mirrors Java/protobuf names. Dart
moved away from it because constants are often changed to `final`, which would
force a rename, and because `enum.values` is lowercase.

### Acronyms and abbreviations

- **Longer than two letters:** capitalise like a word: `HttpClient`, `Uri`,
  `JsonCodec`, `parseHtml`, `NasaMission`. Writing `HTTPSFTP` makes the reader
  guess whether it means `HttpsFtp` or `HttpSftp`.
- **Two letters, both capitalised in English** (`ID`, `TV`, `UI`, `OK`): keep both caps
  inside an identifier: `UIConfig`, `userID`. Two letters **not** capitalised in
  English (`Mr`, `St`, `Rd`) are capitalised like a word.
- **At the start of a lowerCamel identifier**, any abbreviation is all lowercase:
  `httpConnection`, `idToken`, `uiState`, `tvSet`.
- *Practical note:* many Flutter codebases and JSON APIs use `userId`. Effective
  Dart says `userID`. In existing code, follow the codebase and don't flag
  this as a defect. In a new codebase, pick one and be consistent.
- **iOS** (Flutter guide): avoid it in identifiers where possible (use
  `Cupertino`, `UIKit`). If you can't, write `IOS` (`IOSDeviceInfo`), never `Ios`.

## 2. Underscores, prefixes, wildcards

- **A leading `_` means library-private**, and nothing else. Never put it on locals,
  parameters, local functions or import prefixes. There is no "private" for
  those, and the underscore misleads the reader. (Lints:
  `no_leading_underscores_for_local_identifiers`,
  `no_leading_underscores_for_library_prefixes`)
- **Don't use prefix letters.** Avoid Hungarian notation (`strName`, `iCount`), `m`
  for members (`mValue`), and `k` for constants (`kDefaultPadding`). Dart already
  tells you the type, scope and constness.
  *Exception:* Flutter framework code, and apps that already use `kFoo`
  throughout, keep their convention. Don't introduce it into a codebase that
  doesn't have it. Flutter itself prefers `Button.defaultColor`, or an
  `abstract final class` that groups related constants, over globals.
- **No `I` prefix for interfaces** (`IUserRepository`). Every Dart class is an
  implicit interface. Name the abstraction for its role (`UserRepository`) and
  the implementation for how it does it (`RemoteUserRepository`,
  `FakeUserRepository`). Prefer a descriptive word over `Impl`. *Exception:*
  architectures that prescribe `XRepositoryImpl` (Clean Architecture, MVN)
  are following a convention, so `Impl` is consistent there and not a finding.
- **Wildcards (Dart ≥3.7).** In *anonymous, local* callbacks, name unused params `_`.
  It can be repeated: `(_, _) => …`. Declared functions and methods still name
  every parameter, because readers need to know what each one is. Before 3.7,
  use `_`, `__`, `___`. (Lints: `no_wildcard_variable_uses`, `unnecessary_underscores`)
- Don't explicitly name libraries (`library foo;` → `library;`, or omit it).

## 3. Choosing the words (Effective Dart *Design → Names*)

- **DO use terms consistently.** Use one word for one concept across the whole
  API. If it's `fetch` in one repository, it's `fetch` in all of them, not
  `get`/`load`/`retrieve`/`fetch` mixed. Prefer the term the platform already
  uses: `length` not `size`/`count` for collections (Dart's `Iterable` uses
  `length`), and `add` not `push`.
- **AVOID abbreviations** unless the abbreviation is more common than the full
  word (`http`, `json`, `url`, `id`, `db` are fine). Write `pageCount`, not `pgCnt`,
  and `buttonColor`, not `btnClr`. One-letter names are fine only where they are
  idiomatic: `i` as a loop index, `x`/`y` as coordinates, `e` as a caught error in
  a tiny block.
- **PREFER putting the most descriptive noun last.** `pageCount` is a count of pages.
  `numPages` reads as if it were a collection of pages. Likewise `ConversionSink`,
  `CssFontFaceRule`.
- **CONSIDER making the code read like a sentence.** `if (errors.isEmpty)`,
  `subscription.cancel()`, `monsters.where((monster) => monster.hasClaws)`. Don't
  overdo it, though: `theCollectionOfErrors` and
  `producesANewSequenceWhereEach` are noise.
- **PREFER a noun phrase for a non-boolean property or variable**: `list.length`,
  `context.lineWidth`, `quest.rampagingSwampBeast`. Don't use `list.deleteItems`.

## 4. Booleans

- **PREFER a non-imperative verb phrase** for bool properties and variables. Its
  usual forms are:
  - a form of *to be*: `isEnabled`, `wasShown`, `willFire`
  - an auxiliary verb: `hasElements`, `canClose`, `shouldConsume`, `mustSave`
  - an active verb: `ignoresInput`, `wroteFile`

  Don't use imperative forms (`empty`, `close`, `showPopup`), because they
  read as commands.
- **CONSIDER omitting the verb for a named bool *parameter***:
  `Isolate.spawn(entry, msg, paused: false)`, `List.from(x, growable: true)`,
  `Widget(enabled: true)`. Note it's `enabled`, not `isEnabled`, at the call site.
- **PREFER the positive name.** Use `isConnected` rather than `isDisconnected`,
  and `enabled`/`visible` even when the default is `true` (Flutter: "avoid double
  negatives"). `if (!socket.isDisconnected)` makes the reader stop and work it out.
  Exception: when the negative is the overwhelmingly common question (`isEmpty` vs
  `isNotEmpty`), provide both.
- **AVOID positional boolean parameters.** `Button(true)` and `task.run(false)`
  tell the reader nothing. Make them named (`Button(enabled: true)`). Setters
  are fine (`listBox.canScroll = true`), as are params whose meaning is obvious
  from the method name (`setEnabled(true)`). (Lint:
  `avoid_positional_boolean_parameters`)

## 5. Methods and functions

| The member's main purpose | Name it | Examples |
|---|---|---|
| Side effect (changes state, does I/O) | **Imperative verb phrase** | `list.add()`, `queue.removeFirst()`, `window.refresh()`, `repository.save(user)` |
| Returning a value, cheaply, with no side effects | **Getter** with a noun phrase | `list.length`, `user.fullName`, `cart.isEmpty` |
| Returning a value (method, has args or is non-trivial) | **Noun phrase or non-imperative verb phrase** | `list.elementAt(3)`, `string.codeUnitAt(4)`, `list.firstWhere(test)` |
| Returning a value, but you want to stress the work involved | **Imperative verb** naming the work | `fetchUser()`, `downloadFile()`, `calculateTax()`, `parseConfig()` |
| Copying state into a new object | `to___()` | `toList()`, `toJson()`, `toUpperCase()`, `toEntity()` |
| A different view backed by the same object | `as___()` | `asMap()`, `asBroadcastStream()`, `asUnmodifiableView()` |

- **AVOID starting a method name with `get`.** `getBreakfastOrder()` should be a
  getter `breakfastOrder` if it is cheap and has no args. If it is expensive,
  async or has side effects, name the work: `fetchBreakfastOrder()`,
  `calculateBreakfastOrder()`. (`getX` is fine where it mirrors a platform API
  you are wrapping, such as `SharedPreferences.getString`.)
- **Getters vs methods.** Use a getter when the operation takes no args, returns a
  result, the caller cares only about the result, has no user-visible side
  effects, is idempotent, and is fast. A user reasonably assumes
  `obj.foo` is cheap. Use a setter only when there is a matching getter
  (`avoid_setters_without_getters`), and use setters (not `setFoo()` methods) to
  change properties (`use_setters_to_change_properties`).
- **AVOID describing the parameters in the name.** Write `list.add(element)`, not
  `list.addElement(element)`, and `region.containsPoint(point)` only if there is
  also `containsRegion`.
- **No `Async` suffix.** `Future<User> fetchUser()` already says it is async. In
  Dart, `fetchUserAsync` is the C# habit showing through.
- **`dispose` / `close` / `cancel`**: `dispose()` ends an object's life (Flutter
  convention), `close()` ends a sink/stream/connection, and `cancel()` stops a
  subscription/timer/operation.

## 6. Type parameters

Follow the existing mnemonics, and use full words when no mnemonic fits.

| Name | Meaning | Example |
|---|---|---|
| `E` | element of a collection | `class IterableBase<E>` |
| `K`, `V` | key and value | `class Map<K, V>` |
| `R` | return type | `R Function<R>()`, `Future<R> run<R>()` |
| `T`, `S`, `U` | a single generic type, then the next ones | `class Future<T>`, `Future<S> then<S>(...)` |
| Descriptive | anything else | `class Graph<Node, Edge>`, `class Repository<Entity, Id>` |

## 7. Flutter-specific naming

- **Callbacks.** Name the typedef `FooCallback` (`typedef ItemSelectedCallback =
  void Function(Item item);`), the property or argument `onFoo` (`onTap`,
  `onItemSelected`), and the method that handles it `_handleFoo` (`_handleTap`).
  Use the present tense: `onTap`, not `onTapped`, and `onChange`/`onChanged`
  following the SDK. **Never name a method `onFoo`.** If something is called
  `onFoo`, it must be a function-typed property. When you ignore a callback's
  arguments in framework-style code, name them anyway, so that copy-pasted code
  stays readable. (In app code, the wildcard rule in §2 is fine.)
- **Widgets** are nouns describing what they show: `UserAvatar`, `OrderSummaryCard`,
  `EmptyCartView`. A private sub-widget is `_Header`, not a `_buildHeader()` method
  (see the `flutter-ui-practices` skill, `../flutter-ui-practices/references/flutter-ui.md` §3). `State` classes are `_FooState` for `Foo`.
- **Debug-only members** get a `debug`/`_debug` prefix (`debugLabel`,
  `_debugAssertValid`) and must not be used in production paths.
- **Avoid "new/old/v2"** in names (`NewCheckoutScreen`, `oldApi`). "New" stops being
  new. Name the idea instead (`ExpressCheckoutScreen`, `legacyPaymentsApi` only if
  it's genuinely the legacy one).
- **Setter argument** is named `value` (Flutter guide) unless that causes a conflict.
- **Spelling**: use US English to match the SDK (`color`, `canceled`, `initialize`),
  and no cute spellings (`klass` → `classIdentifier`). Words that are one word in
  the dictionary get no inner capital: `toolbar`, `scrollbar`, `offstage`. Two-word
  ones do: `appBar`, `tabBar`.

## 8. Files, directories, architecture roles

- **File = its main declaration in snake_case**: `UserRepository` →
  `user_repository.dart`, `HomeViewModel` → `home_view_model.dart`. Prefer one
  main public class per file, although Effective Dart allows several closely
  related classes in one library.
- **No suffix-only files** like `utils.dart`, `helpers.dart`, `common.dart`,
  `misc.dart`. Name the file after what is in it (`date_formatting.dart`,
  `retry_policy.dart`).
- **Name classes for the architectural role they play** (Flutter architecture
  recommendations): `HomeScreen`, `HomeViewModel`, `UserRepository`,
  `ClientApiService`. Don't pick names that collide with Flutter SDK concepts.
  The guide's example: put shared widgets in `ui/core/`, not a folder called
  `widgets/`. Don't call your class `State`, `Element`, `Widget`, `Router`,
  `Navigator`, `Theme` or `Material*`.
- **Match the project's role vocabulary.** If the project uses `Notifier`/`State`
  (Riverpod / MVN), `Bloc`/`Cubit`, or `ViewModel`, use it. Don't introduce a second
  vocabulary for the same role. §12 lists the role names of each common
  architecture. For MVN projects, the `mvn` skill (if installed) is the
  canonical source for the exact suffixes and folders.
- **Test files** mirror the source path, with `_test.dart`:
  `lib/data/user_repository.dart` → `test/data/user_repository_test.dart`.
  Fakes are `FakeUserRepository`, mocks are `MockUserRepository`.

## 9. General principles (language-agnostic)

These come from long-standing practice (Clean Code, Code Complete, API design
literature) and agree with Effective Dart.

1. **Reveal intent.** A name should answer why it exists, what it does, and how
   it's used. If it needs a comment to explain it, rename it:
   `final d = 86400;` becomes `const secondsPerDay = 86400;`, or better,
   `const Duration(days: 1)`.
2. **Make length proportional to scope.** A loop index can be `i`. A field read
   across a feature deserves `selectedPaymentMethod`. A public package API deserves
   the most care of all.
3. **Use types instead of encoding units.** Use `Duration timeout`, not
   `int timeoutMs`, and `DateTime`, not `int epochMillis`. If a primitive is unavoidable
   (JSON, FFI), put the unit in the name: `timeoutMillis`, `sizeBytes`.
4. **Avoid noise words that add no meaning**: `Manager`, `Helper`, `Util(s)`,
   `Processor`, `Data`, `Info`, `Object`, `Base` (when it isn't actually an
   abstract base), and `Impl` (unless the architecture prescribes it, see §2). `UserInfo` vs `UserData` vs `User` is a distinction nobody
   can remember. In Dart, a `FooUtils` class of statics is also an Effective Dart
   violation (`avoid_classes_with_only_static_members`). Use top-level
   functions, or an extension on the type being operated on.
5. **Make names distinct.** Don't keep `user`, `user2`, `theUser` and `userObj`
   in one scope. Don't use names that differ by one letter or only by case.
6. **Don't use misleading names.** Don't call a `Set` `userList`, and don't name
   a function `validate` if it also saves. If the behaviour changes, the name
   changes.
7. **Pluralise collections; name maps by the lookup.** Use `users`, `selectedIds`,
   and `usersById` / `priceBySku` for maps (the value comes before the key).
8. **Pair names symmetrically**: `open`/`close`, `start`/`stop`, `begin`/`end`,
   `add`/`remove`, `show`/`hide`, `enable`/`disable`, `min`/`max`,
   `first`/`last`, `source`/`destination`. Don't pair `start` with `end` or
   `open` with `destroy`.
9. **Use the domain's vocabulary.** If the business says "subscriber" and
   "line", don't write `customer` and `account`. Ubiquitous language keeps code,
   tickets and conversations aligned.
10. **Name enums and sealed types in the singular**: `PaymentMethod.card`, not
    `PaymentMethods.card`. A value is *one* payment method.
11. **Use pronounceable, searchable names.** `genymdhms` can't be said in a
    review, and `7` can't be grepped. `const maxRetries = 7` can.

## 10. Renaming existing code safely

- **Private or app-internal**: use the IDE/analyzer rename (it updates every
  reference), then run `dart analyze`.
- **Public API of a published package**: renaming breaks callers. Add the new name,
  keep the old one as a forwarding `@Deprecated('Use newName instead.')` member for at
  least one minor version, and note it in `CHANGELOG.md`. The `@Deprecated`
  message is required (`provide_deprecation_message`).
- **Serialised names** (JSON keys, `@JsonKey`, Firestore fields, route paths,
  shared-prefs keys, analytics event names) are wire contracts. Rename the Dart
  identifier, keep the wire name (`@JsonKey(name: 'user_id') final String userID;`),
  and flag any wire-level change as a migration.
- In a diff review, don't ask for renames of code the diff didn't touch unless
  the name is actively misleading.

## 11. Review checklist

- [ ] Casing matches §1 (the analyzer catches this if the lints are on).
- [ ] No leading `_` on locals or params, no Hungarian/`k`/`m`/`I` prefixes (unless the project uses them).
- [ ] Booleans are positive, non-imperative verb phrases. Named bool params have no verb. No positional bools.
- [ ] Side-effect methods use imperative verbs. Value methods use nouns. No `getX()` that should be a getter or `fetchX()`.
- [ ] `toX` copies, `asX` views.
- [ ] Callbacks are `onFoo` (property), `_handleFoo` (method), `FooCallback` (typedef).
- [ ] One term per concept across the feature (fetch/load/get not mixed).
- [ ] No noise words (`Manager`, `Helper`, `Util`, `Data`, `Info`) where a precise word exists. `Impl` is fine where the architecture prescribes it.
- [ ] File names match their main class. No `utils.dart` grab-bags.
- [ ] Units live in types (`Duration`), not names, unless primitives are forced.
- [ ] Role suffixes match the project's architecture vocabulary (§12), with one vocabulary per role.

## 12. Role naming per architecture

Every architecture comes with a vocabulary: which word means "the object that
holds screen logic", what a state or an event is called, where files live. The
vocabulary is a contract between the people on the project, so the first rule
is the precedence rule: **the project's consistent conventions win, then the
pattern's canonical source, then this section.** Use the table at the end to
spot a project that mixes two vocabularies for one role, which is the naming
problem that actually costs teams time.

Files follow the class they hold (§8): `MovieNotifier` → `movie_notifier.dart`.
`X` below stands for the feature or subject (`Movie`, `Login`, `Cart`).

### 12.1 MVN (Model-View-Notifier, Riverpod codegen)

Canonical source: the `mvn` spec by its author (the `mvn` skill, if installed).
The tree is fixed, and its presentation folders are **singular**:

```
features/<x>/domain/entities/<x>_entity.dart            XEntity (immutable)
features/<x>/domain/repositories/<x>_repository.dart    abstract interface class XRepository
features/<x>/domain/usecases/<x>_usecase.dart           FetchTrendingMovies (one intent, call())
features/<x>/data/models/<x>_request.dart               XRequest  (outbound DTO, toJson)
features/<x>/data/models/<x>_response.dart              XResponse (inbound DTO, fromJson, toEntity())
features/<x>/data/repositories/<x>_repository_impl.dart XRepositoryImpl implements XRepository
features/<x>/data/sources/<x>_source.dart               XSource (contract) + XRemoteSource
features/<x>/presentation/notifier/<x>_notifier.dart    XNotifier extends _$XNotifier
features/<x>/presentation/state/<x>_state.dart          sealed XState
features/<x>/presentation/view/<x>_view.dart            XView (ConsumerWidget)
features/<x>/presentation/widget/<x>_widget.dart        sub-widgets, renamed descriptively (movie_list.dart)
```

- **The bridge is `XNotifier`, never `XViewModel`, `XController` or `XVM`.**
  There's no `controller(s)/` or `view_model(s)/` folder. The only "Controller"
  allowed is a Flutter controller (`AnimationController`, `TextEditingController`)
  held as a field. (`ARCH-112` in the `flutter-architecture` skill checks this.)
- **State variants** are `XInitial`, `XLoading`, `XSuccess`, `XError`, all
  `final class … extends XState`. Note that MVN says `Error`/`Loading` where
  Bloc says `Failure`/`InProgress`; don't "correct" one to the other.
- **Use cases are named for one intent** as a verb phrase: `FetchTrendingMovies`,
  `SubmitOrder`, with a single `call()`. The file keeps the seeded name
  `<x>_usecase.dart`. The provider is the lowerCamel form of the class
  (`fetchTrendingMoviesProvider`).
- **`Impl` is prescribed here** (`XRepositoryImpl`), so it's not a noise-word finding (§2).
- Notifier methods are imperative verbs for the action (`loadTrending()`, `retry()`).

### 12.2 MVVM (Flutter architecture guide, Compass sample app)

Canonical source: docs.flutter.dev/app-architecture and its case study.

```
lib/ui/core/                                    shared widgets and themes (not lib/widgets/)
lib/ui/<x>/view_models/<x>_viewmodel.dart       XViewModel extends ChangeNotifier
lib/ui/<x>/widgets/<x>_screen.dart              XScreen (a full-screen view)
lib/data/repositories/<x>/<x>_repository.dart   abstract class XRepository
lib/data/repositories/<x>/<x>_repository_remote.dart   XRepositoryRemote
lib/data/repositories/<x>/<x>_repository_local.dart    XRepositoryLocal
lib/data/services/api/api_client.dart           ApiClient, AuthApiClient
lib/data/services/shared_preferences_service.dart      SharedPreferencesService
lib/domain/models/<x>.dart                      Booking, BookingSummary (plain nouns)
lib/domain/use_cases/                           optional (Conditional in the guide)
```

- **Views** are `XScreen` for a whole screen and `XView` (or a plain noun,
  `LogoutButton`) for a smaller view with its own view model (`LogoutViewModel`).
  One view, one view model.
- **Repository implementations are named for how they work**, with the qualifier
  after the role: `BookingRepositoryRemote`, `BookingRepositoryLocal`, plus
  fakes in tests (`FakeBookingRepository`). The abstract class takes the plain
  role name.
- **Services** are named for the source they wrap: `XApiClient`, `XService`
  (`SharedPreferencesService`, `LocalDataService`). One service per data source.
- **Commands** are view-model fields named for the user action:
  `late final Command0<void> load;`, `late final Command1<void, int> deleteBooking;`,
  backed by private methods `_load`, `_deleteBooking`. The UI calls
  `viewModel.deleteBooking.execute(id)`. Don't add a `Command` suffix to the field.
- The guide's file naming is `<x>_viewmodel.dart`. `<x>_view_model.dart` is
  equally valid snake_case; pick one per project.

### 12.3 Bloc and Cubit (bloclibrary.dev)

Canonical source: bloclibrary.dev *Naming Conventions*. The bloc docs call them
recommendations, so a project's own consistent scheme wins.

**Events are past tense**, because from the bloc's point of view they have
already happened. The anatomy is `BlocSubject + Noun (optional) + Verb (past)`:

| Good | Bad (and why) |
|---|---|
| `CounterStarted` (the initial-load event is always `XStarted`) | `CounterInitialized`, `Initial` (not a past-tense occurrence; no subject) |
| `CounterIncrementPressed`, `CounterDecrementPressed` | `Increment`, `DoIncrement`, `IncrementCounter` (commands, not events) |
| `CounterIncrementRetried`, `TodoDeleted`, `LoginSubmitted` | `LoadTodos`, `SubmitLogin` (imperative: name what happened, not what to do) |

The base event class is `XEvent` (`sealed class CounterEvent {}`).

**States are nouns**, a snapshot at a point in time. Two styles:

- **Subclasses:** `BlocSubject + Verb (action, optional) + Initial | InProgress | Success | Failure`,
  extending the base `XState`: `TodoInitial`, `TodoLoadInProgress`,
  `TodoLoadSuccess`, `TodoLoadFailure` (or `TodoInProgress`/`TodoSuccess`/
  `TodoFailure` when there's one action). The initial state is always `XInitial`.
- **Single class:** one `XState` with an `XStatus` enum,
  `enum TodoStatus { initial, loading, success, failure }`, plus the data fields.

Bad: bare `Initial`, `Loading`, `Success`, `Succeeded`, `Loaded`, `Failure`, `Failed`
(no subject, so they collide across blocs and read as verbs).

- **Files**: `bloc/x_bloc.dart` with `part 'x_event.dart';` and `part 'x_state.dart';`.
  A cubit is `cubit/x_cubit.dart` plus `x_state.dart`. The bloc tutorials split
  the screen into `XPage` (provides the bloc) and `XView` (renders it).
- **Cubit** is `XCubit` with state `XState`. Cubit methods are **imperative
  verbs** (`increment()`, `fetchWeather()`), because calling a method is a
  command. Only bloc *events* are past tense.
- **Event handlers** inside a bloc are registered as
  `on<CounterIncrementPressed>(_onIncrementPressed)`. A private `_onX` handler is
  the bloc convention, so don't flag it against the Flutter `_handleFoo` rule (§7).
- **Data layer:** a *data provider* returns raw data and is named for its source
  (`OpenMeteoApiClient`, `LocalStorageTodosApi`), and a *repository* wraps one or
  more providers and is named for the domain (`WeatherRepository`,
  `TodosRepository`). An abstract provider takes the role name (`TodosApi`) and
  implementations say how (`LocalStorageTodosApi`).

### 12.4 Clean Architecture (generic)

There is no single canonical source, so consistency across the project is the
whole game. Common, defensible choices:

| Role | Layer / folder | Naming |
|---|---|---|
| Entity | `domain/entities/` | Plain noun (`User`) or `UserEntity`. Use the suffix when a DTO would otherwise share the name |
| Use case | `domain/usecases/` | **Verb phrase** for one intent: `SignInWithEmail`, `FetchUserProfile`, optionally suffixed `UseCase` (`SignInUseCase`). Parameters: `SignInParams` |
| Repository contract | `domain/repositories/` | `UserRepository` (abstract / `abstract interface class`) |
| Repository implementation | `data/repositories/` | `UserRepositoryImpl`, or named for how it works (`UserRepositoryRemote`, `FirestoreUserRepository`) |
| Data sources | `data/datasources/` | `UserRemoteDataSource`, `UserLocalDataSource` (contracts), with implementations `…Impl` or named by technology (`UserApiDataSource`) |
| DTO / model | `data/models/` | `UserDto`, `UserModel`, or `UserRequest`/`UserResponse`. Pick one suffix per project |
| Mapper | next to the DTO | `toEntity()` / `fromEntity()` methods, an extension (`extension UserDtoMapper on UserDto`), or a `UserMapper` class |
| Errors | domain / data | Domain `Failure` types (`ServerFailure`, `CacheFailure`), data-layer exceptions (`ServerException`) |

- A use case is a class, not a method, so the `get` rule in §5 doesn't strictly
  apply to `GetUserProfile`. Still, use the **same verb as the repository**
  (§3): if the repository says `fetchProfile()`, the use case is `FetchUserProfile`.
- Don't mix `UseCase`-suffixed and bare use-case names in one project.

### 12.5 MVC

`XModel` holds data and business rules, `XView` (or `XPage`) is the widget, and
`XController` mediates input, in `models/`, `views/` and `controllers/`. With
the `mvc_pattern` package the controller is `XController extends ControllerMVC`
and the screen's state extends `StateMVC<XPage>`.

**Why MVN bans "Controller".** In Flutter, "controller" already means an
imperative handle that a parent uses to drive a widget (`TextEditingController`,
`ScrollController`, `AnimationController`, `TabController`), with a `dispose()`
obligation. It also means different things in MVC and GetX. Reusing it for the
presentation-logic holder makes a reader guess which kind they're looking at.
MVN names the role for what it does in Riverpod: it *notifies* state. In an MVC
or GetX project, though, `XController` is the correct name and not a finding.

### 12.6 GetX

get_cli generates `lib/app/modules/<x>/{bindings,controllers,views}/`:

- `XController extends GetxController` in `x_controller.dart`
- `XBinding extends Bindings` (overriding `dependencies()`) in `x_binding.dart`
- `XView extends GetView<XController>` in `x_view.dart`
- App-wide services: `XService extends GetxService`
- Routes: `AppPages` in `routes/app_pages.dart` and `Routes` in
  `routes/app_routes.dart`. get_cli emits `Routes.HOME`. That's generated-code
  `SCREAMING_CAPS`, so leave it alone (§1).
- Observables are named for the value (`final count = 0.obs;`, `final user = Rxn<User>();`),
  not `countObs` or `rxCount`. The `Rx` type already says it's reactive (§2, no Hungarian).

### 12.7 Riverpod providers

With `riverpod_generator`, the provider name is derived from the annotated
function or class, so the name you choose for the function *is* the provider's name:

| Declaration | Generated provider |
|---|---|
| `@riverpod Future<User> currentUser(Ref ref)` | `currentUserProvider` |
| `@riverpod class TodoList extends _$TodoList` | `todoListProvider` |
| `@riverpod class TodoListNotifier extends _$TodoListNotifier` | `todoListProvider` with riverpod_generator ≥3.0 (it strips a trailing `Notifier` by default); `todoListNotifierProvider` with 2.x |
| `@riverpod Future<User> user(Ref ref, String id)` (family) | `userProvider`, used as `userProvider(id)` |

- **Name a function provider for what it provides**, as a noun:
  `currentUserProvider`, `filteredTodosProvider`, not `getUserProvider` or
  `fetchUserProvider`. Watching a provider reads like reading a getter (§5).
- **Families** are named for what one instance yields. The argument carries the
  key: `userProvider('42')`, not `usersProvider('42')` or `userByIdProvider('42')`.
- **Notifier methods** are imperative verbs (`addTodo`, `toggle`, `refresh`).
- Check the generated `.g.dart` (or the project's `build.yaml`:
  `provider_name_strip_pattern`, `provider_name_prefix`/`_suffix`,
  `provider_family_name_*`, or `@Riverpod(name: …)`) before you write a provider
  name in code or in a finding. Don't guess.
- Hand-written providers keep the `xProvider` suffix:
  `final counterProvider = NotifierProvider<Counter, int>(Counter.new);`.
  Don't put `Provider` on the *class* (`CounterProvider extends Notifier`).

### 12.8 Cross-pattern cheat sheet

| Role | MVN | MVVM (Flutter guide) | Bloc / Cubit | Clean Arch. | MVC | GetX |
|---|---|---|---|---|---|---|
| Screen logic holder | `XNotifier` | `XViewModel` | `XBloc` / `XCubit` | (any of these) | `XController` | `XController` |
| UI state | sealed `XState`: `XInitial/XLoading/XSuccess/XError` | fields on the view model | `XState`: `XInitial/XInProgress/XSuccess/XFailure`, or `XStatus` enum | (per presentation pattern) | `XModel` | `.obs` fields |
| Input | notifier methods | `Command0/1` fields | `XEvent`, past tense (`XStarted`) | | controller methods | controller methods |
| Full screen | `XView` | `XScreen` | `XPage` + `XView` | | `XView`/`XPage` | `XView` |
| Repository | `XRepository` + `XRepositoryImpl` | `XRepository` + `XRepositoryRemote/Local` | `XRepository` | `XRepository` + `XRepositoryImpl` | | `XRepository` |
| Raw data access | `XSource` | `XApiClient`, `XService` | data provider (`XApiClient`, `XApi`) | `XRemoteDataSource`/`XLocalDataSource` | | `XProvider extends GetConnect`, `XService` |
| DTO | `XRequest`/`XResponse` | `XApiModel` | (per project) | `XDto`/`XModel` | | |
| Use case | `FetchTrendingMovies` | optional | (rare) | `SignInWithEmail`/`SignInUseCase` | | |
| DI | `@riverpod` providers | `Provider`/`context.read` at the root | `RepositoryProvider`/`BlocProvider` | (any) | | `XBinding` |

Mixing columns for the same role (a `HomeViewModel` next to a `CartNotifier`
and a `ProfileController`, all holding screen logic) is a naming finding
(`NAME-role-vocabulary`), even when each name is fine on its own.
