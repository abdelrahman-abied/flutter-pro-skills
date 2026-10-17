# Formatting dates, numbers and currency (intl)

Sources: the intl package 0.20.x (`DateFormat`, `NumberFormat`,
`number_symbols_data.dart`, `constants.dart`), `flutter_localizations`
(`MaterialLocalizations`), and docs.flutter.dev internationalization. Facts
marked *measured* were read from the package source in October 2026.

## Contents

1. The rule: format in the view, with the current locale
2. Dates and times
3. Numbers and percentages
4. Money
5. Parsing what users type
6. Where formatting lives, per layer
7. If you set `Intl.defaultLocale`

---

## 1. The rule: format in the view, with the current locale

`DateFormat` and `NumberFormat` without a locale use `Intl.defaultLocale`,
and Flutter never sets it. *Measured:* `flutter_localizations` only passes
the locale to its own formatters. So `DateFormat.yMMMd().format(d)` prints
"Oct 16, 2026" for an Arabic user (I18N-014). Pass the locale every time:

```dart
final locale = Localizations.localeOf(context).toString();     // 'ar', 'ar_EG', 'en_US'
// or: AppLocalizations.of(context).localeName (canonicalised by gen-l10n)

Text(DateFormat.yMMMd(locale).format(order.placedAt.toLocal()));
Text(NumberFormat.decimalPattern(locale).format(order.itemCount));
```

When there are many formatters, put them behind one small helper that takes
the locale, and build it in the view:

```dart
// presentation/formatting/app_formats.dart
final class AppFormats {
  AppFormats(this.locale);
  final String locale;

  late final DateFormat day = DateFormat.yMMMd(locale);
  late final DateFormat time = DateFormat.jm(locale);
  String money(Money m) => NumberFormat.currency(locale: locale, name: m.currency).format(m.major);
}

extension AppFormatsX on BuildContext {
  AppFormats get formats => AppFormats(Localizations.localeOf(this).toString());
}
```

Inside an ARB message, prefer a typed placeholder with a `format`
(`gen-l10n-and-arb.md` §4). The generated code then formats with the
message's own locale.

## 2. Dates and times

- **Use skeletons, not patterns**, for display: `yMMMd`, `yMd`, `MMMEd`,
  `jm` (12/24 hour by locale), `Hm`. A pattern like `'MMMM d, yyyy'` fixes the
  English order for every language.
- **Material helpers** follow the app's localizations and settings:
  `MaterialLocalizations.of(context).formatMediumDate(d)`,
  `formatShortDate`, `formatTimeOfDay(t, alwaysUse24HourFormat:
  MediaQuery.alwaysUse24HourFormatOf(context))`, and `TimeOfDay.format(context)`.
- **Week start**: read `MaterialLocalizations.of(context).firstDayOfWeekIndex`
  (0 is Sunday). Many Arabic locales start on Saturday, so don't hard-code
  Monday in calendars (I18N-calendar-assumption).
- **Time zones**: store and send UTC, and convert with `toLocal()` only in
  the view.
- **Wire formats are not display formats.** For APIs, use
  `toIso8601String()` and `DateTime.parse`, and no `DateFormat` at all. If a
  backend needs a pattern, make the intent explicit with
  `DateFormat('yyyy-MM-dd', 'en')`, so a later "fix" doesn't add the user's
  locale and send Arabic-Indic digits to the server. The checker grades a
  numeric pattern without a locale `info` for this reason.
- **Outside a Flutter app** (unit tests that don't pump the delegates,
  background isolates, pure Dart), the date symbols aren't loaded. Call
  `await initializeDateFormatting('ar')` from
  `package:intl/date_symbol_data_local.dart` first, or `DateFormat` throws
  `LocaleDataException`. Inside the app, `GlobalMaterialLocalizations` loads
  them for you.
- **Relative time** ("3 minutes ago"): the `timeago` package needs the locale
  messages registered (`timeago.setLocaleMessages('ar', timeago.ArMessages())`)
  and the locale passed on every call.
- **Hijri calendar**: intl formats Gregorian only. Apps that show Hijri dates
  (prayer times, Ramadan, Saudi government services) need a Hijri package,
  and they should label which calendar a date uses. `showDatePicker` is
  Gregorian too.

## 3. Numbers and percentages

```dart
NumberFormat.decimalPattern(locale).format(1234567.5);           // ar: 1,234,567.5   ar_EG: ١٬٢٣٤٬٥٦٧٫٥
NumberFormat.decimalPatternDigits(locale: locale, decimalDigits: 1).format(4.25);
NumberFormat.percentPattern(locale).format(0.42);                  // ar: 42% wrapped in LRM marks (see below)
NumberFormat.compact(locale: locale).format(1200000);              // locale-specific "1.2M"
```

