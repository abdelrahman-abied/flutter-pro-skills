# shop_app

Architecture: Clean Architecture + MVN (Model-View-Notifier) with Riverpod code generation.
Flow: View -> Notifier -> UseCase -> Repository -> Source. Feature-first under lib/features/<feature>/.
All user-facing text is localised (English and Arabic) via lib/l10n/*.arb.
