# REL rules: what the checker reports, and why

`scripts/check_release.py` is static and read-only. It needs only the Python
standard library: no Flutter SDK, Gradle, Xcode or `pub get`. Every hit is a
candidate, so read the file before you call a finding `confirmed`. Each rule
lists the false positives it knows about and how to suppress a deliberate case.

The checker judges what no other checker in the suite sees: the release build
configuration (Gradle, Xcode, `Info.plist`, `.gitignore`), the way flavors and
environments reach the code, and the CI that builds and signs the app. Where a
concern already has an owner, REL cross-references it instead (section 4).

## Contents

1. How the checker reads the project
2. REL-001 … REL-012
3. Reading-level findings (REL-<slug>)
4. Not checked here (cross-references)
5. Calibration

## 1. How the checker reads the project

- **Files.** Every non-generated `.dart` file under `lib/` that `arch_check`
  lists in `files[]` (barrels skipped), plus:
  - `android/app/build.gradle` or `build.gradle.kts` (Groovy and Kotlin DSL)
  - `ios/Runner.xcodeproj/project.pbxproj`, its shared schemes
    (`xcshareddata/xcschemes/*.xcscheme`), `ios/**/*.xcconfig` and
    `ios/Runner/Info.plist`
  - `pubspec.yaml` and every `.gitignore` from the project up to the
    repository root
  - `.github/workflows/*.yml|yaml`, `codemagic.yaml`, and the presence of
    `fastlane/`, `android/fastlane/` or `ios/fastlane/`
  - in a monorepo, the repository root's workflows and `codemagic.yaml` when
    they mention the project's folder (for example `working-directory: mobile`).
    Their findings carry a `../` path, and `--files` accepts that path.
- **Signing files** (`*.jks`, `*.keystore`, `*.p12`, `*.p8`,
  `*.mobileprovision`, `key.properties`) are found by walking the project,
  skipping `build/`, `.dart_tool/`, `Pods/` and nested packages. Their content
  is never read. `debug.keystore` is ignored, because the Android debug key is
  public by design.
- **YAML** is read with a small line-based parser (block maps and lists,
  block scalars, flow lists, anchors). It needs no YAML library. A file it
  can't parse is skipped, never reported.
- **Missing platform folders.** A pure Dart package, or a web or desktop-only
  app, has no `android/` or `ios/`. The platform rules are skipped and
  `stats.platform_rules` says so. Dart and CI rules still run.
