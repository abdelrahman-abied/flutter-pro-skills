# Signing and versioning

Signing proves an update comes from you; the version tells the store and the
device which build is newer. Both fail late (at upload, or on a user's
device), so set them up before the first release, not during it.

Follow the docs.flutter.dev deployment guides ("Build and release an Android
app", "Build and release an iOS app") for the clicks and commands. This file
covers the decisions and what to keep out of the repository.

## 1. Android

- **Use Play App Signing** (required for new apps since 2021). Google holds
  the app signing key; you keep an **upload key**. If the upload key leaks or
  is lost, Play can reset it. Without Play App Signing, a lost key means a new
  listing.
- Create the upload keystore once:
  `keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload`.
  Store it and its passwords in your password manager and in the CI secret
  store, nowhere else.
- `android/key.properties` (outside git) points to it:

  ```properties
  storePassword=<from the password manager>
  keyPassword=<from the password manager>
  keyAlias=upload
  storeFile=/absolute/path/or/relative/to/android/app/upload-keystore.jks
  ```

- Load it into `signingConfigs.release` and use it for the `release` build
  type (REL-001). Kotlin DSL:

  ```kotlin
  val keystoreProperties = Properties().apply {
      val f = rootProject.file("key.properties")
      if (f.exists()) load(FileInputStream(f))
  }
  android {
      signingConfigs {
          create("release") {
              keyAlias = keystoreProperties["keyAlias"] as String?
              keyPassword = keystoreProperties["keyPassword"] as String?
              storeFile = keystoreProperties["storeFile"]?.let { file(it) }
              storePassword = keystoreProperties["storePassword"] as String?
          }
      }
      buildTypes {
          getByName("release") { signingConfig = signingConfigs.getByName("release") }
      }
  }
  ```

- **PREFER** failing a release build without a key over falling back to the
  debug key. A fallback is convenient locally, but it lets a debug-signed
  artifact reach a release channel (REL-001 info).
- **DON'T** commit `*.jks`, `*.keystore`, `key.properties`
  (REL-002). `flutter create` writes the patterns into `android/.gitignore`;
  keep them. If a key was committed: remove it, rewrite history, rotate the
  key (Play Console > App integrity > request an upload key reset).

## 2. iOS

- Let **Xcode automatic signing** handle development builds. For CI, use
  `fastlane match` (certificates and profiles in an encrypted repo or bucket)
  or App Store Connect API keys with `xcodebuild -allowProvisioningUpdates`.
- **DON'T** commit `.p12` certificates, `.p8` API keys or
  `.mobileprovision` profiles (REL-002). In CI, import them from secrets into
  a temporary keychain and delete the keychain in an `always()` step (see
  `ci-cd.md`).
- One bundle identifier per flavor (`com.acme.shop`, `com.acme.shop.dev`),
  registered in the Developer portal, never `com.example` (REL-003).

## 3. Versioning

`pubspec.yaml` is the single source:

```yaml
version: 2.4.1+2040100   # build name (versionName / CFBundleShortVersionString) + build number (versionCode / CFBundleVersion)
```

- The **build number must increase with every upload** to a store track. Play
  rejects a reused `versionCode`; App Store Connect rejects a reused
  `CFBundleVersion` for the same version.
- **PREFER** a CI-derived build number:
  `flutter build appbundle --build-number=${{ github.run_number }}` (add an
  offset when migrating), or a scheme derived from the version
  (`2.4.1` → `2040100`) when builds come from several machines.
- Keep `versionCode = flutter.versionCode` and `versionName =
  flutter.versionName` in Gradle, and `$(FLUTTER_BUILD_NUMBER)` /
  `$(FLUTTER_BUILD_NAME)` in Xcode. A hand-edited number in either is a second
  source of truth (REL-version-code-hardcoded).
- Use semantic versions for the build name and tag the commit you shipped
  (`v2.4.1`), so a crash report maps back to source.

## 4. Release build commands

```bash
flutter build appbundle --release --flavor prod -t lib/main_prod.dart \
  --split-debug-info=build/symbols --obfuscate \
  --dart-define-from-file=config/prod.json --build-number="$BUILD_NUMBER"

flutter build ipa --release --flavor prod -t lib/main_prod.dart \
  --split-debug-info=build/symbols --obfuscate \
  --export-options-plist=ios/ExportOptions.plist --build-number="$BUILD_NUMBER"
```

- `--split-debug-info` keeps Dart symbols out of the binary. Archive the
  folder privately per build and upload it to your crash reporter
  (REL-no-symbols-upload). Whether to add `--obfuscate`, and what it does and
  doesn't protect, is `flutter-security-audit`'s call; SEC-012 reports a
  release command without it.
- Upload an **App Bundle** to Play, not APKs. Build APKs only for side-loading
  or other stores.
