# Secrets and configuration

The one rule: **anything in the app binary is public.** String literals,
`--dart-define` values, `envied` fields (obfuscated or not), bundled `.env`
files, assets and native resources can all be pulled out of an APK or IPA in
minutes. `--obfuscate` renames symbols. It doesn't hide strings, and tools
like blutter recover the object pool (see `flutter-security-audit`'s attack
playbook §A to prove it on your own build).

So the question for every key is not "how do I hide it?" but "is it safe for
the whole internet to have it?". If not, it belongs on your backend.

## Contents

1. Secrets vs public identifiers
2. Configuration that isn't secret: flavors and `--dart-define`
3. What not to do: literals, defaults, `.env` assets, envied
4. Third-party APIs that need a secret: proxy through your backend
5. If a secret leaked
6. Review questions

## 1. Secrets vs public identifiers

| Value | Public by design? | What protects it instead |
|---|---|---|
| Firebase `apiKey` in `firebase_options.dart` | Yes: it identifies the project | Security Rules, App Check, API restrictions in Google Cloud |
| Supabase **anon** key (a JWT with `"role":"anon"`) | Yes | Row-level security on every table |
| Supabase **service_role** key | **No**: it bypasses RLS | It never leaves the server |
| Stripe publishable `pk_live_…` | Yes | Server-side PaymentIntents |
| Stripe secret `sk_live_…` / restricted `rk_live_…` | **No** | Server only |
| Google Maps / Places key | Treat as public, but **restrict** it | Android package + SHA-1 and iOS bundle restrictions, an API allow-list, quotas |
| OAuth client ID (mobile, PKCE) | Yes | PKCE and redirect-URI registration |
| OAuth client **secret** | **No**: a mobile app is a public client | Use PKCE, with no secret at all |
| AWS access keys, GitHub tokens, SendGrid, Twilio, OpenAI or Anthropic keys | **No** | Server only, scoped credentials, short-lived tokens via your backend |
| Signing keys, private keys, HMAC secrets | **No** | Server or HSM |

The checker grades these the same way. Vendor secret formats are **High**,
a Google API key is **Medium** ("confirm it's restricted"), and a Firebase
`apiKey` or an anon JWT is **Info** (SEC-008). The audit's `scan.sh` reports
every `AIza…` key as Critical (`SEC-CLOUDKEY`), so expect that difference.

## 2. Configuration that isn't secret: flavors and `--dart-define`

Base URLs, feature flags, environment names and public client IDs are
config. Pass them per flavor and inject an `AppConfig`, so sources don't
hard-code them (`AP-hardcoded-config-in-sources` in `flutter-architecture`):

```dart
final class AppConfig {
  const AppConfig({required this.apiBaseUrl, required this.environment});

  factory AppConfig.fromEnvironment() => AppConfig(
        apiBaseUrl: Uri.parse(const String.fromEnvironment('API_BASE_URL', defaultValue: 'https://api.dev.shop.app')),
        environment: const String.fromEnvironment('APP_ENV', defaultValue: 'dev'),
      );

  final Uri apiBaseUrl;
  final String environment;
}
```

```bash
flutter build appbundle --release --obfuscate --split-debug-info=build/symbols \
  --dart-define=API_BASE_URL=https://api.shop.app --dart-define=APP_ENV=prod
# or --dart-define-from-file=config/prod.json (non-secret values only)
```

`--dart-define` values are compiled into the binary as plain strings. They
also appear in CI logs if you echo the command. That's fine for config and
wrong for secrets: SEC-009 reports a secret-named define (`*_SECRET`,
`*_PRIVATE_KEY`, `*_PASSWORD`) as Medium and any other credential-named one
as Low.

## 3. What not to do: literals, defaults, `.env` assets, envied

```dart
// Bad: a literal secret (SEC-008)
static const stripeSecret = 'sk_live_…';

// Bad: "it's only a default" (SEC-009 medium). It's in git and in every build without the define
const paymentSecret = String.fromEnvironment('PAYMENT_SECRET', defaultValue: 'zX9q…');

// Bad: flutter_dotenv with `- .env` under flutter/assets (SEC-009 medium).
// The file is shipped verbatim at assets/flutter_assets/.env inside the APK.
final key = dotenv.env['OPENAI_API_KEY'];

// Still not secret: envied embeds the value; obfuscate: true only XORs it (SEC-009)
@EnviedField(varName: 'LASTFM_API_SECRET', obfuscate: true)
static final String lastFmSecret = _Env.lastFmSecret;
```

- `.env` files are fine **for build tooling** and for non-secret config. Add
  `.env*` to `.gitignore`, and never list them as Flutter assets.
- Don't put secrets in `AndroidManifest.xml` meta-data, `Info.plist`,
  `google-services.json` or `strings.xml` either. They're as readable as
  Dart.
- Storage key *names* (`static const accessTokenKey = 'access_token'`) are
  not secrets. The checker skips identifier-like values.
- Test credentials in `lib/` ship to users. Keep them in `test/` or
  `integration_test/`, loaded from the CI environment.

## 4. Third-party APIs that need a secret: proxy through your backend

```text
App ──(user session token)──▶ your backend ──(secret key, server-side)──▶ third-party API
```

- The backend authenticates the user, applies rate limits and quotas, and
  holds the key. A leaked app gets an attacker nothing beyond what a normal
  user can do.
- No backend? Use a serverless function (Firebase Functions, Supabase Edge
  Functions, Cloudflare Workers), and protect it with App Check or attestation
  (the audit skill's L6 covers attestation).
- For per-user third-party access, use OAuth with PKCE, so each user gets
  their own scoped token. Store it like any other token.

## 5. If a secret leaked

1. **Rotate it first.** Deleting the line doesn't help: the value is in git
   history and in every shipped build.
2. Check the provider's logs for abuse in the window it was exposed.
3. Remove it from the code, move the operation to the backend, and ship.
4. Rewriting git history (`git filter-repo`) is optional cleanup after
   rotating, never instead of it.
5. Add a secret scanner to CI (gitleaks, trufflehog or GitHub secret
   scanning), plus this skill's checker and the audit's `scan.sh`.

Never paste the leaked value into an issue, a chat or a report. Cite
"a credential at `lib/core/config.dart:5`", or mask it as `sk_live_…(32 chars)`.

## 6. Review questions

- Is every key in the app on the "public by design" list, and restricted?
- Are `--dart-define`, `.env` and envied used only for config?
- Is there a CI secret scanner, and are release builds obfuscated with
  private symbols (SEC-012)?