- **App-aware (sample or app).** `stats.release_intent` lists the signals
  found: a release `signingConfig`, flavors, fastlane, codemagic, a release
  workflow (one that touches keystores, profiles, fastlane or a store upload
  action), and a changed `applicationId` or bundle id. A project is a
  **sample** when it sits inside an `example/`, `examples/`, `sample/` or
  `samples/` folder, or when none of the store signals is present (a changed
  `applicationId` alone isn't enough; see Calibration). In a sample the
  store-readiness rules (REL-001, REL-003, REL-008) are graded **info** and the
  note says why. The other rules keep their severity, because a leaked key or
  a crash on a permission prompt is a bug in any app.
- **Placement notes.** REL-005 and REL-006 notes end with the injection point
  for the detected profile (`MVN: …`, `Riverpod: …`, `MVVM: …`, `Bloc: …`,
  `Provider: …`, `GetX: …`, and `get_it: …` when the project uses it).
  `--profile` overrides the detected pattern. The other rules carry store or
  CI specifics instead.
- **Suppression.** `// rel-ignore: REL-00x <reason>` (Dart, Gradle, xcconfig)
  or `# rel-ignore: REL-0xx <reason>` (YAML, properties, fastlane), on the
  reported line or the line above. `rel-ignore-file:` anywhere in the file
  covers the whole file. The reason is kept in the JSON `suppressed` list.

## 2. Rules

### REL-001 release-signed-with-debug-key

**High** · **Info** in samples, and when the debug key is only a fallback for
a missing keystore · all profiles

**Detects:** inside `buildTypes { release { … } }` (also `getByName("release")`),
`signingConfig signingConfigs.debug` or `signingConfig =
signingConfigs.getByName("debug")`. It's a fallback when the line is a ternary
or elvis, or sits inside an `if`/`else`.

**Why:** Play rejects debug-signed uploads. Debug keys differ per machine, so
two developers' "release" builds can't update each other, and the build you
tested isn't the one you can ship. `flutter create` leaves this line in place
with a TODO, so it survives into real apps.

```groovy
// Bad
buildTypes { release { signingConfig signingConfigs.debug } }

// Good: key.properties is outside git (CI writes it from secrets)
signingConfigs {
    release {
        keyAlias keystoreProperties['keyAlias']
        keyPassword keystoreProperties['keyPassword']
        storeFile keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
        storePassword keystoreProperties['storePassword']
    }
}
buildTypes { release { signingConfig signingConfigs.release } }
```

**Fallback (info):** `signingConfig hasKey ? signingConfigs.release :
signingConfigs.debug` lets contributors build release locally. Prefer failing
the release task when the key is missing, so CI can never publish a
debug-signed artifact by accident.

**False positives:** none known with release intent. Suppress a deliberate
sideload-only build: `// rel-ignore: REL-001 internal QA build, never uploaded`.

### REL-002 signing-file-not-ignored

**High** for a signing file on disk that no `.gitignore` covers · **Low** when
Gradle reads `key.properties` but no `.gitignore` covers `key.properties` or
`*.jks` · all projects

**Why:** anyone who can read the repository (or its history, a fork, a CI
cache) can sign updates as you. An Android upload key can be reset through
Play App Signing; an iOS distribution certificate must be revoked.

**Fix:** add the `flutter create` patterns to `android/.gitignore`
(`key.properties`, `**/*.jks`, `**/*.keystore`) and to the root `.gitignore`
(`*.p12`, `*.p8`, `*.mobileprovision`). Then `git rm --cached` the file,
rewrite history if it was pushed, and rotate the key.

**False positives:** a placeholder test keystore committed on purpose
(suppression can't go inside a binary, so suppress in `--files` review, or
name it `debug.keystore` if it is a debug key). The checker can't see whether
a file is already tracked; "not ignored" means `git add .` would commit it.

### REL-003 placeholder-application-id

**Medium** · **Info** in samples

**Detects:** `applicationId` (or `namespace` when there is no `applicationId`)
in `android/app/build.gradle(.kts)`, and the Runner target's
`PRODUCT_BUNDLE_IDENTIFIER` in `project.pbxproj` (resolved through an xcconfig
when it is `$(VAR)`), equal to `com.example` or starting with `com.example.`.
Test targets are skipped.

**Why:** both stores refuse `com.example`. The id is permanent after the
first upload: Play listings, Play App Signing, keychain groups and push
certificates are tied to it.

**Fix:** a reverse domain you control, the same on both platforms unless you
have a reason. A changed `namespace` isn't required; it is the Kotlin/Java
package, not the store id.

### REL-004 flavor-mismatch

**Medium** for an Android flavor with no iOS scheme, or the reverse · **Low**
for a `lib/**/main_<x>.dart` that matches no flavor

**Detects:** Android `productFlavors` children (`dev { }`, `create("dev")`,
`register("dev")`), iOS shared schemes other than `Runner*` and app-extension
targets (or `Debug-<x>` build configurations when there are no shared
schemes), and `main_<x>.dart` entrypoints. Names compare case-insensitively.
For entrypoints, `dev`/`development`, `prod`/`production` and
`stg`/`stage`/`staging` count as the same.

**Why:** `flutter run --flavor staging` needs a Gradle flavor and an Xcode
scheme of that name. A missing one fails only on the platform nobody tried. An
orphan entrypoint usually means a flavor that was renamed or removed.

**Not reported:** entrypoints when the app has no flavors at all (compass_app
uses `main_development.dart` and `main_staging.dart` with `-t`, which is
fine), extension schemes, and a localized `Runner (French)` scheme.

### REL-005 environment-by-build-mode

**Medium** · all profiles

**Detects:** `kDebugMode`/`kReleaseMode`/`kProfileMode` (or
`bool.fromEnvironment('dart.vm.product')`) in a ternary whose **both**
branches look like environments (URL literals, names containing url, uri,
host, endpoint, server or domain, or `prod`/`staging`/`dev` values). Also an
`if (kDebugMode) { … }` that assigns a URL or a url-named field.

**Why:** build mode isn't environment. Profile builds (what you use to
measure performance) silently hit production, a release build can't be
pointed at staging for QA or a store review account, and the decision is
spread through code instead of made once.

