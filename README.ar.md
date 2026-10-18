<div dir="rtl">

# flutter-pro-skills

**مجموعة Agent Skills بتخلّي أي AI agent يكتب ويراجع كود Flutter نضيف وآمن من الأول (clean and secure by default)، وبيحكم على الكود حسب معمارية مشروعك إنت.**

[English](README.md) · [الترخيص MIT](LICENSE)

## ليه الريبو ده؟

- **أمان وقت الكتابة، مش بعد ما المشكلة تحصل.** طلبنا من agent: "ضيف login واحفظ الـ token".
  - **من غير الـ skills:** حفظ الـ token في `SharedPreferences` في المرتين.
  - **بالـ skills:** استخدم `flutter_secure_storage` في المرتين، ومن غير ولا مشكلة أمان.

  ([تفاصيل الـ benchmark](bench/README.md))
- **بيحكم بمعماريتك إنت.** الـ skills بتكتشف لوحدها مشروعك ماشي بأنهي معمارية: MVVM، و MVN، و Bloc/Cubit، و MVC، و GetX، و Provider، و Riverpod، و Clean Architecture. وبعدها بتطبّق قواعد المعمارية دي بس. ده مهم لأن المعماريات بتختلف فعلًا:
  - في MVVM مسموح للـ ViewModel يكلّم الـ Repository على طول.
  - في MVN لازم الـ Notifier يعدّي على Use Case.
  - في Bloc ممنوع bloc يكلّم bloc تاني.

  أي أداة بتفرض stack واحد هتطلّع لك أخطاء مش حقيقية.
- **أدوات فحص حقيقية، مش بس كلام.**
  - 16 checker بيقروا الكود من غير ما يعدّلوا فيه حاجة: المعمارية، والأخطاء، والتستات، والأمان، والتنقّل، والـ forms، والترجمة والـ RTL، والأداء، والتخزين المحلي، والـ networking، والكود الـ native، والـ design system، والـ adaptive layout، والـ accessibility، والـ release، والـ review.
  - مكتوبين بـ Python من غير أي مكتبات خارجية، وعليهم حوالي 2150 تست.
  - اتجرّبوا على تطبيقات مفتوحة المصدر حقيقية، زي Compass الرسمي من فريق Flutter، وأمثلة Bloc و Riverpod الرسمية، و lichess، و immich، و Wonderous، وأمثلة drift.
- **GitHub Action بيقفل الـ PR على المشاكل الجديدة بس،** فالمشاكل القديمة في المشروع متعطّلش الفريق.
- **شغالة مع أي agent بيقرأ `SKILL.md`:** Claude Code، و Codex، و Cursor، و GitHub Copilot، و Gemini CLI، و OpenCode. اتجربت فعلًا على Claude Code و OpenCode.

## التثبيت

</div>

```bash
npx skills add abdelrahman-abied/flutter-pro-skills
```

<div dir="rtl">

أو:

</div>

```bash
git clone https://github.com/abdelrahman-abied/flutter-pro-skills
cd flutter-pro-skills && ./install.sh
```

<div dir="rtl">

وبعد كده كلّم الـ agent عادي بالعربي أو بالإنجليزي:
- *"اعمل feature للطلبات"*
- *"راجع الـ PR بتاعي"*
- *"هل الـ structure بتاعنا صح؟ إحنا شغالين Clean + MVN"*
- *"احفظ الـ token بشكل آمن"*
- *"إيه اللي ملوش تستات؟"*
- *"راجع الترجمة العربية والـ RTL"*
- *"الليستة دي بتقطّع ليه؟"*
- *"ضيف dark mode بالـ design tokens بتاعتنا"*
- *"الشاشة دي شغالة مع TalkBack؟"*

الـ agent بيختار الـ skill المناسبة لوحده.

## الـ 20 skill

