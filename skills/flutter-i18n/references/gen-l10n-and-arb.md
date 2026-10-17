# gen-l10n, l10n.yaml and ARB files

Sources: docs.flutter.dev *Internationalizing Flutter apps* (the page
reflects Flutter 3.47, checked October 2026), the breaking-change note
*flutter generate i10n source*, and the `flutter_tools` gen-l10n source
(`localizations/gen_l10n.dart`, `message_parser.dart`), which is what decides
whether your ARB files compile. Where this file goes beyond the docs, it says
"measured" or "from the tool source".

For first-time setup step by step, use the official
`flutter-setup-localization` recipe from `flutter/agent-plugins` if it's
installed, and apply the correction in §1. This file adds the options worth
turning on, ICU details that bite, and how to keep catalogs healthy.

## Contents

1. Setup on current Flutter (and the synthetic-package correction)
2. `l10n.yaml` options worth knowing
3. ARB files: naming, keys, metadata, fallback
4. Placeholders, number and date formats
5. Plurals
6. Select: gender and variants
7. Escaping
8. Reading messages in code
9. Keeping catalogs healthy
10. Other l10n systems (intl_utils, easy_localization, slang, GetX)

---

## 1. Setup on current Flutter

```yaml
# pubspec.yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_localizations:
    sdk: flutter
  intl: any          # flutter_localizations pins the real version

flutter:
  generate: true     # required: gen-l10n refuses to run without it
```

```yaml
# l10n.yaml (project root)
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
nullable-getter: false                       # AppLocalizations.of(context) is non-null
untranslated-messages-file: build/untranslated.json
```

```dart
import 'package:my_app/l10n/app_localizations.dart'; // generated next to the ARB files

MaterialApp(
  onGenerateTitle: (context) => AppLocalizations.of(context).appTitle,
  localizationsDelegates: AppLocalizations.localizationsDelegates, // app + Material + Cupertino + Widgets
  supportedLocales: AppLocalizations.supportedLocales,
  locale: selectedLocale, // null = follow the device
  home: const HomeScreen(),
);
```