```dart
// Bad
final baseUrl = kReleaseMode ? 'https://api.acme.com' : 'https://staging.acme.com';

// Good: main_staging.dart / main_production.dart, or --dart-define-from-file=config/prod.json
void main() => bootstrap(const AppConfig(baseUrl: 'https://staging.acme.com'));
// or: AppConfig(baseUrl: const String.fromEnvironment('API_BASE_URL'))
```

**Profile notes:** MVN/Riverpod override `appConfigProvider` in
`ProviderScope(overrides: …)`; MVVM passes `AppConfig` to the API service in
the root provider list; Bloc's `bootstrap(config)` builds the client and hands
repositories down with `RepositoryProvider`; GetX uses `Get.put(config,
permanent: true)` in the initial binding; get_it registers it before `runApp`.

**Not reported:** numbers or durations by build mode (`kDebugMode ? 12 : 18`),
a feature switched off in debug (`!kDebugMode ? dsn : ''`), and loggers added
in `if (kDebugMode)`.

### REL-006 flavor-read-outside-root

**Low** · all profiles

**Detects:** `appFlavor`, `F.appFlavor` (flutter_flavorizr), `FlavorConfig.instance`,
or `String.fromEnvironment('FLAVOR'|'ENV'|'ENVIRONMENT'|'APP_ENV'|…)` in a view,
widget, logic, domain, source or repository file. The composition root is
exempt: `lib/main*.dart`, `lib/app/`, `lib/di/`, `bootstrap`, `config/`,
`env/`, `flavors/`, and files named `flavors.dart`, `app_config.dart`,
`env.dart`.

**Why:** a hidden global per read site. Tests can't override it, and every new
environment means hunting branches through features. It is the
environment case of `AP-hardcoded-config-in-sources` (flutter-architecture).

**Fix:** read the flavor once in `main_<flavor>.dart` or `bootstrap`, build
`AppConfig`, inject the specific value (`showBetaBanner`, `baseUrl`). One
finding per file.

### REL-007 debug-switch-left-on

