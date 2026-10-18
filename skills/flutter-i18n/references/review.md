# flutter-i18n: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`I18N-0xx`). The checker skips generated files and the
gen-l10n output, test, debug, example and preview paths, and code under
`kDebugMode`, `assert`, logging and keys.

| ID | Name | Default severity | What it finds | Don't flag / false positives |
|---|---|---|---|---|
| I18N-001 | catalog-missing-keys | Medium | template keys missing in a locale (once per file, with coverage %); `ar_EG` counts keys from `ar` | a locale deliberately shipped partial: suppress with the reason |
| I18N-002 | placeholder-mismatch | Medium | translation drops a placeholder, or uses an unknown or translated one (`{الاسم}`) | none known |
| I18N-003 | plural-forms-missing | Medium | `ar` plural without one/two/few/many (also he, ru, uk, pl, cs, hr, sr, sl, lt, ga, cy, lv) | messages whose count is always 0–2 |
| I18N-004 | secret-in-catalog | High | API keys, tokens, JWTs, private keys, credentials in URLs | public publishable keys are still a smell; move them |
| I18N-005 | synthetic-package | High for `synthetic-package: true`, Medium for `package:flutter_gen` imports | the removed synthetic package | Flutter < 3.32 projects that can't upgrade yet |
| I18N-006 | catalog-missing-descriptions | Info | ≥20% of template messages without `description` | |
| I18N-010 | hardcoded-ui-string | Low (prose), Info (one capitalised word or acronym) | literals in `Text`, `hintText`, `tooltip`, `semanticLabel`, app `title`, `Get.snackbar`, string params of the project's own widgets | brand names, units, notation (`O-O`): suppress. The checker counterpart of `UI-l10n` |
| I18N-011 | translation-concatenation | Medium (words in the literal), Low (punctuation, values, separators) | `l10n.a + …`, `'${l10n.a} items'`, `tr('k') + …` | `'${l10n.a}'` alone is not reported |
| I18N-012 | physical-direction-geometry | Medium (Low for gradients, borders, files that force LTR) | `EdgeInsets.only(left/right)` (asymmetric), `fromLTRB`, `Positioned(left/right)`, `Alignment.*Left/*Right`, `TextAlign.left/right`, dot shorthands | code that already picks by direction; physical widgets. The checker counterpart of `UI-rtl` |
| I18N-013 | non-mirroring-directional-icon | Medium | `Icons.keyboard_arrow_*`, `east`/`west`, `CupertinoIcons.chevron_*` | media and map arrows; icons chosen by `isRtl` |
| I18N-014 | format-without-locale | Medium (Info in data/domain, for numeric patterns, or when `Intl.defaultLocale` is set) | `DateFormat.yMMMd()`, `NumberFormat.compact()` with no locale | wire formats: pass `'en'` explicitly to say so |
| I18N-015 | translation-in-logic | Medium (Low for GetX `.tr`) | `AppLocalizations.of`, `lookupAppLocalizations`, `S.current`, `.tr()` in logic, state or data files | composition-root code |
| I18N-016 | missing-localization-delegates | High when RTL ships, else Medium (Low for a secondary error app) | app widget without `localizationsDelegates`/`supportedLocales` or `GlobalWidgetsLocalizations` | |
| I18N-017 | dynamic-icu-pattern | Medium | `MessageFormat(<non-constant>)`, `Intl.message('… $x')` | |
| I18N-018 | mojibake-text | High | UTF-8 text decoded as Latin-1 and saved (`Ø§Ù„`, `Ã˜Â§`) in literals or catalogs | |

Reading-level findings (`I18N-<slug>`):

