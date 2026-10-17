# Store requirements

Store rules change every year. This file lists the ones that most often block
a Flutter upload and how to check each; confirm current values against the
Play Console and App Store Connect help before a release.

## 1. Both stores

| Requirement | Check |
|---|---|
| A permanent app id that you own | `applicationId` / `PRODUCT_BUNDLE_IDENTIFIER` is not `com.example.*` (REL-003) |
| A build number higher than every previous upload | `version: x.y.z+N` with N from CI (`signing-and-versioning.md` §3) |
| Release signing, not debug | REL-001 (Android); a distribution certificate and App Store profile (iOS) |
| A privacy policy URL and an accurate data-safety / privacy-label form | store consoles; matches what your analytics and crash SDKs collect |
| An account deletion path if users can create accounts | in-app and on the web (both stores require it) |
| A review account for login-gated apps | credentials in the review notes, pointing at a backend the release build can reach (another reason not to choose environments by build mode, REL-005) |

## 2. Google Play

- **Target API level.** New apps and updates must target a recent Android
  level: API 35 since 2025-08-31, and Google raises it every August
  (developer.android.com/google/play/requirements/target-sdk). Prefer
  `targetSdk = flutter.targetSdkVersion`; a hard-coded lower number is
  REL-008. When you raise it, read the behaviour changes of each skipped
  version (edge-to-edge, foreground service types, exact alarms,
  notification permission).
- **App Bundle** (`.aab`) uploads with **Play App Signing**.
- **Permissions.** Declare only what you use; sensitive ones (SMS, call log,
  all-files access, background location, exact alarms) need a declaration
  form. Plugins merge their permissions into your manifest, so read the
  merged manifest (`build/app/intermediates/merged_manifests/`).
- **64-bit native code**: Flutter's default ABIs already comply; check any
  prebuilt `.so` you add.

## 3. Apple App Store

- **Purpose strings.** Every protected resource the binary uses needs its
  `NS…UsageDescription` in `ios/Runner/Info.plist`, written for users ("Scan
  a receipt to add it to your expenses"), and localised in
  `InfoPlist.strings`. Missing strings crash the app on request and get
  flagged at upload (REL-009).
- **Privacy manifest.** Apple requires `PrivacyInfo.xcprivacy` for
  required-reason API use and for listed third-party SDKs (since 2024-05-01).
  Plugins and the Flutter engine ship their own; add
  `ios/Runner/PrivacyInfo.xcprivacy` when your own native code or the app's
  data collection needs declaring, or when App Store Connect warns
  (REL-privacy-manifest, reading level).
- **Encryption export compliance.** Set `ITSAppUsesNonExemptEncryption` to
  `false` in `Info.plist` when you only use HTTPS/standard OS crypto, to skip
  the question on every upload.
- **Minimum iOS version** in the Podfile and Xcode matches what your plugins
  need; Xcode and SDK versions follow Apple's yearly minimum for uploads.
- **Tracking.** If any SDK tracks across apps, show the App Tracking
  Transparency prompt (`NSUserTrackingUsageDescription`) before it does.

## 4. What this skill doesn't check

Manifest and plist **hardening** (`android:debuggable`, `allowBackup`,
cleartext and ATS exceptions, pinning, root/jailbreak detection) belongs to
`flutter-security-audit` (installed separately). Secrets in the build belong
to `flutter-secure-defaults` (SEC-008/009).
