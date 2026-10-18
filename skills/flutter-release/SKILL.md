---
name: flutter-release
description: Get a Flutter app from the repo to Google Play and the App Store safely, judged by the app's own architecture. Covers flavors and environments (productFlavors, iOS schemes, main_flavor.dart, --dart-define-from-file) with one AppConfig injected at the root, upload keystore and key.properties kept out of git, Play App Signing, iOS signing in CI, build numbers, release build flags, app ids, target SDK, usage strings, CI/CD in GitHub Actions, Codemagic and Fastlane (pinned Flutter, secrets, pull_request_target), staged rollouts and release checklists. Ships a REL checker. Use it whenever someone sets up flavors, signing, a release build or a deploy workflow, bumps the version, or asks "is this ready for the store", even if nobody says "release". For secrets load flutter-secure-defaults, for obfuscation and hardening flutter-security-audit, for the PR review gate dart-flutter-review.
license: MIT
metadata:
  author: abdelrahman-abied
  version: "1.7.0"
  suite: flutter-pro-skills
---

# Flutter release

Release problems surface at the worst moment: an upload rejected for a debug
signature or a `com.example` id, a build number Play has already seen, a
profile build that talks to production because the environment was chosen by
`kReleaseMode`, a staging flavor that only exists on Android, a keystore in
git, or a CI job that hands your signing secrets to whoever opens a pull
request. This skill sets the release path up once, the same way in every
architecture, and checks it on every review.

The core split holds in every pattern:

- **One list of flavors**, mirrored on Android (`productFlavors`), iOS
  (schemes and `Debug-/Release-/Profile-<flavor>` configurations) and
  `lib/main_<flavor>.dart`.
- **One `AppConfig`**, built at the composition root (`main_*.dart`,
  `bootstrap`, `app/`, `di/`) from the flavor or `--dart-define-from-file`,
  and injected. The data layer receives `baseUrl` and keys; logic and views
  never branch on the flavor or the build mode.
- **Signing material never enters the repository.** The upload keystore,
  `key.properties`, `.p12`, `.p8` and profiles live in a password manager and
  the CI secret store.
- **The pipeline is code**: a pinned Flutter, least-privilege tokens, secrets
  only through `env:`, keys in a temp folder, CI-derived build numbers, and
  staged rollouts watched by someone.
- **Secure by default**: no secrets in builds (`flutter-secure-defaults` owns
  that), no keys in artifacts or logs, no untrusted code next to secrets.

## Workflow

### 1. Detect the architecture and the release setup

Check your agent's project instructions file (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursor/rules/…`, `.github/copilot-instructions.md`) for a
declared pattern, flavor names or release process. A declared convention
wins. Then run the checker. It is read-only, uses only the Python standard
library, and needs no Flutter SDK, Gradle or Xcode:

```bash
python3 -I <skill-dir>/scripts/check_release.py <project-root>                     # text report
python3 -I <skill-dir>/scripts/check_release.py <project-root> --json              # schema flutter-pro-skills/release@1
python3 -I <skill-dir>/scripts/check_release.py <project-root> --files changed.txt # diff review
python3 -I <skill-dir>/scripts/check_release.py <project-root> --profile bloc      # declared pattern wins
```

The CLI is `check_release.py <project-root> [--json] [--files
<list-file-or-comma-list>] [--profile auto|mvn|mvvm|bloc|mvc|getx|provider|riverpod|setstate]
[--max n]`. It exits `0` whenever a report is produced and `2` on a usage
error. Besides `lib/`, it reads the Android Gradle files, the Xcode project,
schemes, xcconfigs and `Info.plist`, `pubspec.yaml`, `.gitignore` files,
GitHub workflows, `codemagic.yaml` and fastlane folders. In a monorepo it
also reads the root workflows that mention the project's folder, reported
with a `../` path. It takes the profile and file roles from the
`flutter-architecture` checker (`../flutter-architecture/scripts/arch_check.py
--json`, or `$FPS_ARCH_JSON` when the review already ran it); without that
sibling it falls back to path-based detection and says so.

```text
== RELEASE
  profile: bloc (arch_check, confidence high)
  classification: arch_check files[]
  scanned: 108 Dart files; platforms: android, ios; 3 CI files; flavors: development, production; release intent: release signingConfig, flavors, codemagic
  [REL-004] flavor-mismatch (medium) x1 — Flavors disagree between Android productFlavors, iOS schemes and lib/main_<flavor>.dart. ...
      android/app/build.gradle.kts:52  create("staging") {   [Android flavor "staging" has no iOS scheme ...]
```

