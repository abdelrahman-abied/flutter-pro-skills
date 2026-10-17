# CI/CD for Flutter releases

A release pipeline holds the most valuable secrets you have (signing keys,
store credentials), so it gets the same care as production code. This file
covers building and shipping. Gating pull requests on review findings is a
separate job: use the suite's own GitHub Action and baseline, described in
`dart-flutter-review` (`../dart-flutter-review/references/ci.md`), and keep it
out of the release workflow.

## Contents

1. Principles
2. GitHub Actions: an Android release job
3. GitHub Actions: an iOS release job
4. `pull_request_target` and other supply-chain holes
5. Codemagic
6. Fastlane
7. Review checklist

## 1. Principles

- **Pin the toolchain.** `subosito/flutter-action` with `flutter-version:
  3.x.y` or `flutter-version-file: pubspec.yaml` (with an exact
  `environment.flutter`), or `.fvmrc`; Codemagic `flutter: 3.x.y`. A floating
  `stable` changes your release build when Flutter ships
  (REL-flutter-unpinned).
- **Pin third-party actions** to a full commit SHA (with the version in a
  comment), and let Dependabot or Renovate bump them.
- **Cache** pub (`cache: true` in flutter-action, or `~/.pub-cache`) and
  Gradle, keyed on the lock files.
- **Least privilege.** A top-level `permissions: contents: read`, widened per
  job only where needed (REL-ci-permissions). Release jobs run on tags or
  protected branches, inside a GitHub **environment** with required reviewers
  holding the store secrets.
- **Secrets only from the secret store**, passed through `env:` to the step
  that needs them. Never `echo` them (REL-011). `${{ secrets.X }}` written
  directly into `run:` is expanded into the script text; prefer `env:` and
  `"$X"`.
- **Keys live in `$RUNNER_TEMP`**, never in the workspace, never in an
  artifact, and are deleted in an `if: always()` step (REL-012).
- **Build numbers come from CI** (`--build-number=${{ github.run_number }}`).
- **Upload symbols** from `--split-debug-info` to your crash reporter in the
  same job (REL-no-symbols-upload).

## 2. GitHub Actions: an Android release job

```yaml
name: Release Android
on:
  push:
    tags: ['v*']

permissions:
  contents: read

jobs:
  android:
    runs-on: ubuntu-latest
    environment: production            # required reviewers + scoped secrets
    steps:
      - uses: actions/checkout@<sha>   # v4
      - uses: subosito/flutter-action@<sha>   # v2
        with:
          flutter-version-file: pubspec.yaml
          cache: true
      - name: Signing
        env:
          UPLOAD_KEYSTORE_B64: ${{ secrets.UPLOAD_KEYSTORE_B64 }}
          KEYSTORE_PASSWORD: ${{ secrets.KEYSTORE_PASSWORD }}
          KEY_PASSWORD: ${{ secrets.KEY_PASSWORD }}
        run: |
          echo "$UPLOAD_KEYSTORE_B64" | base64 --decode > "$RUNNER_TEMP/upload.jks"
          {
            echo "storeFile=$RUNNER_TEMP/upload.jks"
            echo "storePassword=$KEYSTORE_PASSWORD"
            echo "keyPassword=$KEY_PASSWORD"
            echo "keyAlias=upload"
          } > android/key.properties
      - run: >
          flutter build appbundle --release --flavor prod -t lib/main_prod.dart
          --split-debug-info=build/symbols --obfuscate
          --build-number=${{ github.run_number }}
      - uses: actions/upload-artifact@<sha>   # v4
        with:
          name: prod-aab
          path: build/app/outputs/bundle/prodRelease/*.aab
      - name: Clean up signing files
        if: always()
        run: rm -f "$RUNNER_TEMP/upload.jks" android/key.properties
```

Ship to a Play track with `r0adkll/upload-google-play` (pinned) or fastlane
`supply`, using a service account JSON from the secret store written to
`$RUNNER_TEMP`, starting at the internal track or a staged rollout
(`release-checklist.md`).

## 3. GitHub Actions: an iOS release job

Run on `macos-*`. Import the distribution certificate into a temporary
keychain (`security create-keychain`, `security import … -T
/usr/bin/codesign`, `security set-key-partition-list`), install profiles from
secrets or with `fastlane match`, build with `flutter build ipa
--export-options-plist=ios/ExportOptions.plist`, upload with an App Store
Connect API key (`.p8` written to `$RUNNER_TEMP` or
`~/.appstoreconnect/private_keys`), and `security delete-keychain` in an
`if: always()` step. Never upload the `.p12`, `.p8` or keychain as an artifact.

## 4. `pull_request_target` and other supply-chain holes

- `pull_request_target` runs the **base** branch's workflow with secrets and a
  write token. That's safe only while it never executes PR code. Checking
  out `github.event.pull_request.head.sha` and then running `flutter test`,
  `pub get` (which runs build hooks), a script or a local action hands the
  secrets to any PR author (REL-010). Build PRs with `on: pull_request`.
- `workflow_run` jobs that download a PR's artifacts must treat them as
  untrusted data: never execute them, and never interpolate their contents
  into `run:`.
- Untrusted text (`github.event.pull_request.title`, branch names, issue
  bodies) interpolated with `${{ }}` into `run:` is script injection. Pass it
  through `env:` and quote it.
- Self-hosted runners for public repositories run strangers' code. Keep them
  for private repositories or protected release jobs, and keep keys off their
  disks (REL-012 low).
- Consider `zizmor` (a GitHub Actions linter) for the rest of this list; it
  reports dangerous triggers, unpinned actions and excessive permissions.

## 5. Codemagic

- Pin `environment.flutter` to a version, not `stable`.
- Keep keys in **code signing identities** (Android keystores, iOS
  certificates and profiles uploaded to Codemagic) or encrypted environment
  groups; reference them by name, never print them (REL-011).
- `artifacts:` lists only build outputs (`build/**/outputs/**/*.aab`,
  `build/ios/ipa/*.ipa`, `build/symbols/**` privately), never a pattern that
  covers a decoded key (REL-012).

## 6. Fastlane

- Keep `Appfile` ids and `Fastfile` lanes in git; keep the service account
  JSON, `.p8` key and `match` password out of it.
- `supply` (Play) with `track: internal` or `rollout: '0.1'`; `pilot`
  (TestFlight) and `deliver` (App Store) with an App Store Connect API key.
- Run lanes from CI so every release is reproducible; a laptop release is an
  unreviewed one.

## 7. Review checklist

| Finding | Severity |
|---|---|
| REL-010 `pull_request_target` runs PR code | High |
| REL-011 secret printed to the log | High |
| REL-012 keystore inside an uploaded artifact | High |
| REL-012 keystore left on a persistent runner | Low |
| REL-flutter-unpinned | Low |
| REL-ci-permissions | Low |
| SEC-012 release `flutter build` without `--obfuscate --split-debug-info` | Low (flutter-secure-defaults) |
