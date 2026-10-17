# Where localization goes, per architecture

The rule is the same in every pattern, but the code isn't:

- **Logic decides *what* to say.** Notifiers, view models, blocs and
  controllers hold keys, enums and typed failures, never translated strings.
- **The view says it in the user's language.** Widgets translate with the
  `BuildContext` they already have, so the text follows a locale change on
  the next build.
- **Locale state** (the user's choice, or "follow the device") lives in the
  pattern's logic holder. **Persistence** lives in the data layer.
- **Formatting** (dates, money) happens in the view (`formatting.md` §6).

Why it matters. A string built in logic is frozen at the locale it was
built in, so switching to Arabic leaves old English text on screen. It also
drags `BuildContext` or a global lookup into logic (ARCH-102, I18N-015), and
it makes the logic hard to test without a widget tree.

Detect the pattern first with the `flutter-architecture` skill (if your agent
doesn't auto-load skills, read `../flutter-architecture/SKILL.md`). Judge each
app by its own pattern's rules. Names below follow the pattern's own
conventions. Match the project's naming if it differs.

## Contents

1. Shared pieces: failure messages, the l10n extension, Accept-Language
2. MVN (Riverpod codegen, Clean Architecture)
3. MVVM (Flutter architecture guide)
4. Bloc / Cubit
5. Provider (ChangeNotifier)
6. GetX
7. Plain Riverpod and setState
8. Text outside the widget tree (notifications, widgets, isolates)

---

## 1. Shared pieces

**Failure → message, in presentation.** Typed failures come up from the
repository (see the `flutter-error-handling` skill, or
`../flutter-error-handling/SKILL.md`), and one extension in the presentation
layer turns them into text:

```dart
// presentation/l10n/failure_messages.dart (per feature, or in core/presentation)
extension CartFailureMessage on CartFailure {
  String message(AppLocalizations l10n) => switch (this) {
        CartFailure.network => l10n.errorNetwork,
        CartFailure.outOfStock => l10n.errorOutOfStock,
        CartFailure.unknown => l10n.errorUnknown,
      };
}
```

An exhaustive `switch` means a new failure can't ship without a message.
Never show `e.toString()` (ERR-008).

**One `context.l10n` extension** (`gen-l10n-and-arb.md` §8), so widgets don't
repeat `AppLocalizations.of(context)`.

**Accept-Language, in the data layer.** When the server localizes content
(product names, notifications), the data layer sends the language. It reads
the *persisted* choice or the device locale, never a `BuildContext` or a
presentation notifier:

```dart
// data/network/accept_language_interceptor.dart
final class AcceptLanguageInterceptor extends Interceptor {
  AcceptLanguageInterceptor(this._languageTag);
  final String Function() _languageTag;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['Accept-Language'] = _languageTag();
    handler.next(options);
  }
}

// wiring: the saved choice, else the device
AcceptLanguageInterceptor(
  () => localeSource.readLanguageTag() ?? PlatformDispatcher.instance.locale.toLanguageTag(),
);
```

## 2. MVN (Riverpod codegen, Clean Architecture)

The flow is View → Notifier → UseCase → Repository → Source, and sources
never read UI state (`../flutter-architecture/references/mvn.md`). The domain
doesn't import Flutter, so it models the language as its own enum and the
notifier maps it to a `Locale`.

```dart
// features/settings/domain/entities/app_language.dart
enum AppLanguage { en, ar }

// features/settings/domain/repositories/language_repository.dart
abstract interface class LanguageRepository {
  AppLanguage? saved();                      // null = follow the device
  Future<void> save(AppLanguage? language);
}

// features/settings/data/sources/language_local_source.dart
final class LanguageLocalSource {
  const LanguageLocalSource(this._prefs);
  final SharedPreferences _prefs;
  static const _key = 'app_language';

  String? read() => _prefs.getString(_key);
  Future<void> write(String? code) async =>
      code == null ? await _prefs.remove(_key) : await _prefs.setString(_key, code);
}

// features/settings/data/repositories/language_repository_impl.dart
final class LanguageRepositoryImpl implements LanguageRepository {
  const LanguageRepositoryImpl(this._source);
  final LanguageLocalSource _source;

  @override
  AppLanguage? saved() => AppLanguage.values.asNameMap()[_source.read()];

  @override
  Future<void> save(AppLanguage? language) => _source.write(language?.name);
}

@riverpod
LanguageRepository languageRepository(Ref ref) =>
    LanguageRepositoryImpl(LanguageLocalSource(ref.watch(sharedPreferencesProvider)));
```

```dart
// features/settings/domain/usecases/language_usecases.dart (use cases + their providers: the DI seam)
final class GetSavedLanguage {
  const GetSavedLanguage(this._repository);
  final LanguageRepository _repository;
  AppLanguage? call() => _repository.saved();
}

final class SaveLanguage {
  const SaveLanguage(this._repository);
  final LanguageRepository _repository;
  Future<void> call(AppLanguage? language) => _repository.save(language);
}

@riverpod
GetSavedLanguage getSavedLanguage(Ref ref) => GetSavedLanguage(ref.watch(languageRepositoryProvider));

@riverpod
SaveLanguage saveLanguage(Ref ref) => SaveLanguage(ref.watch(languageRepositoryProvider));
```

```dart
// features/settings/presentation/notifier/locale_notifier.dart
@Riverpod(keepAlive: true)
class LocaleNotifier extends _$LocaleNotifier {
  @override
  Locale? build() => _toLocale(ref.watch(getSavedLanguageProvider)());

  Future<void> select(AppLanguage? language) async {
    await ref.read(saveLanguageProvider)(language);
    state = _toLocale(language);
  }

  static Locale? _toLocale(AppLanguage? l) => l == null ? null : Locale(l.name);
}
```

```dart
// main.dart: SharedPreferences is read once, so the first frame already has the locale
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  runApp(ProviderScope(
    overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
    child: const App(),
  ));
}

class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp(
        locale: ref.watch(localeProvider), // riverpod_generator 3 name; 2.x: localeNotifierProvider
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const HomeView(),
      );
}
```

Feature state stays typed, and the view translates in its exhaustive
`switch`:

```dart
sealed class CartState { const CartState(); }
final class CartEmpty extends CartState { const CartEmpty(); }
final class CartError extends CartState {
  const CartError(this.failure);
  final CartFailure failure;     // not `String message`
}

// view
final l10n = context.l10n;
return switch (ref.watch(cartProvider)) {
  CartEmpty() => Text(l10n.cartEmptyTitle),
  CartError(:final failure) => Text(failure.message(l10n)),
  // ...
};
```

One-time messages (a "saved" snackbar) go through `ref.listen` in the view,
which has the context: `ref.listen(cartProvider, (_, next) { if (next is
CartSaved) showSnackBar(context.l10n.cartSaved); })`.

## 3. MVVM (Flutter architecture guide)

App-wide state lives in a repository that many view models share
(`../flutter-architecture/references/mvvm.md`). The language choice is
exactly that.

```dart
// data/repositories/language_repository.dart
abstract class LanguageRepository extends ChangeNotifier {
  String? get languageCode;                          // null = follow the device
  Future<Result<void>> setLanguageCode(String? code);
}

// data/repositories/language_repository_local.dart
class LanguageRepositoryLocal extends LanguageRepository {
  LanguageRepositoryLocal({required SharedPreferencesService prefs}) : _prefs = prefs;
  final SharedPreferencesService _prefs;
  String? _code;

  @override
  String? get languageCode => _code;

  Future<void> load() async => _code = await _prefs.read('app_language');

  @override
  Future<Result<void>> setLanguageCode(String? code) async {
    final result = await _prefs.write('app_language', code);
    if (result is Ok<void>) {
      _code = code;
      notifyListeners();
    }
    return result;
  }
}
```

```dart
// ui/settings/view_models/language_view_model.dart
class LanguageViewModel extends ChangeNotifier {
  LanguageViewModel({required LanguageRepository repository}) : _repository = repository {
    select = Command1<void, String?>(_repository.setLanguageCode);
  }

  final LanguageRepository _repository;
  late final Command1<void, String?> select;

  String? get selected => _repository.languageCode;
}
```

```dart
// main.dart (DI with package:provider, as in the Compass app)
ListenableBuilder(
  listenable: context.read<LanguageRepository>(),
  builder: (context, _) {
    final code = context.read<LanguageRepository>().languageCode;
    return MaterialApp.router(
      locale: code == null ? null : Locale(code),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      routerConfig: router,
    );
  },
);
```

Feature view models expose typed state, and a command's error is a typed
exception. The view maps both to text, for example in the listener that
shows the snackbar: `if (vm.save.error) showSnackBar(context.l10n.saveFailed);`
followed by `vm.save.clearResult()`.

## 4. Bloc / Cubit

```dart
// settings/cubit/locale_cubit.dart
class LocaleCubit extends Cubit<Locale?> {
  LocaleCubit(this._repository) : super(_repository.savedLocale());
  final LanguageRepository _repository;

  Future<void> select(Locale? locale) async {
    await _repository.save(locale?.languageCode);
    emit(locale);
  }
}

// app.dart
BlocBuilder<LocaleCubit, Locale?>(
  builder: (context, locale) => MaterialApp(
    locale: locale,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: const HomePage(),
  ),
);
```

`HydratedCubit` is the idiomatic alternative when the app already uses
`hydrated_bloc`: `fromJson`/`toJson` replace the repository call.

Feature blocs emit a status enum or a typed failure
(`CartState(status: CartStatus.failure, failure: CartFailure.network)`).
Translate in `BlocBuilder` and show one-time messages in `BlocListener`
(`../flutter-architecture/references/bloc.md` §5):

```dart
BlocListener<CartBloc, CartState>(
  listenWhen: (prev, next) => next.status == CartStatus.failure && prev.status != next.status,
  listener: (context, state) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(state.failure!.message(context.l10n)))),
  child: const CartBody(),
);
```

Blocs never take a `BuildContext` to look up strings, and an event never
carries translated text.

## 5. Provider (ChangeNotifier)

```dart
class LocaleModel extends ChangeNotifier {
  LocaleModel(this._store) : _locale = _store.read();
  final LocaleStore _store;   // data layer, wraps SharedPreferences
  Locale? _locale;

  Locale? get locale => _locale;

  Future<void> select(Locale? locale) async {
    _locale = locale;
    notifyListeners();
    await _store.write(locale);
  }
}

// root
ChangeNotifierProvider(
  create: (_) => LocaleModel(store),
  child: Builder(
    builder: (context) => MaterialApp(
      locale: context.watch<LocaleModel>().locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const HomeScreen(),
    ),
  ),
);
```

Feature models hold typed fields (`CartFailure? failure`), and `Consumer` or
`build()` translates them.

## 6. GetX

GetX has its own translation system, and it's context-free: `'key'.tr`
re-reads `Get.locale` when it runs. Respect the idiom, and keep two rules:

- **Store keys, translate in the view.** `message.value = 'saved'.tr` in a
  controller freezes the text at the current locale. Store `'saved'`, and
  render `Obx(() => Text(controller.messageKey.value.tr))`. The checker
  grades `.tr` in a controller `low` under the getx profile (I18N-015).
- **GetMaterialApp still needs Flutter's delegates.** GetX translations don't
  set `Directionality`. Without `GlobalWidgetsLocalizations`, Arabic renders
  LTR and Material widgets (date pickers, text selection menus) stay English
  (I18N-016).

```dart
GetMaterialApp(
  translations: AppTranslations(),
  locale: localeStorage.read() ?? Get.deviceLocale,
  fallbackLocale: const Locale('en'),
  localizationsDelegates: const [
    ...GlobalMaterialLocalizations.delegates,       // Material + Widgets (direction)
    GlobalCupertinoLocalizations.delegate,
  ],
  supportedLocales: const [Locale('en'), Locale('ar')],
  home: const HomeView(),
);

class LocaleController extends GetxController {
  LocaleController(this._storage);
  final LocaleStorage _storage;   // GetStorage or SharedPreferences behind a small service

  Future<void> select(Locale locale) async {
    await _storage.write(locale.languageCode);
    await Get.updateLocale(locale);
  }
}
```

**Arabic plurals in GetX.** `trPlural` only picks between singular and
plural, which is wrong for Arabic (I18N-plural-by-hand). Keep one key per
CLDR category and let intl choose:

```dart
// in the view (or a view helper), not the controller
String itemsLabel(int count) {
  final n = {'count': '$count'};
  return Intl.pluralLogic(
    count,
    locale: Get.locale?.languageCode ?? 'en',
    zero: 'items_zero'.tr,
    one: 'items_one'.tr,
    two: 'items_two'.tr,
    few: 'items_few'.trParams(n),
    many: 'items_many'.trParams(n),
    other: 'items_other'.trParams(n),
  );
}
```

`Get.snackbar('Saved', 'Your changes were saved')` with literals is a
hardcoded string like any other (I18N-010). Use
`Get.snackbar('saved_title'.tr, 'saved_body'.tr)`.

## 7. Plain Riverpod and setState

- **Plain Riverpod** (no MVN layering): the same `LocaleNotifier`, but it may
  read a repository provider directly. Feature providers keep `AsyncValue`
  with typed errors, and the widget's `switch` translates `AsyncError`'s
  error with the failure extension.
- **setState apps**: keep the locale in a `ValueNotifier<Locale?>` created
  next to `runApp`, persisted by a small store, and rebuild `MaterialApp`
  with a `ValueListenableBuilder`. `State` fields hold typed values, and
  `build()` translates them.

## 8. Text outside the widget tree

Some text has no `BuildContext`: a local notification scheduled in the
background, a home-screen widget, a message built in an isolate. Build it at
that edge, from the saved locale, with the generated lookup:

```dart
// platform/notifications/reminder_presenter.dart
String reminderTitle(AppLanguage? saved) {
  final locale = saved == null ? PlatformDispatcher.instance.locale : Locale(saved.name);
  final l10n = lookupAppLocalizations(
    basicLocaleListResolution([locale], AppLocalizations.supportedLocales),
  );
  return l10n.reminderTitle;
}
```

`basicLocaleListResolution` (from `package:flutter/widgets.dart`) falls back
the same way `MaterialApp` does, so an unsupported device locale doesn't
throw. This is the only sanctioned non-widget lookup. Don't use it to put
strings back into notifiers or blocs (I18N-015), and don't hard-code
`Locale('en')`.