**The synthetic-package correction.** Older guides (and the official recipe
as of April 2026) write `synthetic-package: true` and
`import 'package:flutter_gen/gen_l10n/app_localizations.dart'`. Flutter 3.32
stopped generating the synthetic `package:flutter_gen` by default, and the
tool source now rejects `synthetic-package: true` outright ("Cannot enable
synthetic-package, this feature has been removed"). `synthetic-package: false`
only prints a warning that it "no longer has any effect and should be
removed". So delete the key, generate into `lib/`, and import the file from
there. The checker reports both as I18N-005.

`AppLocalizations.localizationsDelegates` already contains
`GlobalMaterialLocalizations.delegate`, `GlobalCupertinoLocalizations.delegate`
and `GlobalWidgetsLocalizations.delegate`. The last one sets the text
direction: without it, an Arabic app renders left-to-right (I18N-016). If you
list delegates by hand, keep all three.

Add the languages to the iOS project too (Xcode → Runner → Info →
Localizations). Otherwise iOS doesn't treat the app as supporting those
languages, so system-provided text and the per-app language setting stay
English.

## 2. `l10n.yaml` options worth knowing

| Option | Default | Turn it on when |
|---|---|---|
| `nullable-getter: false` | `true` | always for new apps: removes `!` at every call site |
| `untranslated-messages-file: <path>` | summary on stdout | CI: fail or warn on untranslated keys |
| `use-escaping: true` | off | you need literal `{` `}` in messages (see §7 first: it changes how `'` works) |
| `required-resource-attributes: true` | off | you want every message to have `@key` metadata (descriptions for translators) |
| `preferred-supported-locales: [ar]` | alphabetical | the default when the device language isn't supported should be Arabic, not the first alphabetical locale |
| `output-dir: lib/src/l10n` | `arb-dir` | generated code should live elsewhere |
| `output-class: L10n` | `AppLocalizations` | the project already uses a name |
| `use-named-parameters: true` | off | messages with several placeholders (`l10n.transfer(amount: a, to: b)` reads better) |
| `format: true` | off | generated code should be `dart format`ted |
| `use-deferred-loading` | off | Flutter web with many locales (only affects web) |
| `relax-syntax: true` | off | legacy catalogs with stray braces; prefer fixing the messages |

## 3. ARB files: naming, keys, metadata, fallback

- **One file per locale**: `app_en.arb`, `app_ar.arb`, `app_ar_EG.arb`. The
  locale comes from `@@locale` or the file-name suffix. Keep `@@locale` in
  every file; translation tools rely on it.
- **Keys are Dart identifiers** (they become getters): `lowerCamelCase`,
  named by meaning, not by text: `cartEmptyTitle`, not `yourCartIsEmpty`.
  When the English text changes, the key stays.
- **Metadata lives in the template only** (`@key`): a `description` for the
  translator, and for each placeholder its `type` and an `example`. Without a
  description, "Book" (noun) becomes "احجز" (verb) instead of "كتاب" (I18N-006).
- **Fallback chain** (from the tool source): a key missing in `app_ar_EG.arb`
  comes from `app_ar.arb`, then from the template. Nothing fails at build
  time, so missing keys reach users as English (I18N-001). Use
  `untranslated-messages-file` and the checker to see them.
- **Never hand-edit the generated `app_localizations*.dart`**. Regeneration
  wipes the edit (I18N-generated-edited).

```json
{
  "@@locale": "en",
  "cartEmptyTitle": "Your cart is empty",
  "@cartEmptyTitle": {"description": "Title of the empty-cart screen"},
  "greeting": "Hello {name}",
  "@greeting": {
    "description": "Greeting on the home screen",
    "placeholders": {"name": {"type": "String", "example": "Sara"}}
  }
}
```

## 4. Placeholders, number and date formats

Placeholders are `{name}`, where `name` is a valid Dart identifier. They
become positional parameters, or named ones with `use-named-parameters`.
Types are `String`, `int`, `double`, `num`, `DateTime` and `Object`. An
undeclared placeholder gets type `Object`.

Translators must copy placeholder names exactly. A translated name
(`{الاسم}`) or a typo doesn't fail cleanly. gen-l10n *adds* it as a new
parameter, which changes the method for every locale, or it stops on the
invalid identifier. A dropped placeholder silently loses the value. The
checker reports both (I18N-002).

**Numbers** (`int`, `double`, `num`) take a `format` from the `NumberFormat`
constructors: `compact`, `compactCurrency`, `compactSimpleCurrency`,
`compactLong`, `currency`, `decimalPattern`, `decimalPatternDigits`,
`decimalPercentPattern`, `percentPattern`, `scientificPattern` and
`simpleCurrency`. The currency formats, `decimalPatternDigits` and
`decimalPercentPattern` also take `optionalParameters`:

```json
"price": "Price: {amount}",
"@price": {
  "placeholders": {
    "amount": {"type": "double", "format": "simpleCurrency", "optionalParameters": {"name": "SAR", "decimalDigits": 2}}
  }
}
```

The generated code formats with the message's own locale, which is what you
want. Pass `name:` for currency: intl's `ar` defaults to EGP (formatting.md §3).

**Dates** (`DateTime`) take any `DateFormat` skeleton name (`yMd`, `yMMMd`,
`jm` …). Join skeletons with `+` (`"format": "yMMMd+jm"`), or set
`"isCustomDateFormat": "true"` and give a pattern (`"format": "EEE, d MMM"`).
Inline ICU arguments work too: `"{when, date, yMMMd}"`.

## 5. Plurals

```text
{count, plural, =0{…} =1{…} =2{…} zero{…} one{…} two{…} few{…} many{…} other{…}}
```

From the tool source:

- `other` is **required**. Everything else is optional.
- Exact matches are only `=0`, `=1` and `=2`. `=3` and above are a build error.
- `=0` and `zero` are the same argument, as are `=1` and `one`, and `=2` and
  `two` (the tool maps both spellings to the same `Intl.pluralLogic`
  parameter). Don't write both: gen-l10n keeps one and prints a warning.
- The plural placeholder must be `int` or `num`.
- intl first returns `zero`/`one`/`two` for exactly 0/1/2 when you gave them,
  then applies the locale's CLDR rule, and falls back to `other` for any
  missing category.

That last point is why Arabic needs every form. Its CLDR rule (intl
`plural_rules.dart`, measured) is: 0 → zero, 1 → one, 2 → two,
n % 100 in 3–10 → few, n % 100 in 11–99 → many, everything else (100, 101,
102, …) → other. Missing `few` and `many` gives grammatically wrong text for
almost every count a user sees (I18N-003):

```json
"itemsInCart": "{count, plural, zero{لا توجد عناصر} one{عنصر واحد} two{عنصران} few{{count} عناصر} many{{count} عنصرًا} other{{count} عنصر}}"
```

Categories the checker requires, by language (integer counts only):

| Language | Required besides `other` |
|---|---|
| ar | one, two, few, many (zero recommended) |
| he | one, two |
| ru, uk, be, pl | one, few, many |
| cs, sk, hr, sr, bs, lt | one, few |
| sl | one, two, few |
| ga | one, two, few, many |
| cy | zero, one, two, few, many |
| lv | zero, one |

English, French, Persian, Urdu and most others need only `one` (or nothing).
A template message with only `other` ("{count} items") is still wrong for 1.

## 6. Select: gender and variants

```json
"welcomeBack": "{gender, select, female{مرحبًا بعودتكِ} male{مرحبًا بعودتكَ} other{مرحبًا بعودتك}}",
"@welcomeBack": {"placeholders": {"gender": {"type": "String"}}}
```

- The selector is a `String`, and matching is case-sensitive: `"Male"` falls
  through to `other`. Pass an enum's `.name` from the view.
- `other` is required. Make it the neutral form, because the server may not
  know the user's gender (and many users won't say).