**App-aware.** The `scanned:` line says whether this is an app with release
intent (a release signing config, flavors, fastlane, codemagic or a release
workflow) or a sample (none of those, or inside an `examples/` folder). In a
sample, the store-readiness rules (REL-001, REL-003, REL-008) are graded info:
a debug-signed `com.example` sample is correct as a sample. A pure Dart
package without `android/` or `ios/` skips the platform rules and says so.

### 2. Place each piece by the pattern

The patterns differ only in how the config reaches the data layer:

| Piece | MVN | MVVM | Bloc / Cubit | Clean | Provider | GetX | Riverpod |
|---|---|---|---|---|---|---|---|
| build `AppConfig` | `main_<flavor>.dart` | `main_<flavor>.dart` (compass_app) | `main_<flavor>.dart` → `bootstrap(config)` | DI module | `main_<flavor>.dart` | initial binding | `main_<flavor>.dart` |
| inject it | `ProviderScope(overrides: [appConfigProvider.overrideWithValue(config)])` | root provider list → API service | `RepositoryProvider` of repositories built from it | constructor of the remote data source | `Provider<AppConfig>.value` | `Get.put(config, permanent: true)` | same override as MVN |
| read it | the keepAlive client provider in `core/network` | API service | API client in `bootstrap` | data source | services | services | client-building providers |
| never | notifiers, use cases, views | view models, views | blocs, widgets | domain | ChangeNotifiers | controllers, views | UI providers |

With get_it, `registerSingleton<AppConfig>(config)` in `main_<flavor>.dart`
before `runApp`, resolved only where clients are built.

Read `references/flavors-and-environments.md` for the platform setup and the
injection code, `references/signing-and-versioning.md` for keystores, iOS
signing, build numbers and release commands, `references/store-requirements.md`
before a first upload, `references/ci-cd.md` before writing or reviewing a
release workflow, and `references/release-checklist.md` to run a release.

For step-by-step setup (creating flavors, a keystore, an archive in Xcode),
defer to the docs.flutter.dev deployment and flavors guides and, if your
agent has them installed, the official `flutter/agent-plugins` or
`dart-lang/skills` recipes. This skill adds the architecture placement, the
secure defaults and the review checks.

### 3. Write with the checklist below, then run the checker

Read the file behind every hit before calling it `confirmed`.
`references/rules.md` lists each rule's detection and known false positives.
Suppress a deliberate case with a reason, on the reported line or the line
above: `// rel-ignore: REL-001 internal sideload build` in Dart, Gradle or
xcconfig files, `# rel-ignore: REL-012 ephemeral larger runner` in YAML, or
`rel-ignore-file:` for a whole file.

## WRITE checklist

**Flavors and environments**
1. DO keep one list of flavors on Android, iOS and `lib/main_<flavor>.dart`
   (REL-004), each with its own id suffix, name and backend project.
2. DO choose the environment by flavor or `--dart-define-from-file`, never by
   `kDebugMode`/`kReleaseMode` (REL-005). Profile builds must be able to hit
   staging.
3. DO read the flavor once at the composition root and inject values
   (REL-006); give UI a fact (`showDebugMenu`), not the flavor name.
4. DON'T put secrets in defines, define files or `.env` assets; they ship in
   the app (SEC-009, `flutter-secure-defaults`).

**Signing and versioning**
5. DO sign `release` with an upload key from `key.properties` or CI secrets,
   and enrol in Play App Signing (REL-001). PREFER failing the build to
   falling back to the debug key.
6. DON'T commit `*.jks`, `*.keystore`, `key.properties`, `*.p12`, `*.p8`,
   `*.mobileprovision`; keep the `flutter create` ignore patterns (REL-002).
7. DO use `version: x.y.z+N` with N increasing on every upload, derived in CI
   (`--build-number`); keep Gradle and Xcode on `flutter.versionCode` and
   `FLUTTER_BUILD_NUMBER`.
8. DO build releases with `flutter build appbundle|ipa --release
   --split-debug-info=<dir>` and upload the symbols to the crash reporter;
   obfuscation is SEC-012's and `flutter-security-audit`'s call.