*Measured* locale data: `ar` uses Western digits with `.` and `,`, `ar_EG`
uses Arabic-Indic digits with `٫` and `٬`, `ar_DZ` uses `,` as the decimal
separator, and `fa` uses Persian digits. `ar`'s percent sign is wrapped in
LRM marks (`\u200E%\u200E`), so it stays next to its number in RTL text.
Choosing the digit system is a product decision (`rtl-and-arabic.md` §5).

Positional and named locales differ by constructor, and it's easy to get
wrong:

| Takes the locale positionally | Takes `locale:` by name |
|---|---|
| `NumberFormat(pattern, locale)`, `decimalPattern(locale)`, `percentPattern(locale)`, `scientificPattern(locale)` | `currency`, `simpleCurrency`, `compact`, `compactLong`, `compactCurrency`, `compactSimpleCurrency`, `decimalPatternDigits`, `decimalPercentPattern` |
| `DateFormat(pattern, locale)` and every `DateFormat.<skeleton>(locale)` | |

## 4. Money

- **Model money as an integer of minor units plus an ISO 4217 code** in the
  domain (`Money(amountMinor: 4250, currency: 'SAR')`), never a `double` you
  do arithmetic on. Format it only in the view.
- **Always pass the currency.** *Measured:* intl's default currency for `ar`
  is EGP, so `NumberFormat.currency(locale: 'ar')` prints Egyptian pounds for
  a Saudi shop (I18N-currency-default). Use
  `NumberFormat.currency(locale: locale, name: 'SAR')`.
- **Fraction digits follow the currency** when you pass `name:` (intl's
  `currencyFractionDigits`, from ISO 4217: KWD, BHD, OMR and JOD have three,
  JPY none). Don't hard-code `decimalDigits: 2` for the Gulf.
- **Symbols.** `simpleCurrency` uses intl's short symbols, and *measured*
  they're Latin: SAR → `Riyal`, AED → `dh`, KWD/BHD/JOD → `din`,
  EGP → `E£`. For an Arabic UI, pass the symbol you want explicitly
  (`NumberFormat.currency(locale: locale, name: 'SAR', symbol: 'ر.س')`), or
  show the ISO code. The new Saudi riyal sign (U+20C1, Unicode 17) needs a
  font that has the glyph. Check yours before you use it.
- **Placement in RTL.** *Measured:* `ar` puts the symbol after the number
  with an RLM in front (`\u200F#,##0.00\u00A0¤`). Don't glue the symbol on
  yourself with `+` (I18N-011), and isolate a formatted amount that you insert
  into a sentence (`rtl-and-arabic.md` §6).

## 5. Parsing what users type

- Normalise Arabic-Indic and Persian digits before `int.parse` or
  `double.parse` (`rtl-and-arabic.md` §5, I18N-digits-parse). Arabic
  keyboards type them by default.
- `NumberFormat.decimalPattern(locale).parse(text)` understands that locale's
  separators. Use it when users type grouped numbers. Normalise digits first
  anyway, because users mix keyboards.
- Prefer pickers (`showDatePicker`, `showTimePicker`) over parsing typed
  dates. If you must parse, use `DateFormat(pattern, locale).parseStrict`.
- Validation messages are translated text: the validator returns a failure
  or key, and the view shows `l10n.amountInvalid` (see the `flutter-forms`
  skill, or `../flutter-forms/SKILL.md`, if installed).

## 6. Where formatting lives, per layer

| Layer | Holds | Never holds |
|---|---|---|
| Data (DTO, source) | wire formats: ISO 8601 strings, ASCII numbers, minor units | `DateFormat` with a user locale |
| Domain (entity, use case) | `DateTime` (UTC), `int`/`num`, `Money`, enums | formatted strings |
| Logic (notifier, view model, bloc, controller) | the same typed values in state | `'Oct 16'`, `'SAR 42.50'` |
| View / widgets | formatters built with the current locale | |

The data layer may need the locale for one thing: asking the server for
localized content. Send `Accept-Language` from an interceptor that reads the
app's locale state (a repository or provider, not a `BuildContext`, see
`placement-by-architecture.md`), I18N-accept-language-missing.

## 7. If you set `Intl.defaultLocale`

Some apps set `Intl.defaultLocale` once, so bare `DateFormat.yMMMd()` calls
work. That's acceptable if it happens at the composition root **and on every
locale change**, for example in a listener next to `MaterialApp` that reacts
to the locale state. A value set once in `main()` goes stale as soon as the
user switches language in the app. The checker downgrades I18N-014 to `info`
when it sees an assignment, and says so in the note. Confirm the assignment
follows locale changes before you accept it.
