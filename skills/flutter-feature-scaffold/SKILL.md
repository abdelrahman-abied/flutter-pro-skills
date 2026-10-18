---
name: flutter-feature-scaffold
description: Scaffold a new Flutter feature, screen, page or module in the architecture the project already uses - MVN (Riverpod codegen notifiers + use cases), MVVM (view models with Command/Result), Bloc, Cubit, GetX, Provider or plain Riverpod. It detects the pattern, copies the project's conventions (feature-first vs layer-first, Screen/Page/View, import style), dry-runs first and never overwrites, and its output is secure by default, with fake-based tests. Use it first, before writing any files, whenever someone asks to create, add, build, scaffold or generate a feature, module, page or new screen (settings, profile, checkout), says "generate the boilerplate" or "set up a feature in clean architecture/MVN/MVVM/bloc", or wants a new repository, notifier, bloc, cubit or view model with its layers, even if they never say "scaffold". For restructuring existing code, use flutter-architecture.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.0"
  suite: flutter-pro-skills
---

# Flutter feature scaffold

Creates a new feature, with every layer, in **the architecture the project
already uses**, not the one you'd pick for a fresh app. It runs the
`flutter-architecture` checker, copies the conventions it finds, and produces
code that passes that checker with zero violations for the profile. It also
writes test skeletons that use fakes, and prints the commands that make the
code compile. Every generated file is idiomatic Dart 3: sealed states,
`final class` data types, `abstract interface class` contracts, const
constructors and `super.key`. It is also **secure by default** (see below):
the code passes the suite's security, error-handling and forms checkers with
zero findings, so it needs no hardening pass afterwards.

The script is `scripts/scaffold.py` (Python ≥3.8, stdlib only). It is the only
script in the suite that writes into a project, and it does so only with
`--write`. It never overwrites a file, never edits `pubspec.yaml`, and never runs
pub, build_runner or the analyzer itself.

## Workflow

1. **Detect.** Check for a declared architecture first, because it beats
   inference: your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
   `GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`), the README
   or ADRs. If one is declared, pass it as `--profile`. Otherwise `auto` runs
   `../flutter-architecture/scripts/arch_check.py --json` for you. In a mixed
   codebase, follow the pattern of the feature's neighbours or the declared
   target, and don't add a third (flutter-architecture › `detect.md` §8).
2. **Dry run** (the default) and read the plan:
   ```bash
   python3 -I <skill-dir>/scripts/scaffold.py <project-root> <feature_name> [--profile auto] [--clean] [--entity Name]
   ```
   `== SCAFFOLD PLAN` shows the pattern and why it was chosen, the layout and
   every inferred convention with its evidence. `== FILES` lists each file
   with the classes and providers it declares (`+` new, `=` exists and will be
   skipped). `== DEPENDENCIES` lists what's missing from pubspec.
