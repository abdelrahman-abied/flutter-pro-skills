---
name: flutter-i18n
description: Localize Flutter apps and review localization by the app's own architecture - gen-l10n, l10n.yaml and ARB files, intl, ICU plurals, select and gender, date, number and currency formatting, locale switching, and RTL for Arabic, Hebrew, Persian and Urdu (Directionality, EdgeInsetsDirectional, mirrored icons, bidi text, Arabic-Indic digits, Arabic plural forms, RTL tests). Logic returns keys or typed failures and the view translates, in MVN, MVVM, Bloc, Provider or GetX. No secrets or PII in ARB, no ICU patterns built from user text. Includes a checker for ARB key, placeholder and plural parity, hardcoded strings, left/right layout and non-mirroring icons. Use it whenever Flutter code shows user-facing text or touches l10n.yaml or ARB files, or someone says "translate", "hardcoded strings", "RTL", "Arabic", "ترجمة" or "عربي", including a review limited to strings or RTL.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.1"
  suite: flutter-pro-skills
---

# Flutter internationalization (i18n), RTL and Arabic

> **Writing a standard feature?** If you're filling in a feature that
> `flutter-feature-scaffold` generated, its cross-cutting rules already cover
> this skill's write-time defaults (strings through the project's l10n). You can stop reading here and check
> once at the end with `bash ../dart-flutter-review/scripts/review.sh <project-root> --diff HEAD --findings-only`.
> Read on when the work is about this area itself, or to fix a finding it reports.

Localization bugs don't crash the app, so nobody sees them in review.
Instead, an Arabic user sees English month names, a cart that says
"3 كتاب" when it should say "٣ كتب", a back chevron pointing the wrong way,
or a padding that hugs the wrong edge. The fixes are cheap when you write the
code and expensive once there are hundreds of screens.

This skill makes text, numbers and layout correct for every locale the app
ships, and it places the work in the layers the project *already has*. The
rule is the same in every pattern: **logic decides what to say, and the view
says it in the user's language**. Notifiers, view models, blocs and
controllers hold keys, enums and typed failures. Widgets turn them into
strings with the `BuildContext` they already have. Where the locale lives,
and how it's persisted, follows the pattern (MVN notifier, MVVM view model,
Bloc cubit, Provider model, GetX `Get.updateLocale`).

## Workflow

### 1. Read the project first

