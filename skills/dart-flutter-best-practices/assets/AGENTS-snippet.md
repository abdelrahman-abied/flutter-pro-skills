## Dart / Flutter conventions

<!-- Paste this block into the repo's AGENTS.md. Agents that read another file
     can include or copy it: CLAUDE.md (a line `@AGENTS.md` imports it),
     GEMINI.md, .cursor/rules/*.mdc, .github/copilot-instructions.md.
     It's loaded on every task, so keep it short; the flutter-pro-skills
     skills carry the detail. Edit the [bracketed] parts and delete the rest. -->

- Follow Effective Dart and this repo's `analysis_options.yaml`. When writing or
  reviewing Dart, use the `dart-flutter-best-practices` skill (it routes to
  `dart-naming`, `flutter-ui-practices`, `flutter-architecture` and
  `dart-flutter-review`).
- Architecture: [Clean + MVN | MVVM (Flutter guide) | Bloc + Clean | Provider | MVC | GetX]
  (see the `flutter-architecture` skill). Reviewers judge the code against this
  declared pattern, not a guessed one.
- Layout: [feature-first `lib/features/<name>/{domain,data,presentation}` | layer-first].
  Role suffixes: [`XView`, `XNotifier`, `XState`, `XUseCase`, `XRepository`/`XRepositoryImpl`].
- Locals: [`final` unless reassigned | `var` everywhere]. Imports: [relative inside lib/ | `package:` only].
- Constants: lowerCamelCase (`defaultPadding`), no `k` prefix. [Delete this line if the repo uses `kFoo`.]
- Before saying a change is done, run `dart format <changed files>` and
  `flutter analyze` (or `dart analyze`) with zero new issues. Never add
  `// ignore:` without a reason comment.
- Never edit generated files (`*.g.dart`, `*.freezed.dart`). Change the
  source and run `dart run build_runner build -d`.
