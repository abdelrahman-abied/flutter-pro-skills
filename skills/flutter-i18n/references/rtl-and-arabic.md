# RTL, Arabic and bidirectional text

Sources: the Flutter framework (`flutter_localizations`
`GlobalWidgetsLocalizations`, the Material and Cupertino icon tables), the
intl package (`plural_rules.dart`, `number_symbols_data.dart`, `bidi.dart`,
intl 0.20.x), CLDR plural rules, and the Unicode bidirectional algorithm
(UAX #9). Facts marked *measured* were read from that source in October
2026. Re-check them after a major intl or Flutter upgrade.

This expands `flutter-ui-practices` › `flutter-ui.md` §7 (use
`EdgeInsetsDirectional`/`AlignmentDirectional`, no literals in a localised
app). It doesn't replace it.

## Contents

1. How Flutter decides the direction
2. Directional layout
3. Icons and images that must mirror
4. Arabic plurals and gender
5. Digits: Western, Arabic-Indic, Persian
6. Mixed-direction (bidi) text
7. Fonts, line height and letter spacing
8. Testing RTL

---

## 1. How Flutter decides the direction

`GlobalWidgetsLocalizations` maps the locale to a `TextDirection`. *Measured:*
`ar`, `fa`, `he`, `ps`, `sd` and `ur` are RTL, and everything else is LTR.
`MaterialApp` puts a `Directionality` at the top of the tree from that, so
it only works when `GlobalWidgetsLocalizations.delegate` is among the
`localizationsDelegates` (I18N-016). `GetMaterialApp` and `CupertinoApp` need
the same delegates.

Then every directional widget reads `Directionality.of(context)`. Two
directions matter, and they can differ:

- **UI direction** follows the locale: menus, padding, chevrons.
- **Content direction** follows the text itself. A Qur'an verse is RTL in an
  English UI, and an English product name is LTR in an Arabic UI. Set
  `Text(…, textDirection: TextDirection.rtl)` on content whose direction you
  know, and leave UI text to the ambient direction.

Physical things stay physical: a chess board, a map, a piano keyboard, a
media scrubber, a chart's time axis in most products. Wrap them in
`Directionality(textDirection: TextDirection.ltr, child: …)` once, and
suppress I18N-012 for that file with the reason.

Watch the import clash. `package:intl/intl.dart` exports its own
`TextDirection`, so a file that imports it and Flutter fails with "imported
from both". Use `import 'package:intl/intl.dart' hide TextDirection;` or
`as intl`.

## 2. Directional layout

| Physical (LTR-only) | Directional | Note |
|---|---|---|
| `EdgeInsets.only(left: 16)` | `EdgeInsetsDirectional.only(start: 16)` | `EdgeInsets.symmetric` and `.all` are fine |
| `EdgeInsets.fromLTRB(16, 8, 4, 8)` | `EdgeInsetsDirectional.fromSTEB(16, 8, 4, 8)` | |
| `Alignment.centerLeft` | `AlignmentDirectional.centerStart` | gradients too, unless the gradient is purely decorative |
| `Positioned(left: 8)` | `PositionedDirectional(start: 8)` | or `Positioned.directional(textDirection: …)` |
| `BorderRadius.only(topLeft: …)` | `BorderRadiusDirectional.only(topStart: …)` | chat bubbles |
| `Border(left: …)` | `BorderDirectional(start: …)` | list accent bars |
| `TextAlign.left` | `TextAlign.start` | `TextAlign.justify` is fine |
| `Offset(1, 0)` slide-in | flip the sign when `Directionality.of(context) == TextDirection.rtl` | `SlideTransition` doesn't mirror itself |
| `DismissDirection.endToStart` | already directional | `startToEnd` means "towards the reading end" |

The checker finds the first seven (I18N-012), including Dart 3.10 dot
shorthands (`alignment: .centerLeft`). It skips symmetric pairs
(`left: 8, right: 8`), values copied from a resolved `EdgeInsets`
(`left: p.left`), and code that already picks by direction.

Already directional, so leave them alone: `Row`, `Wrap`, `Flex` and
`MainAxisAlignment.start`/`end`, `CrossAxisAlignment.start`, `ListTile`
`leading`/`trailing`, `Stack`'s default alignment
(`AlignmentDirectional.topStart`), horizontal `ListView`/`PageView` (they
start at the right in RTL), `Scaffold.drawer` (opens from the start side),
`AppBar.leading`, `TextField` cursor and selection.

Custom painting doesn't flip. In `CustomPainter`, read the direction you were
given and mirror the coordinates (`canvas.translate(size.width, 0);
canvas.scale(-1, 1);` for drawings that must mirror, and never for text).

## 3. Icons and images that must mirror

An icon mirrors in RTL only if its `IconData` has `matchTextDirection: true`.
*Measured* from Flutter's icon tables:

| Mirrors automatically | Does **not** mirror (I18N-013) |
|---|---|
| `Icons.arrow_back`, `arrow_forward`, `arrow_back_ios`, `arrow_back_ios_new`, `arrow_forward_ios`, `chevron_left`, `chevron_right`, `navigate_before`, `navigate_next`, `arrow_left`, `arrow_right`, `arrow_right_alt`, `send`, `reply`, `reply_all`, `undo`, `redo`, `list`, `sort`, `first_page`, `last_page`, `open_in_new`, `launch`, `trending_up` | `Icons.keyboard_arrow_left`, `keyboard_arrow_right`, `keyboard_double_arrow_left/right`, `arrow_circle_left/right`, `east`, `west`, `subdirectory_arrow_left/right`, `logout`, `login`, `exit_to_app` |
| `CupertinoIcons.back`, `forward`, `left_chevron`, `right_chevron` | `CupertinoIcons.chevron_left`, `chevron_right`, `chevron_back`, `chevron_forward`, `arrow_left`, `arrow_right`, `chevron_compact_left/right` |

Mirror what shows *direction of reading or navigation*: back and forward,
next and previous, list chevrons, "send", progress that fills along the
line, steppers. Don't mirror what shows a *physical or universal* direction:
media playback (play, fast-forward, skip), clocks and refresh arrows, check
marks, logos, a slash, numbers, charts with a time axis, a phone handset. The
checker can't tell a "next" chevron from a media control, so read each hit.

How to mirror the rest:

```dart
// Pick the mirroring icon
const Icon(Icons.chevron_right); // not Icons.keyboard_arrow_right

// Your own icon font
const IconData kNext = IconData(0xe901, fontFamily: 'AppIcons', matchTextDirection: true);

// Images and SVGs
Image.asset('assets/illustrations/arrow_hint.png', matchTextDirection: true);
SvgPicture.asset('assets/icons/next.svg', matchTextDirection: true); // flutter_svg

// Anything else
Transform.flip(
  flipX: Directionality.of(context) == TextDirection.rtl,
  child: const LottieArrow(),
);
```

## 4. Arabic plurals and gender

Arabic has six plural categories, and intl selects them from the count
(*measured*, `_ar_rule`). The noun form changes with each:

| Category | Counts | Example (كتاب, book) |
|---|---|---|
| zero | 0 | لا توجد كتب |
| one | 1 | كتاب واحد |
| two | 2 | كتابان |
| few | n % 100 in 3–10 (3–10, 103–110, …) | ٣ كتب |
| many | n % 100 in 11–99 (11–99, 111–199, …) | ١١ كتابًا |
| other | everything else (100–102, 200, …) | ١٠٠ كتاب |

A message with only `one` and `other`, which is what an English template
invites, reads wrong for 2 and for almost every count from 3 to 99 (I18N-003).
The ICU form is in `gen-l10n-and-arb.md` §5. Hand-written Dart
(`count == 1 ? … : …`) is worse, because translators can't fix it
(I18N-plural-by-hand). In GetX, `trPlural` only knows singular and plural, so
use `Intl.pluralLogic` with per-category keys (`placement-by-architecture.md`,
GetX).

Gender: verbs, adjectives and pronouns agree with the person addressed. The
UI usually addresses the reader ("you"), so either know the reader's gender
and use `select`, or write neutral Arabic: a passive or a verbal noun
("تم الحفظ" instead of "حفظتَ"). Tell translators which one you want in the
`@key.description`.

Duals also appear outside plurals ("كلا الخيارين"). Give translators whole
sentences, not fragments to assemble.

## 5. Digits: Western, Arabic-Indic, Persian

Three digit systems are in use:

- **Western** `0123456789`: the default in most Gulf and Maghreb apps.
- **Arabic-Indic** `٠١٢٣٤٥٦٧٨٩` (U+0660–0669): common in Egypt and the
  Levant, and the default on iOS Arabic keyboards.
- **Extended Arabic-Indic** `۰۱۲۳۴۵۶۷۸۹` (U+06F0–06F9): Persian and Urdu.

What intl does (*measured*, `number_symbols_data.dart`):

| Locale | Digits | Decimal / group separators | Default currency |
|---|---|---|---|
| `ar` | Western `0` | `.` `,` | EGP |
| `ar_EG` | Arabic-Indic `٠` | `٫` `٬` | EGP |
| `ar_DZ` | Western | `,` `.` | DZD |
| `fa` | Extended `۰` | `٫` `٬` | IRR |
| `he`, `ur` | Western | | |

So `Locale('ar')` alone gives Western digits, and there is no `ar_SA` entry
in intl's number data (it falls back to `ar`). Decide the digit system as a
product decision, write it down, and apply it in one place: format with
`ar_EG` (or map the output) for Arabic-Indic, or keep `ar` for Western.
`DateFormat` follows the same locale data. For one locale, you can switch a
`DateFormat` to Western digits with
`DateFormat.useNativeDigitsByDefaultFor('ar_EG', false)`.

**Parse what users type.** `int.parse('١٢٣')` and `double.tryParse('٣٫٥')`
fail, because Dart's parsers accept only ASCII digits (I18N-digits-parse).
Normalise first, in the parser that your form field or input formatter uses:

```dart
/// Arabic-Indic and Persian digits (and Arabic separators) to ASCII, so
/// int.parse/double.parse accept what an Arabic keyboard types.
String normalizeDigits(String input) {
  final out = StringBuffer();
  for (final rune in input.runes) {
    if (rune >= 0x0660 && rune <= 0x0669) {
      out.writeCharCode(rune - 0x0660 + 0x30); // ٠-٩
    } else if (rune >= 0x06F0 && rune <= 0x06F9) {
      out.writeCharCode(rune - 0x06F0 + 0x30); // ۰-۹
    } else if (rune == 0x066B) {
      out.write('.'); // Arabic decimal separator
    } else if (rune != 0x066C) {
      out.writeCharCode(rune); // drop the Arabic thousands separator
    }
  }
  return out.toString();
}

final amount = double.tryParse(normalizeDigits(controller.text.trim()));
```

Send ASCII digits to servers, and store numbers as numbers. Only the view
decides which digits to show.

## 6. Mixed-direction (bidi) text

The Unicode bidi algorithm orders each run of text by its characters' own
direction, inside the paragraph's base direction. That breaks in
predictable ways when you mix scripts:

- Punctuation at the end of LTR text in an RTL paragraph jumps to the wrong
  side: `"Flutter!"` inside Arabic shows as `!Flutter`.
- A Latin name or number next to Arabic can swap places with its neighbours,
  for example a list of Latin names separated by Arabic commas.
- Phone numbers (`+966 50 123 4567`), IBANs, order codes and URLs reorder
  their groups.

Fixes, from the least to the most effort:

1. **Isolate inserted values.** Wrap a name, number or code that goes into a
   translated sentence in FSI … PDI (U+2068 … U+2069). It then can't affect
   the text around it (I18N-bidi-isolation):

   ```dart
   String isolate(String value) => '\u2068$value\u2069'; // first-strong isolate

   Text(context.l10n.sharedBy(isolate(user.displayName)));
   ```

2. **Give known-direction content its own direction**: `Text(iban,
   textDirection: TextDirection.ltr)`, `Text(ayah, textDirection:
   TextDirection.rtl)`.
3. **Force LTR on Latin-only fields** in an RTL UI: email, password, URL,
   phone, OTP, IBAN, code fields (`TextField(textDirection:
   TextDirection.ltr, textAlign: TextAlign.start)`, I18N-ltr-field). The field
   still sits on the right side of the layout. Only its text runs LTR.
4. **Detect the direction for free text** (chat, comments). intl's `Bidi`
   (`Bidi.detectRtlDirectionality`, `Bidi.estimateDirectionOfText`,
   `Bidi.hasAnyRtl`) estimates it from the content:

   ```dart
   import 'package:intl/intl.dart' as intl;

   TextDirection directionOf(String text) =>
       intl.Bidi.detectRtlDirectionality(text) ? TextDirection.rtl : TextDirection.ltr;

   Text(message.body, textDirection: directionOf(message.body));
   ```

   For a `TextField` the user types into, recompute that in `onChanged` and
   store it in the field's `State`. `BidiFormatter.wrapWithUnicode` exists
   too, but it inserts the older embedding marks (LRE/RLE … PDF), so prefer
   isolates.

**Security: bidi spoofing (I18N-bidi-spoofing).** Control characters let
untrusted text reorder what the user sees. For example, the file name
`"invoice" + U+202E + "fdp.exe"` displays as `invoiceexe.pdf`, and a username
can impersonate another one. Strip them where untrusted text enters the app
(in the data layer, when you map a DTO to an entity, or in the validator),
then isolate the value where you display it:

```dart
final _bidiControls = RegExp('[\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]');

String stripBidiControls(String untrusted) => untrusted.replaceAll(_bidiControls, '');
```

Don't strip them from your own translations, which may use RLM/LRM on
purpose.

## 7. Fonts, line height and letter spacing

- **Fallback.** A custom Latin font (Poppins, Inter) has no Arabic glyphs, so
  Arabic falls back to the platform font, with different metrics and weight
  (I18N-font-fallback). Bundle an Arabic family and declare it:

  ```dart
  ThemeData buildTheme(Locale locale) {
    final arabic = const {'ar', 'fa', 'ur', 'ps', 'sd'}.contains(locale.languageCode);
    final base = ThemeData(fontFamily: arabic ? 'NotoSansArabic' : 'Inter');
    return base.copyWith(
      textTheme: base.textTheme.apply(fontFamilyFallback: const ['NotoSansArabic']),
    );
  }
  ```

  Noto Sans Arabic, Noto Naskh Arabic, IBM Plex Sans Arabic, Cairo, Tajawal
  and Almarai are all under the SIL Open Font License. With `google_fonts`,
  bundle the files and set `GoogleFonts.config.allowRuntimeFetching = false`
  for release, so text doesn't depend on a network call to Google.
- **Line height.** Arabic has tall letters, deep descenders and diacritics
  (harakat) above and below. `height: 1.0`, fixed-height containers and
  tight `maxLines: 1` boxes clip them (I18N-line-height). Leave `height` null
  or use at least 1.3 for UI text and more for vocalised or Qur'anic text,
  and let containers size to their text.
- **No letter spacing on Arabic.** `letterSpacing` pulls apart the joined
  letters of a cursive script (I18N-letter-spacing). Set it from the theme
  per locale, not per widget.
- **No synthetic styles.** Arabic has no capitals and no italics:
  `toUpperCase()` does nothing to it, and `FontStyle.italic` slants it
  unnaturally. Use weight or colour for emphasis. Check that the bold weight
  you use exists in the Arabic font, or the platform fakes it.
- **Length.** Arabic UI text is often shorter in characters but taller, while
  German and Russian are longer. Avoid fixed widths around labels, and test
  with the longest locale you ship.

## 8. Testing RTL

A test harness that matches the app (the same delegates, the locale under
test):

```dart
Widget harness(Widget child, {Locale locale = const Locale('ar')}) => MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

testWidgets('settings row is mirrored in Arabic', (tester) async {
  await tester.pumpWidget(harness(const LanguageTile()));

  expect(Directionality.of(tester.element(find.byType(LanguageTile))), TextDirection.rtl);
  final width = tester.view.physicalSize.width / tester.view.devicePixelRatio;
  expect(tester.getCenter(find.byIcon(Icons.language)).dx, greaterThan(width / 2)); // leading → right
  expect(tester.getCenter(find.byIcon(Icons.chevron_right)).dx, lessThan(width / 2)); // trailing → left
});
```

- gen-l10n and the `Global*` delegates load synchronously, so `pumpWidget` is
  enough. Asynchronous delegates (easy_localization, deferred loading) need
  `await tester.pumpAndSettle()` first.
- Run layout tests in both directions with a variant, and fail on overflow:

  ```dart
  final locales = ValueVariant<Locale>({const Locale('en'), const Locale('ar')});

  testWidgets('cart has no overflow in either direction', (tester) async {
    await tester.pumpWidget(harness(const CartSummary(), locale: locales.currentValue!));
    expect(tester.takeException(), isNull);
  }, variant: locales);
  ```

- Test plurals without widgets. The generated lookup works in a plain unit
  test:

  ```dart
  test('Arabic plural forms', () {
    final ar = lookupAppLocalizations(const Locale('ar'));
    expect(ar.itemsInCart(2), 'عنصران');
    expect(ar.itemsInCart(5), '5 عناصر');
    expect(ar.itemsInCart(11), '11 عنصرًا');
    expect(ar.itemsInCart(100), '100 عنصر');
  });
  ```

- Golden tests render text in the Ahem test font (boxes) unless you load
  real fonts. Load the Arabic font with `FontLoader` in the test setup before
  you compare RTL goldens, or the golden can't show clipping or joining
  bugs.
- Wrap the widget under test in `ProviderScope(overrides: …)`,
  `BlocProvider.value` or `ChangeNotifierProvider.value` as usual (see the
  `flutter-testing` skill, or `../flutter-testing/SKILL.md`).