3. **Decide, say it, and keep going.** Choose the feature name (snake_case,
   named for the user-facing capability: `order_history`, not
   `orders_screen`), the domain object name (`--entity Order` when it differs
   from the feature), and whether to add use cases (`--clean`, or what the
   project's neighbours do). State those choices in one line and go on to
   step 4: the user already asked for the feature, the dry run shows the
   plan, and `--write` never overwrites. Stop and ask **only** when the
   answer would change the architecture and the project doesn't settle it:
   confidence is `low`, the pattern looks wrong, or two patterns coexist
   with no declared target. Then re-run with `--profile`. If nobody can
   answer (a non-interactive or CI run), take the pattern of the feature's
   neighbours, list the assumption in your final message, and write.
4. **Write**: add `--write`. Existing files are listed as `skipped … (exists, not
   overwritten)`. If the feature folder already exists the script stops (exit 2)
   unless you pass `--force-dir`, which adds only the missing files.
5. **Run the printed commands**, in order: `flutter pub add …` for missing
   dependencies, `dart run build_runner build -d` for MVN and Riverpod (the
   `*.g.dart` parts don't exist until then), then `dart analyze <paths>` and
   `flutter test <paths>`. Expect zero analyzer errors or warnings and green
   tests, because the templates are compile-checked against real projects.
6. **Wire it up** with the snippet under `== NEXT STEPS`: a route, plus
   `ProviderScope`, `RepositoryProvider`, `ChangeNotifierProvider` or a `GetPage`
   binding at the composition root, and the shared HTTP client created once
   there (`createHttpClient()`, or `Get.put(ApiClient())` for GetX).
7. **Fill in the TODOs.** The script prints the count. They mark the parts only
   you can write: the real fields of the entity, model and DTO (keep the
   `fromJson` shape check); the endpoint path in the source; the https base URL
   and the auth interceptor in the shared HTTP client; extra failure mapping in
   the repository; and localized, user-facing error text. The wording follows
   `flutter-secure-defaults` › `secure-scaffold-checklist.md` §10, so filling
   them in keeps the defaults.
8. **Check once, at the end, with one command:**
   `bash <skills-dir>/dart-flutter-review/scripts/review.sh <project-root> --diff HEAD --findings-only`.
   It runs every checker in the suite and prints only what is left at low or
   above (plus analyzer errors and warnings), each with its fix. Fix those and
   run it again. Don't run the checkers one by one: each run adds a turn and
   its whole output to the context, which is what makes a feature expensive.

### The screen's cross-cutting rules (no need to load the specialists)

The generated code already follows these. Keep them as you fill in the UI,
and you won't need to load the performance, design-system, accessibility,
adaptive-layout, networking or i18n skills to write a standard feature. Load
one only when the request is about that area itself, or when step 8 reports
a finding whose note you can't act on.

- **Lists:** `ListView.builder` / `GridView.builder` / slivers for data. For
  pagination, fetch the next page from the logic holder behind an in-flight
  guard (Bloc: a `droppable()` transformer).
- **Images:** set `cacheWidth` (or `memCacheWidth`) to the display size in
  list items, and give each a `semanticLabel`, or `excludeFromSemantics` when
  it is decorative.
- **Theme:** colours from `Theme.of(context).colorScheme`, text from
  `textTheme`, no `Color(0x…)` or `fontSize:` literals. Dark mode then comes
  for free.
- **Semantics:** a `tooltip` on every `IconButton`, `Semantics(button: true,
  label:)` on custom tappables, targets of at least 48 dp, and no fixed height
  around text.
- **Layout:** the width a widget gets (`LayoutBuilder`) or the window size
  class picks one pane or two. Logic never reads the screen size, and keep the
  selected item in the view or logic so it survives a resize.
- **Network:** one shared client with timeouts, injected into the remote
  source. The repository maps errors to the project's `Failure`.
- **Text:** user-facing strings through the project's l10n (`AppLocalizations`),
  never literals in widgets.
- **Tests (no need to load `flutter-testing`):** extend the generated tests to
  cover what you filled in. Use fakes behind the contracts, not mocks, and no
  real network or delays.
  - **The repository** over a fake source: the success path, and each error
    mapped to its `Failure`.
  - **The logic holder** (notifier, view model or bloc): loading, then data,
    empty or error. For pagination, test that the next page is appended, that
    the in-flight guard drops a second request, and that a failed page keeps
    the list.
  - **The screen:** one widget test per state. For two panes, test both size
    classes (`tester.view.physicalSize`, then `addTearDown(tester.view.reset)`).
  - **Labels:** find controls by their label (`find.bySemanticsLabel`), so the
    test also checks accessibility.

Exit codes: `0` means the plan was printed or the files were written. `2` means
a usage or environment error: no pubspec, an invalid name, an unsupported or
undetectable pattern, or a feature that already exists.

## CLI

```text
python3 -I scripts/scaffold.py <project-root> <feature_name>
    [--profile auto|mvn|mvvm|bloc|cubit|getx|provider|riverpod]
    [--clean]            add domain/ entities + use cases where the pattern lacks them
    [--entity <Name>]    UpperCamel domain object name (default: from the feature)
    [--write]            create the files (never overwrites)
    [--force-dir]        allow adding files to an existing feature folder
```

Feature names must be snake_case (`order_history` → `OrderHistory`). Dart
keywords and names that would collide with core types (`state`, `error`,
`widget`, `test`) are rejected with a suggestion.

## Profiles, conventions and what is left out

The dry run already lists every file it will write. For the per-profile file
lists, how conventions are inferred and what the scaffold deliberately does not
generate, read `references/profiles.md`.

## Secure by default

The templates follow the secure scaffold checklist, rules S-1 to S-33
(`../flutter-secure-defaults/references/secure-scaffold-checklist.md`), for
every profile, with and without `--clean`. Every generated feature guarantees:

- **One configured client, injected.** The source receives the app's HTTP
  client (Dio, or GetConnect for GetX) through its constructor or provider. It
  never builds `Dio()` or sets `BaseOptions`, so it can't skip the timeouts or
  the auth interceptor. Paths are relative (`'/orders'`); the https base URL and
  the timeouts live in the shared client (S-5, S-9, S-27, S-28).
- **No auth in features.** Nothing outside the shared client touches headers.
  The auth interceptor is a TODO there, because the scheme is app-specific (S-6).
- **Validated JSON.** `fromJson(Object? json)` pattern-matches the shape and
  throws `FormatException` on a mismatch. There are no `as` casts over
  untrusted JSON, and the source checks that the payload is a list (S-14).
- **Typed failures.** The repository maps transport errors
  (`DioException`, a GetConnect error response, `FormatException`) to a
  `Failure` that carries no URL, headers or server text. MVVM returns it in a
  `Result` (S-11).
- **User-safe errors.** Error state holds the `Failure`, never `e.toString()`.
  The view maps it to fixed text in one `_failureMessage` function, ready for
  localization, with a retry action (S-18, S-21, S-22, S-24).
- **Nothing logged.** No `print`, no logger and no HTTP logging interceptor.
  The shared client says where debug-only logging may go (S-1, S-8, S-10, S-29).
- **Nothing risky by default.** No certificate overrides, `String.fromEnvironment`,
  `http://` URLs, secrets, storage, WebViews, `launchUrl` or `HydratedBloc`
  (S-2, S-4, S-13, S-20, S-26, S-30). Tests use obviously fake data and
  check that a transport error becomes a typed failure (S-32, S-33).

The skill's tests enforce this: each profile and layout passes
`check_secure_defaults.py`, `check_errors.py` (nothing in the generated files),
`check_forms.py` and `arch_check.py` with zero findings, the generated files
get zero findings from `check_performance.py`, `check_persistence.py`,
`check_networking.py`, `check_firebase.py`, `check_platform.py`, `check_design_system.py`, `check_adaptive.py` and `check_accessibility.py` (clean by default: lazy
lists, theme colours, labelled buttons), plus greps for the
checklist rules the checkers can't see. If the project already configures a
client or declares a `Failure` type, the plan prints a `note:`. Inject that
client instead, so there's never a second, unauthenticated one (S-31).

## Notes

- A plain-Riverpod app with three or more `*Notifier extends _$X` classes looks
  like MVN to the checker. Declare `riverpod` in the project instructions file
  and pass `--profile riverpod`.
- Projects on `package:http` instead of Dio get a `note:`. The templates inject
  Dio, so swap the client type in the source and the shared client.
- GetX, Bloc and Provider versions differ in small APIs. The templates target
  current stable releases (flutter_bloc 9, get 4.7, provider 6, Riverpod 3).
  On Riverpod 2.x, regenerate with the 2.x generator and check the provider
  names it prints.

## Related skills

- `flutter-architecture`: detection, each pattern's rules, and the checker this
  skill runs (if your agent doesn't auto-load skills, read
  `../flutter-architecture/SKILL.md`). If it isn't installed, the script falls
  back to a minimal built-in scan and says so in `profile source:`.
- `dart-naming`: role names per architecture, which the templates follow
  (`../dart-naming/SKILL.md`, §12 of its reference).
- `flutter-testing`: grow the generated test skeletons
  (`../flutter-testing/SKILL.md`).
- `flutter-error-handling`: the failure flow each profile follows, and how to
  grow the `Failure` set (`../flutter-error-handling/SKILL.md`,
  `../flutter-error-handling/references/error-flow-by-architecture.md`).
- `flutter-secure-defaults`: the checklist the templates follow, and the token
  source and auth interceptor to add to the shared client
  (`../flutter-secure-defaults/SKILL.md`).
- `dart-flutter-best-practices`, `flutter-ui-practices`: for the code you write
  into the TODOs. `dart-flutter-review`: review the finished feature.
