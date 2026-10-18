# flutter-release: review checklist and finding examples

Moved out of `SKILL.md` so writing code doesn't load it: read this file
when you review code in this area, or when `dart-flutter-review` sends
you here. Paths are relative to the skill folder.

## REVIEW checklist

Script rules (`REL-0xx`, full detail in `references/rules.md`):

| ID | Name | Default severity | What it catches |
|---|---|---|---|
| REL-001 | release-signed-with-debug-key | High (Info in samples or as a missing-key fallback) | `buildTypes.release` signed with `signingConfigs.debug` |
| REL-002 | signing-file-not-ignored | High (Low when only the ignore pattern is missing) | a keystore, `key.properties`, `.p12`, `.p8` or profile no `.gitignore` covers |
| REL-003 | placeholder-application-id | Medium (Info in samples) | `applicationId` or the Runner bundle id still `com.example.*` |
| REL-004 | flavor-mismatch | Medium (Low for an orphan entrypoint) | Android flavors, iOS schemes and `main_<flavor>.dart` disagree |
| REL-005 | environment-by-build-mode | Medium | base URL, host or environment chosen by `kDebugMode`/`kReleaseMode` |
| REL-006 | flavor-read-outside-root | Low | `appFlavor`, `String.fromEnvironment('FLAVOR')`, `FlavorConfig` read in features, logic or data |
| REL-007 | debug-switch-left-on | Medium (Low for debug-only switches) | `showPerformanceOverlay: true`, checkerboarding, `debugPaintSizeEnabled = true` |
| REL-008 | target-sdk-below-play-minimum | Medium (Info in samples) | a literal `targetSdk` below Play's current requirement |
| REL-009 | usage-description-missing | Medium | a permission plugin without its `NS…UsageDescription` |
| REL-010 | pr-target-runs-untrusted-code | High | `pull_request_target` checks out the PR head and runs it |
| REL-011 | secret-printed-in-ci | High | `echo`/`printf` of a secret that reaches the log |
| REL-012 | signing-key-exposed-in-ci | High (Low on a persistent runner) | a decoded key inside an uploaded artifact, or left on a self-hosted runner |

Reading-level findings (`REL-<slug>`; the checker can't see these):

| ID | Severity | Look for |
|---|---|---|
| REL-build-number-reused | Medium | no `+build` in `version:` and no CI `--build-number`; a second upload is rejected |
| REL-no-symbols-upload | Medium | `--split-debug-info` symbols never uploaded, so release stack traces are unreadable |
| REL-config-in-features | Medium | per-flavor values scattered over feature files instead of one `AppConfig` |
| REL-version-code-hardcoded | Low | `versionCode` / `CURRENT_PROJECT_VERSION` set by hand |
| REL-flutter-unpinned | Low | CI on a floating `stable` or `latest` Flutter |
| REL-ci-permissions | Low | a deploying workflow without a top-level `permissions:` block |
| REL-privacy-manifest | Low | own required-reason API use without `ios/Runner/PrivacyInfo.xcprivacy` |
| REL-no-staged-rollout | Low | straight to 100% with nobody watching crash-free rate |

**Don't report here (cross-reference instead):**
- hard-coded secrets, secrets in `--dart-define` defaults, `.env` assets or
  envied: SEC-008/009; obfuscation and `--split-debug-info` missing from a
  release command: SEC-012; HTTP loggers in release: SEC-005; cleartext URLs:
  SEC-003 (all `flutter-secure-defaults`)
- `debugLogDiagnostics: true`: NAV-011; a base URL repeated across sources:
  NET-008; `print`: the `avoid_print` lint
- `android:debuggable`, `allowBackup`, ATS exceptions, pinning, RASP:
  `flutter-security-audit` (`scan.sh`), if installed
- the PR review gate: `dart-flutter-review`

**When not to flag:**
- A sample or example signed with the debug key under `com.example` (info).
- `main_development.dart` / `main_staging.dart` with `-t` and no platform
  flavors (compass_app): entrypoints without flavors are a valid design.
- A debug-key fallback for contributors without the keystore (info; prefer
  failing the build).
- Build-mode switches that aren't environments: `kDebugMode ? 12 : 18`, a
  crash reporter disabled in debug, a logger added in `if (kDebugMode)`.
- `pull_request_target` workflows that only label, comment or read the base.
- `echo "$KEY" | base64 --decode > file`, which never reaches the log.

## Finding examples

Use the suite's finding format (`dart-flutter-review` merges them):

```markdown
### [HIGH] pull_request_target workflow runs the PR's code with secrets
- id: REL-010
- where: .github/workflows/pr.yml:12
- evidence: `ref: ${{ github.event.pull_request.head.sha }}` followed by `run: flutter test` with `API_TOKEN: ${{ secrets.API_TOKEN }}`
- rule: never execute PR code in pull_request_target (flutter-release › rules.md REL-010)
- why: any PR author can change a test or a build hook and read API_TOKEN and the write GITHUB_TOKEN
- fix: |
    on: pull_request          # no secrets, read-only token
- confidence: confirmed

### [MEDIUM] Staging chosen by build mode
- id: REL-005
- where: lib/core/network/endpoints.dart:4
- evidence: `kReleaseMode ? 'https://api.shop.example.com' : 'https://staging.shop.example.com'`
- rule: choose environments per flavor or define file (flutter-release › flavors-and-environments.md §4)
- why: profile builds hit production and QA can't run a release build against staging
- fix: |
    // main_staging.dart
    runApp(ProviderScope(overrides: [appConfigProvider.overrideWithValue(const AppConfig(apiBaseUrl: 'https://staging.shop.example.com'))], child: const App()));
- confidence: confirmed
```

Open the report with one line naming the profile, the platforms and the
release setup (`bloc, android + ios, flavors development/production, signed in
CI via codemagic`). Report a pipeline-wide issue (for example, Flutter
unpinned in every workflow) **once**, with a few locations.