**Store readiness**
9. DO set the final `applicationId` and bundle id before the first upload,
   never `com.example` (REL-003).
10. PREFER `targetSdk = flutter.targetSdkVersion`; a hard-coded number below
    Play's current level is rejected (REL-008).
11. DO add a user-facing `NS…UsageDescription` for every permission a plugin
    needs (REL-009), and a `PrivacyInfo.xcprivacy` when your own code needs one.
12. DON'T leave the performance overlay, checkerboarding, the semantics
    debugger or `debugPaint*` switched on (REL-007).

**CI/CD**
13. DO pin Flutter (`flutter-version`, `flutter-version-file`, `.fvmrc`,
    Codemagic `flutter: 3.x.y`) and third-party actions; cache pub.
14. DO set top-level `permissions: contents: read` and keep store secrets in a
    protected environment.
15. DON'T run PR code in `pull_request_target` (REL-010); build PRs with
    `pull_request`.
16. DON'T echo secrets (REL-011); pass them through `env:` into files.
17. DO decode keys into `$RUNNER_TEMP`, upload only build outputs, and delete
    keys and keychains in an `if: always()` step (REL-012).
18. DO gate PRs with the suite's review action
    (`../dart-flutter-review/references/ci.md`) in its own workflow, not in the
    release job.

**Rollout**
19. DO ship through internal testing and TestFlight, then a staged rollout or
    phased release with someone watching crash-free rate and ANRs
    (`references/release-checklist.md`).
20. DO wire crash reporting through the global handlers before the first
    release (`flutter-error-handling`).

## Reviewing

For a review, read `references/review.md`: the review checklist (every
finding ID with its severity and how to confirm it) and worked finding
examples in the suite's format. Writing code doesn't need it.

## Related skills

These assume the suite is installed as sibling folders. If your agent doesn't
auto-load skills, read the path given. If a sibling is missing, carry on and
say which check you skipped.

- **`flutter-secure-defaults`** for secrets in builds and defines, loggers,
  cleartext and the release obfuscation flag (SEC-003/005/008/009/012).
  Fallback: `../flutter-secure-defaults/SKILL.md` and
  `../flutter-secure-defaults/references/secrets-and-config.md`.
  **`flutter-security-audit`** (installed separately) for release hardening,
  obfuscation depth, manifests, plists, pinning and RASP.
- **`flutter-architecture`** for detecting the pattern, the composition root
  and `AP-hardcoded-config-in-sources`. Fallback:
  `../flutter-architecture/SKILL.md`.
- **`flutter-networking`** for the one configured client that receives the
  base URL (NET-008 for duplicated hosts). Fallback:
  `../flutter-networking/SKILL.md`.
- **`flutter-error-handling`** for global error handlers and crash reporting
  before a rollout. Fallback: `../flutter-error-handling/SKILL.md` and
  `../flutter-error-handling/references/global-handlers.md`.
- **`flutter-navigation`** for deep links you verify before a release
  (NAV-011 for router logging). Fallback: `../flutter-navigation/SKILL.md`.
- **`dart-flutter-review`** merges REL findings into its report and owns the
  PR review gate. Fallback: `../dart-flutter-review/SKILL.md` and
  `../dart-flutter-review/references/ci.md`.

## References

| File | Read it when |
|---|---|
| `references/review.md` | reviewing: the checklist with every ID, severity and fix, and finding examples |
| `references/flavors-and-environments.md` | adding flavors on Android and iOS, choosing flavors vs `--dart-define-from-file` vs entrypoints, building and injecting `AppConfig` in MVN, MVVM, Bloc, Clean, Provider, GetX, Riverpod or get_it |
| `references/signing-and-versioning.md` | creating the upload keystore, `key.properties`, Play App Signing, iOS certificates and profiles, version and build numbers, release build commands |
| `references/store-requirements.md` | preparing a first upload: ids, target SDK, purpose strings, privacy manifest, export compliance, data-safety forms |
| `references/ci-cd.md` | writing or reviewing GitHub Actions, Codemagic or Fastlane release pipelines; `pull_request_target`; keys in CI |
| `references/release-checklist.md` | running a release, staged rollouts and phased releases, watching crash-free rate, halting |
| `references/rules.md` | every REL rule: detection, why, fix, false positives; the reading-level slugs; what's checked elsewhere; calibration |