- **Declared conventions.** Look in your agent's project instructions file
  (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/…`,
  `.github/copilot-instructions.md`), for rules like "keys are snake_case",
  "we use easy_localization" or "Arabic is the default". A declared convention
  wins.
- **The l10n system.** `l10n.yaml` plus `lib/l10n/*.arb` means gen-l10n.
  `lib/l10n/intl_*.arb` plus `flutter_intl:` in pubspec means intl_utils
  (`S.of(context)`). `easy_localization` means JSON under
  `<app>/assets/translations/`. `slang` means `*.i18n.json`. A `Translations`
  subclass means GetX `.tr`. Keep the system the project has. Two systems in
  one app is worse than either of them alone.
- **Locales and direction.** Find the ARB/JSON files and `supportedLocales`.
  If any of them is `ar`, `fa`, `he`, `ps`, `sd` or `ur`, the app ships RTL
  and every RTL rule below applies.
- **The architecture.** Detect it with the `flutter-architecture` skill (if
  your agent doesn't auto-load skills, read `../flutter-architecture/SKILL.md`).
  The placement rules depend on it.

Then run the checker. It is read-only, needs only the Python standard library,
and doesn't need `pub get`:

```bash
python3 -I <skill-dir>/scripts/check_i18n.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_i18n.py <project-root> --json              # schema flutter-pro-skills/i18n@1
python3 -I <skill-dir>/scripts/check_i18n.py <project-root> --files changed.txt # diff review: report only these files
python3 -I <skill-dir>/scripts/check_i18n.py <project-root> --profile getx      # declared pattern wins
```

The CLI is `check_i18n.py <project-root> [--json] [--files <list>]
[--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate] [--max n]`.
`--files` takes a file of relative paths or a comma-separated list. It still
reads every catalog, because parity needs the template. The exit code is `0`
whenever a report is produced and `2` on a usage error. Layers and roles come
from `../flutter-architecture/scripts/arch_check.py --json`. Without that
sibling it falls back to path-based classification and says so.

```text
== I18N
  profile: mvn (arch_check, confidence high)
  classification: arch_check files[]
  localisation: gen-l10n (lib/l10n, template app_en.arb), 2 locales; RTL: ar
  scanned: 142 Dart files, 2 catalog files
  [I18N-003] plural-forms-missing (medium) x1 — A plural message lacks CLDR categories this locale needs ...
      lib/l10n/app_ar.arb:6  itemsInCart (ar): missing few, many   [ar: zero=0, one=1, two=2, few=3-10, many=11-99, other=100+ (mod 100)]
```

### 2. Set up (only if the app isn't localised yet)

For the step-by-step setup (dependencies, `generate: true`, `l10n.yaml`,
delegates), defer to the official `flutter-setup-localization` recipe from
`flutter/agent-plugins`, if it's installed. **One correction:** its April
2026 text still shows `synthetic-package: true` and
`import 'package:flutter_gen/gen_l10n/…'`. Current Flutter removed the
synthetic package: `synthetic-package: true` stops the tool ("Cannot enable
synthetic-package, this feature has been removed"), and the generated file
lives in your source tree (`lib/l10n/app_localizations.dart` by default).
Import it from there. `references/gen-l10n-and-arb.md` has the current
setup, the `l10n.yaml` options worth turning on, and ICU syntax.

### 3. Write

Follow the WRITE checklist below. Before you add a locale-dependent feature,
read `references/placement-by-architecture.md` for the pattern's code. Read
`references/rtl-and-arabic.md` before you touch layout in an RTL app, and
`references/formatting.md` before you format a date, number or price.

### 4. Review

Run the checker, then read every hit before calling it `confirmed`. Then walk
the reading-level checklist, which covers what a script can't see. Suppress a
deliberate hit with a reason:
`// i18n-ignore: I18N-012 the chess board is physical and never mirrors` (on
the line or the line above), `// i18n-ignore-file: I18N-010 <reason>`, or, in
an ARB or JSON catalog, a top-level `"@@x-i18n-ignore": "I18N-001 <reason>"`.
gen-l10n ignores keys that start with `@`.

## Where translation happens, per architecture

| Concern | MVN | MVVM | Bloc / Cubit | Provider | GetX |
|---|---|---|---|---|---|
| Logic emits | sealed state with enums / typed `XError` | view-model fields + `Command` error as typed values | state with a status enum / typed failure | typed fields on the `ChangeNotifier` | keys in `.obs` fields |
| Translated in | the view's `switch` with `AppLocalizations.of(context)` | the view (`ListenableBuilder`) | `BlocBuilder` / `BlocListener` | `Consumer` / `build()` | the view: `Text(controller.key.value.tr)` |
| Locale state | `@riverpod class LocaleNotifier` → use case → `LocaleRepository` | `LocaleViewModel` (or the settings view model) → `LocaleRepository` | `LocaleCubit` (→ repository, or `HydratedCubit`) | `LocaleModel` via `ChangeNotifierProvider` | `Get.updateLocale` from a `LocaleController` |
| Persistence | data layer: a source over `SharedPreferences` | `LocaleRepositoryLocal` over a prefs service | repository, or hydrated storage | a service the model calls | `GetStorage`/prefs in a service |
| Failure → text | extension in presentation: `failure.message(l10n)` | same | same | same | a key map in the view |

GetX is different on purpose. `'key'.tr` is context-free and re-reads the
current locale, so `.tr` in a view is the idiom. A controller that stores
`'saved'.tr` in a field freezes the text at the old locale, so store the key
there and call `.tr` in the view. The checker grades that case `low` under the
getx profile, and `medium` elsewhere.

## WRITE checklist

1. **No user-facing literals in widgets** once the app is localised: `Text`,
   `hintText`, `labelText`, `tooltip`, `semanticLabel`, `title:` of the app,
   snackbar and dialog text. Brand names, units and codes may stay literal.
   Say so with an `i18n-ignore` comment.
2. **One message per sentence, with placeholders.** Never build text with `+`
   or by gluing `'${l10n.a} ${l10n.b}'`. Word order, spaces and punctuation
   change per language. `"Total: {amount}"` is one message.
3. **Plurals through ICU**, not `count == 1 ? … : …`. Arabic needs `zero`,
   `one`, `two`, `few`, `many` and `other`. Every other locale needs at least
   the categories CLDR defines for it. Only `=0`, `=1` and `=2` are allowed
   as exact matches. gen-l10n treats `=1` and `one` as the same argument.
4. **Gender and variants through `select`**, with `other` as the fallback.
   In Arabic, second-person text agrees with the reader's gender. Use `select`
   when you know it, and neutral phrasing when you don't.
5. **Logic returns keys, enums or typed failures, never translated strings.**
   The view translates. State that stores display text goes stale when the
   locale changes, and it drags `BuildContext` into logic (ARCH-102).
6. **Locale state lives in the pattern's logic holder**, and its persistence
   lives in the data layer. Offer "follow the device" (`locale: null`) as well
   as explicit choices.
7. **Format in the view, with the current locale**: `DateFormat.yMMMd(locale)`,
   `NumberFormat.currency(locale: locale, name: 'SAR')`. Flutter does not set
   `Intl.defaultLocale` for you. Entities keep `DateTime`, `num` or integer
   minor units plus a currency code, never formatted strings.
8. **Directional geometry everywhere in an app that ships RTL**:
   `EdgeInsetsDirectional`, `AlignmentDirectional`, `PositionedDirectional`,
   `BorderRadiusDirectional`, `TextAlign.start/end`. Use physical `left`/`right`
   only for things that really are physical (a chess board, a map compass,
   media controls).
9. **Icons that point must mirror.** `Icons.arrow_back`, `chevron_left/right`
   and `arrow_forward_ios` mirror automatically. `Icons.keyboard_arrow_left/right`,
   `east`/`west` and `CupertinoIcons.chevron_left/right/back/forward` don't.
   Mirror images and SVGs with `matchTextDirection: true`.
10. **Isolate user and server text inside translated sentences** (names,
    numbers, URLs, codes), and strip bidi control characters from untrusted
    names at the data boundary. See "Secure by default".
11. **Normalise digits before you parse** user input. `int.parse('١٢٣')`
    throws, and Arabic keyboards type Arabic-Indic digits.
12. **Give Arabic a real font and room**: `fontFamilyFallback` with an Arabic
    font, line height of at least 1.3 (or `null`), no fixed heights around
    text, no `letterSpacing` on Arabic (it breaks the cursive joins).
13. **Configure the app widget**: `localizationsDelegates` (including
    `GlobalWidgetsLocalizations`, which sets RTL) and `supportedLocales`, on
    `MaterialApp`, `CupertinoApp` or `GetMaterialApp`.
14. **Describe every template message** (`@key.description`, with an
    `example` per placeholder). Translators can't see your screen.
15. **Test in an RTL locale**: one widget test per screen family with
    `locale: Locale('ar')`, plus unit tests for plural output. See
    `references/rtl-and-arabic.md` §8.

## Secure by default

- **No secrets or PII in catalogs.** ARB and JSON files ship inside the app
  binary and go to translation vendors (Crowdin, Lokalise). API keys, tokens,
  internal URLs, staff emails, test accounts and real customer names don't
  belong there. Keep config in the data layer (see the `flutter-secure-defaults`
  skill if it's installed: `../flutter-secure-defaults/SKILL.md`).
- **Never build an ICU pattern from runtime text.** gen-l10n inserts
  placeholder *values* as plain strings, which is safe. A pattern that
  contains user or server text (`MessageFormat('Hi $name')`,
  `Intl.message('… $x')`, translations downloaded and parsed at runtime) is
  parsed as syntax: `{`, `}`, `'` and `plural` in the data change the message
  or break it. Pass untrusted text as an argument.
- **Neutralise bidi controls in untrusted text.** U+202A–U+202E and
  U+2066–U+2069 in a username or file name can reorder what the user sees
  (`"invoice" + U+202E + "fdp.exe"` displays as `invoiceexe.pdf`). Strip
  them where the data enters the app, then wrap the value in an isolate (FSI…PDI) where you
  display it.
- **Treat over-the-air translations as untrusted input**: plain text only,
  never HTML, Markdown links or URLs.

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-setup-localization`** (official, `flutter/agent-plugins`, if
  installed) for first-time setup, with the synthetic-package correction
  above.
- **`flutter-architecture`** for detecting the pattern and its layer rules
  (ARCH-102 context-in-logic). Fallback: `../flutter-architecture/SKILL.md`.
- **`flutter-ui-practices`** for the widget side: `UI-l10n`, `UI-rtl`, theming
  and accessibility. Fallback: `../flutter-ui-practices/references/flutter-ui.md` §7.
- **`flutter-error-handling`** for mapping failures to user-safe messages
  (ERR-008). Fallback: `../flutter-error-handling/SKILL.md`.
- **`flutter-forms`** for validators and input fields (digit normalisation
  belongs in the parser it uses). Fallback: `../flutter-forms/SKILL.md`.
- **`flutter-secure-defaults`** for where config and secrets live. Fallback:
  `../flutter-secure-defaults/SKILL.md`.
- **`flutter-testing`** for widget-test setup and fakes. Fallback:
  `../flutter-testing/SKILL.md`.
- **`dart-flutter-review`** for running this skill inside a full review.
  Fallback: `../dart-flutter-review/SKILL.md`.

## References

| File | Read it when |
|---|---|
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/gen-l10n-and-arb.md` | setting up or changing gen-l10n, `l10n.yaml` options, ARB metadata, ICU placeholders, plurals, select, escaping, fallbacks, other l10n systems |
| `references/rtl-and-arabic.md` | layout in an RTL app, mirrored icons, Arabic plurals and gender, digits, bidi text, fonts and line height, RTL tests |
| `references/formatting.md` | formatting dates, times, numbers, percentages and currency with intl, parsing user numbers, `Intl.defaultLocale`, Hijri and week start |
| `references/placement-by-architecture.md` | putting locale state, persistence, translation and failure messages in MVN, MVVM, Bloc/Cubit, Provider, GetX, Riverpod or setState code |
