# Release checklist, staged rollouts and monitoring

Copy this into the release issue or PR, and tick it off per release. The
first section is a one-time setup; the rest repeats.

## 1. Once per app

- [ ] Final application id and bundle id, the same family on both platforms
      (REL-003)
- [ ] Flavors mirrored on Android, iOS and `lib/main_*.dart` (REL-004), each
      with its own id suffix, name, icon and backend project
- [ ] One `AppConfig` built at the composition root and injected
      (`flavors-and-environments.md`; REL-005/006)
- [ ] Play App Signing enrolled; upload keystore and passwords in the
      password manager and the CI secret store only (REL-001/002)
- [ ] iOS distribution certificate and profiles managed by `match` or the
      App Store Connect API, not by one developer's laptop
- [ ] `.gitignore` covers `key.properties`, `*.jks`, `*.keystore`, `*.p12`,
      `*.p8`, `*.mobileprovision` (REL-002)
- [ ] Release pipeline in CI: pinned Flutter, least-privilege permissions,
      secrets via `env:`, keys in `$RUNNER_TEMP`, symbols uploaded
      (`ci-cd.md`)
- [ ] Crash reporting wired through the global handlers
      (`FlutterError.onError`, `PlatformDispatcher.instance.onError`); load
      `flutter-error-handling` for the setup and for keeping PII out of
      reports
- [ ] Store listings: privacy policy, data safety / privacy labels matching
      the SDKs you ship, review account, account deletion

## 2. Every release

**Before the build**
- [ ] `version:` bumped; build number comes from CI and is higher than every
      upload
- [ ] Changelog and release notes written (per store locale)
- [ ] `dart-flutter-review` run on the release branch, including the
      `== RELEASE` and `== SECURITY DEFAULTS` sections; no debug switches
      left on (REL-007)
- [ ] targetSdk still meets Play's current level (REL-008); new plugins'
      iOS purpose strings added (REL-009)

**Build and verify**
- [ ] Tagged commit built by CI, not locally
- [ ] Install the **release** artifact of the **prod** flavor on a real
      device of each platform: cold start, login, the main flow, a deep link,
      a push notification, an upgrade from the previous store version
      (migrations)
- [ ] `--split-debug-info` symbols archived and uploaded for this build
      number

**Ship**
- [ ] Android: internal track → closed testing → production as a **staged
      rollout** (for example 5% → 20% → 50% → 100% over several days)
- [ ] iOS: TestFlight → App Store with **phased release** (7 days,
      automatically paused if you pause it)
- [ ] A rollout owner watches the dashboards for the first 24 to 48 hours

## 3. Watching a rollout

| Signal | Where | Act when |
|---|---|---|
| Crash-free users / sessions | Crashlytics, Sentry, Play Console vitals | it drops below the previous release's baseline |
| ANR rate (Android) | Play Console vitals | it nears Play's bad-behaviour threshold |
| New top crashes | crash reporter, filtered to this build number | a new issue reaches the top five |
| Store reviews and support tickets | consoles, help desk | a pattern appears |

**Halting.** Play lets you halt a staged rollout and resume or replace it;
App Store phased release can be paused. Neither can un-install a bad build,
so the fix is a new build with a higher build number. Remote config or
feature flags let you switch a broken feature off without a release; design
them in before you need them.

## 4. After the release

- [ ] Tag and release notes published; the store build number recorded
      against the git tag
- [ ] Crash reporter's release marked as deployed; previous release's issues
      re-checked
- [ ] Anything that went wrong becomes a checklist item or a CI check