**Medium** for `showPerformanceOverlay: true`, `checkerboardRasterCacheImages: true`,
`checkerboardOffscreenLayers: true` and `showSemanticsDebugger: true` (they
render outside debug builds) · **Low** for `debugShowMaterialGrid: true` and
`debugPaint*Enabled = true` / `debugRepaint*RainbowEnabled = true` (debug only,
but they distort every developer's screen)

**Not reported:** a value that isn't the literal `true`, a switch inside
`if (kDebugMode) { … }` or `assert(() { … }())`, and commented-out lines.
`print` belongs to the `avoid_print` lint and `debugShowCheckedModeBanner` is
cosmetic, so neither is reported.

### REL-008 target-sdk-below-play-minimum

**Medium** · **Info** in samples

**Detects:** a literal `targetSdk`/`targetSdkVersion` below
`PLAY_MIN_TARGET_SDK` (35, Google Play's requirement for new apps and updates
since 2025-08-31). Google raises the level every August, so update the two
constants at the top of the script when it does
(developer.android.com/google/play/requirements/target-sdk).

**Fix:** `targetSdk = flutter.targetSdkVersion`, which the Flutter tool keeps
current, or raise the number after reading the behaviour changes of each
skipped Android version.

### REL-009 usage-description-missing

**Medium** · all projects with `ios/Runner/Info.plist`

**Detects:** a direct dependency that always needs a purpose string, with the
key missing from `Info.plist`. Reported on the dependency line in
`pubspec.yaml`.

| Dependency | Key |
|---|---|
| `camera`, `mobile_scanner`, `qr_code_scanner(_plus)` | `NSCameraUsageDescription` |
| `local_auth` | `NSFaceIDUsageDescription` |
| `geolocator`, `location` | `NSLocationWhenInUseUsageDescription` (or the Always variant) |
| `record`, `flutter_sound` | `NSMicrophoneUsageDescription` |
| `speech_to_text` | `NSSpeechRecognitionUsageDescription`, `NSMicrophoneUsageDescription` |
| `flutter_contacts`, `contacts_service` | `NSContactsUsageDescription` |
| `photo_manager` | `NSPhotoLibraryUsageDescription` |
| `gal`, `image_gallery_saver` | `NSPhotoLibraryAddUsageDescription` |
| `flutter_blue_plus`, `flutter_reactive_ble` | `NSBluetoothAlwaysUsageDescription` |
| `health`, `device_calendar`, `app_tracking_transparency`, `nfc_manager` | their single key |

**Why:** iOS kills the app when it requests a protected resource without the
string, and App Store processing flags binaries that link the API without it.

**Not reported:** `image_picker` (the system picker needs no permission since
iOS 14) and `permission_handler` (its keys depend on Podfile macros), which
are reading-level checks. Neither are transitive dependencies.

### REL-010 pr-target-runs-untrusted-code

**High** · GitHub Actions

**Detects:** a workflow triggered by `pull_request_target` whose job checks
out `github.event.pull_request.head.*`, `github.head_ref`, `refs/pull/…` (or
runs `gh pr checkout`) and then runs a script or a local action.

**Why:** `pull_request_target` runs with the base repository's secrets and a
write token. Building the PR's code in that job lets any PR author execute
code with them (GitHub Security Lab's "pwn request").

**Fix:** build PR code under `on: pull_request` (no secrets, read-only token).
When a privileged follow-up is needed (a comment, a label), pass the results
as an artifact to a `workflow_run` job that never executes PR code.

**Not reported:** `pull_request_target` workflows that only label, comment or
check out the base (immich's labeller and auto-close workflows).

### REL-011 secret-printed-in-ci

**High** · GitHub Actions and Codemagic

**Detects:** `echo`/`printf`/`print`/`puts`/`Write-Host`/`Write-Output` of
`${{ secrets.X }}` or of an env var mapped from a secret (Codemagic: a
secret-named variable such as `CM_KEYSTORE_PASSWORD`) whose output reaches
the log: not redirected to a file, not piped (except to `tee`), or sent to
`>&2`.

**Why:** masking replaces the exact value only. A multi-line secret (a service
account JSON, a PEM), a base64 or URL-encoded copy, or a substring prints in
clear. Logs are readable by every collaborator, and on public repositories by
everyone.

**Not reported:** `echo "$X" | base64 --decode > file`, `echo "k=$X" >>
key.properties`, `echo "::add-mask::$X"`, and plain expressions such as
`${{ github.ref_name }}`.

### REL-012 signing-key-exposed-in-ci

**High** when an artifact includes the key · **Low** when the key stays on a
runner that isn't a GitHub-hosted image

**Detects:** a `run:` (or Codemagic script) line that writes a signing file
(`.jks`, `.keystore`, `.p12`, `.p8`, `.mobileprovision`, or a `key.properties`
holding `storeFile`) into the workspace, resolved through `working-directory`.
Writes under `$RUNNER_TEMP`, `$HOME`, `~`, `/tmp` and other absolute paths
are outside the workspace and fine. Then either:
- a later `actions/upload-artifact` `path:` in the same job (or a Codemagic
  `artifacts:` pattern) covers that file (`.`, `android/`, `**`), or
- the job's `runs-on` is `self-hosted` or a custom label, and no later step
  removes the file.

**Why:** artifacts can be downloaded by anyone with read access. A self-hosted
runner keeps the workspace between jobs and repositories.

**Fix:** decode into `$RUNNER_TEMP`, upload only build outputs
(`build/app/outputs/bundle/<flavor>Release/*.aab`, the `.ipa`), and delete
keys and temporary keychains in an `if: always()` step.

**False positives (low):** GitHub's larger hosted runners use custom labels
too. If yours is ephemeral, suppress with `# rel-ignore: REL-012 ephemeral
larger runner`.

## 3. Reading-level findings (REL-<slug>)

The checker can't decide these reliably. Report them from reading, in the
suite's finding format.

| ID | Severity | Look for |
|---|---|---|
| REL-build-number-reused | Medium | `version:` without `+build`, or a fixed build number, with no CI `--build-number`; the second upload is rejected as a duplicate versionCode / CFBundleVersion |
| REL-version-code-hardcoded | Low | `versionCode 12` / `CURRENT_PROJECT_VERSION` set by hand instead of `flutter.versionCode` and pubspec, so two sources of truth drift |
| REL-flutter-unpinned | Low | CI installs `channel: stable` or `flutter: latest` with no version (`flutter-version`, `flutter-version-file`, `.fvmrc`), so a release build changes when Flutter does |
| REL-ci-permissions | Low | a workflow that uses secrets or deploys with no top-level `permissions:`, so the token gets the repository default (often write) |
| REL-privacy-manifest | Low | an app with its own required-reason API use (UserDefaults, file timestamps, disk space, boot time) and no `ios/Runner/PrivacyInfo.xcprivacy`; plugins and the Flutter engine ship their own |
| REL-no-symbols-upload | Medium | `--split-debug-info` or `--obfuscate` without uploading the symbols to Crashlytics/Sentry, so release stack traces are unreadable |
| REL-no-staged-rollout | Low | production releases pushed to 100% at once with no Play staged rollout or App Store phased release, and no crash-rate gate |
| REL-config-in-features | Medium | environment values (hosts, keys, feature flags per flavor) defined in several feature files instead of one `AppConfig` |

## 4. Not checked here (cross-references)

| Concern | Owner | Why REL stays out |
|---|---|---|
| hard-coded secrets; secrets in `--dart-define` defaults, `.env` assets, envied | SEC-008 / SEC-009 (`flutter-secure-defaults`) | client-side config is never secret |
| obfuscation, and `--split-debug-info` missing from a release command | SEC-012 | REL only covers where the symbols go (REL-no-symbols-upload) |
| HTTP loggers in release | SEC-005 | |
| cleartext `http://` | SEC-003 | |
| `debugLogDiagnostics: true` | NAV-011 | |
| `android:debuggable`, `allowBackup`, ATS arbitrary loads, pinning, RASP | `flutter-security-audit` (`scan.sh`), if installed | manifest and plist hardening is an audit |
| one base URL repeated across sources | NET-008 | REL-005 is about choosing the environment |
| `print` | `avoid_print` lint | |
| the review gate in CI (fail PRs on new violations) | `dart-flutter-review` (`../dart-flutter-review/references/ci.md`, the suite's GitHub Action) | REL checks the release pipeline, not the review gate |

## 5. Calibration

Run on the suite's shared calibration pool (§24 and §29 of the suite
contracts). Each project with its own `pubspec.yaml` and `lib/` was run
separately; monorepo workflows were included when they mention the project.
Every high and medium hit was read, low and info hits too.

| App | Commit | Projects | Kind | Hits (per rule) | TP / FP |
|---|---|---|---|---|---|
| flutter/samples `compass_app` (canonical) | flutter/samples@5541c59 | 1 | sample | REL-001 ×1, REL-003 ×2 (info) | 3 / 0 |
| flutter/samples, the other projects (canonical, robustness) | flutter/samples@5541c59 | 35 | 18 samples, 16 without platform folders, 1 without `lib/` | REL-001 ×14, REL-003 ×16, REL-008 ×1 (info) | 31 / 0 |
| felangel/bloc `examples/*` (canonical) | felangel/bloc@b9be1e2 | 28 | 13 samples, 15 without platform folders | REL-001 ×1, REL-003 ×2 (info) | 3 / 0 |
| rrousselGit/riverpod `examples/*` (canonical) | rrousselGit/riverpod@87aad84 | 7 | without platform folders | none | 0 / 0 |
| flutter/news_toolkit `flutter_news_example` (canonical, real flavors) | flutter/news_toolkit@6655bbc | 1 | app (flavors, signing, codemagic) | none | 0 / 0 |
| VGVentures/io_flip | VGVentures/io_flip@964e511 | 1 | web, no platform folders | none | 0 / 0 |
| immich-app/immich `mobile` + `.github` | immich-app/immich@188d64e | 1 | app (fastlane, signing, workflows) | REL-001 ×1 (info), REL-012 ×1 (low) | 2 / 0 |
| lichess-org/mobile | lichess-org/mobile@99e1fb7 | 1 | app (fastlane, Play deploy workflow) | none | 0 / 0 |
| hiddify/hiddify-app | hiddify/hiddify-app@f26aadb | 1 | app (signing, release workflow) | REL-001 ×1 (info) | 1 / 0 |
| gskinnerTeam/flutter-wonderous-app | gskinnerTeam/flutter-wonderous-app@747b945 | 1 | sample (no store metadata in the repo) | REL-001 ×1 (info) | 1 / 0 |

**The canonical apps have no high or medium hits.** The info hits are true
positives: the samples sign release with the debug key and keep `com.example`
ids, which is right for a sample and wrong for a store build. news_toolkit's
flavors match across Gradle, Xcode schemes and `lib/main/main_*.dart`, its
release config reads the keystore from the environment, and its codemagic
config pins Flutter.

**Other true positives.** immich decodes the Android keystore into the
workspace on a runner with a custom label and never deletes it (low; it
depends on whether that runner is persistent). immich and hiddify fall back to
the debug key when the keystore is missing (info). Running the CI rules over
every workflow in the pool (about 120 files) found nothing else: the
`pull_request_target` workflows there don't check out PR code, and every
`echo` of a secret is piped or redirected to a file.

**False-positive causes fixed.** Each cause has a `calib_*` regression fixture
(fresh minimal code; no lines or names from the GPL/AGPL apps) plus a test
that the related true positive still fires.

| Cause | Seen in | Hits without the fix | Fix | Fixture |
|---|---|---|---|---|
| a changed `applicationId` (`dev.flutter.x`) counted as release intent, so sample apps signed with the debug key were high | flutter/samples (×6: animations, form_app, navigation_and_routing, platform_channels, platform_design, testing_app), wonderous | REL-001 high ×7 | a changed id alone isn't release intent; a release signing config, flavors, fastlane, codemagic or a release workflow is | `calib_samples` |
| an app inside an `examples/` folder with a signing config | (robustness) | REL-001 high | the examples folder makes it a sample | `calib_samples/examples/signed_demo` |
| debug signing as a fallback when the keystore is missing (`if/else`, ternary) | hiddify, immich | REL-001 high ×2 | graded info, with the "fail the build instead" note | `calib_hiddify`, `calib_immich` |
| a DSN switched off in debug (`!kDebugMode \|\| x ? dsn : ''`) | hiddify | REL-005 medium | both ternary branches must look like environments | `calib_hiddify` |
| numeric thresholds by build mode (`kDebugMode ? 12 : 18`) | lichess (×4) | REL-005 medium | numbers and durations are not environments | `calib_lichess` |
| app-extension and localized `Runner (…)` schemes taken for flavors | lichess, hiddify | REL-004 medium | schemes named after a native target, or starting with Runner, are skipped | `calib_lichess`, `calib_hiddify` |
| `main_timeline.page.dart` (a debug entrypoint) and `main_prod.dart` with no flavors | immich, hiddify | REL-004 low | entrypoint names are `main_<identifier>.dart`, compared only when flavors exist | `calib_immich`, `calib_hiddify` |
| `key.properties` written with `>>` on a GitHub-hosted runner | lichess, hiddify | REL-012 low | only persistent runners or artifact uploads are reported | `calib_lichess` |
| the monorepo's workflows weren't seen from `mobile/` | immich | (false negative) | root workflows that mention the project folder are read, with `../` paths | `calib_immich` (the test adds a `.git` marker to a temp copy) |