| الـ skill | بتعمل إيه |
|---|---|
| `dart-flutter-best-practices` | المدخل الرئيسي: كتابة كود Dart سليم على أسلوب مشروعك، و 149 قاعدة من Effective Dart |
| `flutter-architecture` | بتكتشف معماريتك وبتحكم بقواعدها (28 قاعدة أوتوماتيك و 28 anti-pattern) |
| `flutter-feature-scaffold` | بتعمل feature جديدة كاملة بمعماريتك، **آمنة من الأول**، ومش بتكتب فوق أي ملف موجود |
| `flutter-secure-defaults` | الأمان في كل طبقة: الـ tokens في secure storage، والـ auth في interceptor، و HTTPS بس، ومفيش secrets في الكود ولا بيانات شخصية في الـ logs |
| `flutter-error-handling` | الأخطاء ماشية صح بين الطبقات، و `Result` ولا exceptions، ومفيش spinner بيلف على طول |
| `flutter-testing` | تختبر إيه الأول حسب معماريتك، و test smells، والأجزاء اللي ملهاش تستات |
| `flutter-navigation` | go_router، والـ guards، و validation للـ deep links |
| `flutter-forms` | الـ validation، وحقول الباسورد والـ OTP، والحماية من الضغط مرتين |
| `flutter-i18n` | ملفات الترجمة، **صيغ الجمع العربي**، والـ RTL، والأيقونات اللي لازم تنعكس |
| `flutter-performance` | الـ rebuilds حسب معماريتك، و `const`، و `RepaintBoundary`، والليستات الـ lazy والـ slivers، والـ isolates، وحجم الصور، وتشخيص التقطيع بـ DevTools |
| `flutter-persistence` | Drift و sqflite و Hive و shared_preferences، والـ caching، والـ offline-first والـ sync، والـ migrations، وكلها ورا الـ repository. والـ SQL بـ parameters بس |
| `flutter-networking` | طبقة الـ API حسب معماريتك: client واحد متظبّط (Dio أو http) بـ timeouts، و DTOs و JSON متأكد منه، وحماية الـ pagination من الطلب المكرر، والـ cancellation، والـ retry للطلبات الآمنة بس، والـ WebSockets، و fake clients في التستات |
| `flutter-platform-integration` | الكود الـ native كـ data source: الـ platform channels والـ Pigeon، والـ FFI من غير memory leaks، والـ platform views، وكتابة plugin، والـ permissions وقت ما تحتاجها، والـ background isolates |
| `flutter-design-system` | الـ tokens، و `ThemeData` و `ColorScheme`، و `ThemeExtension`، وطبقة components، والـ dark mode، ومفيش ألوان أو مقاسات مكتوبة على طول في الـ features |
| `flutter-adaptive-layout` | كود واحد شغال على الموبايل والتابلت والـ foldables والـ desktop والويب: breakpoints موحّدة، و list-detail، و bar أو rail حسب العرض، ومفيش قفل للـ orientation، و hover و keyboard، ومفيش crash من `dart:io Platform` على الويب |
| `flutter-accessibility` | `Semantics` والـ labels، وحجم الـ tap targets، والـ contrast، وتكبير الخط، وترتيب الـ focus، وتستات الـ screen reader. ومفيش أسرار بتتقري بصوت عالي |
| `flutter-release` | النشر: الـ flavors والـ environments بتتحدد في مكان واحد، والـ signing بره الـ git، والـ versioning، ومتطلبات المتاجر، و CI/CD آمن (مفيش secrets في الـ logs ولا ثغرات `pull_request_target`) |
| `flutter-ui-practices` | الـ dispose، و `context` بعد `await`، وتكلفة الـ build، والـ keys |
| `dart-naming` | قواعد التسمية، وأسماء كل دور في كل معمارية |
| `dart-flutter-review` | **review كامل** بـ agents شغالين بالتوازي، وتقرير واحد مرتّب حسب الخطورة |

ولو عايز فحص أمان عميق قبل النشر على المتجر (obfuscation، و pinning، و RASP)، ثبّت معاها [flutter-security-audit](https://github.com/abdelrahman-abied/flutter-security-audit).

## نتايج الـ benchmark (بصراحة)

| المهمة | من غير skills | بالـ skills |
|---|---|---|
| كتابة login وحفظ الـ token | `SharedPreferences` ❌ | `flutter_secure_storage` ✅ |
| review لـ 12 مشكلة مزروعة | 92% | 96%، ومن غير أي إنذار غلط على MVN |
| الحكم على معمارية Bloc | 2/2 | 2/2، وكان فيه ادعاءات غلط **اتصلّحت بعدها** |
| كتابة شاشة ليستة (T4، اتعادت 18 أكتوبر) | مرة من مرتين ضاف مخالفة معمارية و catch بيبلع الخطأ | 0 مشاكل جديدة في المرتين؛ ومرة صلّح مشاكل قديمة كمان. الفرق صغير على الموديل ده |

اتعادت T3 في 18 أكتوبر وطلعت نفس النتيجة (من غير skills: الـ token في `SharedPreferences` في المرتين). العينة صغيرة (مرتين لكل مهمة، وموديل واحد مجاني)، والتفاصيل كلها في [bench/README.md](bench/README.md).

## المساهمة

**أهم مساهمة ممكن تعملها هي إنك تبلّغ عن false positive،** يعني الأداة قالت إن فيه مشكلة وهي مش مشكلة. فيه نموذج جاهز لده في الـ issues. اقرأ [CONTRIBUTING.md](CONTRIBUTING.md).

## الترخيص

MIT، © 2026 Abdulrahman Obaid. نمط MVN (Model-View-Notifier) من تأليف Abdulrahman Abied.

</div>