| ID | Severity | Look for |
|---|---|---|
| I18N-plural-by-hand | Medium | `count == 1 ? 'item' : 'items'`, or GetX `trPlural` (singular/plural only) for Arabic |
| I18N-translated-string-in-state | Medium | state classes with `String message` built from l10n (the script sees the lookup, not the field) |
| I18N-locale-state-placement | Medium | the locale in a global, a widget `State`, or `Platform.localeName` read in logic |
| I18N-locale-not-persisted | Low | the language choice is lost on restart; no "follow the device" option |
| I18N-accept-language-missing | Low | the server returns localized content but the data layer never sends `Accept-Language` |
| I18N-digits-parse | High | `int.parse`/`double.parse`/`num.tryParse` on user input with no Arabic-Indic digit normalisation |
| I18N-currency-default | Medium | `NumberFormat.currency(locale: 'ar')` without `name:` (intl's `ar` defaults to EGP) |
| I18N-bidi-isolation | Medium | names, numbers, phone numbers or URLs inserted into RTL text without isolation, so punctuation jumps |
| I18N-bidi-spoofing | Medium | untrusted names or file names shown without stripping bidi controls (security) |
| I18N-ltr-field | Low | email, phone, OTP, IBAN or code fields not forced to `TextDirection.ltr` in an RTL UI |
| I18N-font-fallback | Medium | a Latin-only custom font with no Arabic `fontFamilyFallback` |
| I18N-line-height | Low | `height: 1.0`, fixed-height boxes or `maxLines: 1` that clip Arabic diacritics |
| I18N-letter-spacing | Low | `letterSpacing` applied to Arabic text |
| I18N-case-transform | Low | `toUpperCase()`/`toLowerCase()` on translated text |
| I18N-mirror-asset | Low | directional images, SVGs or Lottie files not mirrored in RTL |
| I18N-slide-direction | Low | physical `Offset(1, 0)` slides, `DismissDirection.left/right`-style assumptions |
| I18N-icu-escaping | Medium | `use-escaping: true` turned on while messages still contain `Don't`, or literal braces without it |
| I18N-pii-in-catalog | Medium | real emails, phone numbers, names or internal hosts in catalogs (security) |
| I18N-remote-translations | Medium | downloaded translations rendered as HTML or Markdown, or used as URLs (security) |
| I18N-calendar-assumption | Low | assuming Monday as the first day (`MaterialLocalizations.firstDayOfWeekIndex`) or Gregorian only (Hijri apps) |
| I18N-generated-edited | Medium | hand edits in `app_localizations*.dart`; they vanish on the next generation |
| I18N-rtl-untested | Info | no widget test runs any screen in an RTL locale |

**Dedupe with other skills.** When the checker ran, report `I18N-010` and
`I18N-012` instead of `UI-l10n` and `UI-rtl` (from `flutter-ui-practices`)
for the same lines. Raw `e.toString()` in the UI is `ERR-008`
(`flutter-error-handling`), and `BuildContext` in logic is `ARCH-102`
(`flutter-architecture`). Mention the other ID in the note instead of
filing it twice.

## Finding examples

Use the suite's finding format, so `dart-flutter-review` can merge the
findings:

```markdown
### [MEDIUM] Arabic plural falls back to "other" for 3–10 and 11–99
- id: I18N-003
- where: lib/l10n/app_ar.arb:6
- evidence: `"itemsInCart": "{count, plural, =0{…} =1{…} =2{…} other{{count} عنصر}}"`
- rule: CLDR Arabic plural categories (flutter-i18n › rtl-and-arabic.md §4)
- why: intl picks `few` for 3–10 and `many` for 11–99; without them the cart reads "٥ عنصر" instead of "٥ عناصر"
- fix: |
    "{count, plural, zero{لا توجد عناصر} one{عنصر واحد} two{عنصران} few{{count} عناصر} many{{count} عنصرًا} other{{count} عنصر}}"
- confidence: confirmed

### [MEDIUM] Notifier stores English text
- id: I18N-015
- where: lib/features/cart/presentation/notifier/cart_notifier.dart:14
- evidence: `final l10n = lookupAppLocalizations(const Locale('en')); return CartEmpty(l10n.cartTitle);`
- rule: logic returns typed values; the view translates (flutter-i18n › placement-by-architecture.md §MVN)
- why: Arabic users see English, and the message never updates when the locale changes
- fix: emit `const CartEmpty()` and render `AppLocalizations.of(context).cartEmpty` in the view's switch
- confidence: confirmed
```

Open the report with one line naming the profile, the l10n system and the
RTL locales (`mvn, gen-l10n, RTL: ar`). Report a pattern-wide problem
**once**, with a few locations and the count.