- Arabic second-person text agrees with the reader (أنتَ / أنتِ). If you
  don't have the gender, phrase it neutrally ("تم حفظ التغييرات" rather than
  "لقد حفظتَ التغييرات").
- Nest `select` inside `plural` or the other way round only when a language
  really needs both. Nested messages are hard to translate. Split them into
  two messages when you can.

## 7. Escaping

By default `{` and `}` are always syntax, and `'` is a plain character.

With `use-escaping: true`, text between single quotes is literal, and `''`
is one apostrophe:

```json
"braces": "Use '{name}' literally",
"dont": "Don''t forget"
```

Turning it on in an existing app changes every apostrophe: "Don't" now
starts a quoted section that swallows the rest of the message
(I18N-icu-escaping). Search the catalogs for `'` before you switch it on.
Arabic rarely uses `'`, but transliterated names (`Qur'an`) do.

**Untrusted text never goes into the pattern.** Placeholder values are
inserted as plain strings by the generated code, so `l10n.greeting(userName)`
is safe whatever the user typed. A pattern built at runtime is not:
`MessageFormat('Hello $name')` or `Intl.message('… $x')` parse the data as
ICU syntax (I18N-017). The same goes for translations downloaded at runtime:
validate them against the template's placeholders and render them as plain
text.

## 8. Reading messages in code

```dart
// lib/l10n/l10n_x.dart: one extension, used by every widget
extension L10nX on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}

Text(context.l10n.greeting(user.name));
```

- **In widgets only.** Logic gets keys, enums or typed failures and the view
  translates them (`placement-by-architecture.md`).
- **`lookupAppLocalizations(locale)`** (generated) works without a context.
  Use it where there is no widget tree: a notification built in a background
  isolate, a home-screen widget, a test. Pass the user's saved locale. Don't
  hard-code `Locale('en')`, and don't use it to smuggle text into a notifier
  (I18N-015).
- **`Localizations.override(context: context, locale: …, child: …)`**
  localizes one subtree differently (a receipt printed in Arabic inside an
  English UI).
- **Locale resolution:** an exact match in `supportedLocales` wins, then the
  first with the same language code, then the first entry. Order
  `supportedLocales` deliberately, or use `preferred-supported-locales`.
- **`AppLocalizations.of(context)` needs the app to be built.** Calling it in
  `main()` or before `MaterialApp` throws.

## 9. Keeping catalogs healthy

- Run the checker in CI next to `flutter gen-l10n`: I18N-001 (missing keys),
  I18N-002 (placeholders), I18N-003 (plural forms) and I18N-018 (mojibake)
  catch what gen-l10n accepts silently.
- **Mojibake** (`Ø§Ù„Ø³Ù„Ø©` instead of `السلة`) happens when a file is
  opened as Windows-1252 and saved as UTF-8. Keep ARB and Dart files UTF-8
  without a BOM, and pin it for every editor with an `.editorconfig`
  (`charset = utf-8`). The checker reports mojibake in literals and catalogs.
- **No secrets or PII.** Catalogs are uploaded to translation vendors and
  shipped readable inside the app (I18N-004, I18N-pii-in-catalog). Support
  emails and public URLs are fine. API keys, internal hosts, test accounts and
  real customer data aren't.
- **Delete dead keys** when you delete a screen. Translators keep paying for
  them, and nobody can tell which ones are live.

## 10. Other l10n systems

Keep whichever system the project uses. The checker reads all of these.

| System | Catalog | In widgets | Plurals | Watch out for |
|---|---|---|---|---|
| gen-l10n | `lib/l10n/*.arb` | `AppLocalizations.of(context).key` | ICU, full CLDR | this file |
| intl_utils (Flutter Intl plugin) | `lib/l10n/intl_*.arb` | `S.of(context).key` | ICU | `S.current` reads a global: fine in widgets, wrong in logic (I18N-015) |
| easy_localization | `<app>/assets/translations/<locale>.json` | `'key'.tr()`, `Text('key').tr()`, `plural('key', n)` | `zero one two few many other` sub-keys | needs `localizationsDelegates: context.localizationDelegates` and `supportedLocales: context.supportedLocales` |
| slang | `*.i18n.json` | `t.section.key` / `context.t` | CLDR keys | the generated global `t` follows `LocaleSettings`; still translate in widgets |
| GetX | a `Translations` subclass (`keys` map) | `'key'.tr`, `'key'.trParams({...})` | `trPlural` is singular/plural only | Arabic needs `Intl.pluralLogic` (placement-by-architecture.md §GetX); `GetMaterialApp` still needs the Flutter delegates for RTL |

The checker's catalog parity (I18N-001 to I18N-004, I18N-018) covers ARB,
easy_localization JSON and slang JSON. GetX maps live in Dart, so check them
by reading.
