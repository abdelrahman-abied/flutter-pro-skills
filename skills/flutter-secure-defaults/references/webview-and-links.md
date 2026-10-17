# WebViews, links and permissions

A WebView runs someone else's code inside your app, url_launcher hands a URL
to another app, and a permission prompt asks the user to trust you. Each
needs an allow-list by default.

Ownership in the suite:
- WebView JS bridges and file access in config: `flutter-security-audit`
  (`WEB-JS-CHANNEL`, `WEB-FILE-ACCESS`).
- Opening untrusted URLs and secrets in routes: `flutter-navigation`
  (NAV-005 `untrusted-url-launch`, NAV-006 `sensitive-data-in-route`; read
  `../flutter-navigation/SKILL.md` and its `deep-links-and-security.md`).
- Manifest and plist permissions: `flutter-security-audit` (`PRV-PERMS`,
  `PRV-IOS-PERMS`).

This file gives the write-time defaults, and SEC-007 checks the WebView
default.

## Contents

1. WebView defaults (webview_flutter)
2. flutter_inappwebview specifics
3. Opening links with url_launcher
4. Permissions
5. Review questions

## 1. WebView defaults (webview_flutter)

1. **JavaScript off unless the page needs it.** The default is
   `JavaScriptMode.disabled`. Turn it on only for pages you control.
2. **Restrict navigation.** When JS is on, add an `onNavigationRequest`
   allow-list by scheme **and** host. An always-`navigate` delegate is no
   guard (SEC-007 treats it as missing).
3. **Validate before `loadRequest`.** On Android, `onNavigationRequest` does
   not fire for programmatic `loadRequest()` calls (flutter#152168). If the
   URL comes from a deep link, a push or the server, check it at the call
   site.
4. **No JS channels for content you don't control.** `addJavaScriptChannel`
   is a native bridge for every script on every page the WebView reaches. If
   you need one, accept only an allow-listed origin and validate every
   message as untrusted input.
5. **No file access.** Don't load `file://` URLs built from input. On Android,
   keep file access off in the platform settings (the audit's
   `WEB-FILE-ACCESS` checks it).
6. **Clear cookies and storage on logout**:
   `WebViewCookieManager().clearCookies()` and `controller.clearLocalStorage()`.
7. **Don't inject tokens into pages.** Use a short-lived, single-use ticket
   your backend exchanges for a web session, never the app's refresh token.

```dart
const _allowedHosts = {'help.shop.app', 'shop.app'};

bool isAllowedWebUrl(Uri uri) => uri.scheme == 'https' && _allowedHosts.contains(uri.host);

final controller = WebViewController()
  ..setJavaScriptMode(JavaScriptMode.unrestricted)          // only because help pages need it
  ..setNavigationDelegate(NavigationDelegate(
    onNavigationRequest: (request) {
      final uri = Uri.tryParse(request.url);
      if (uri != null && isAllowedWebUrl(uri)) return NavigationDecision.navigate;
      if (uri != null && uri.scheme == 'https') {
        launchUrl(uri, mode: LaunchMode.externalApplication); // other sites open in the browser
      }
      return NavigationDecision.prevent;
    },
  ));

void openHelp(Uri url) {
  if (!isAllowedWebUrl(url)) return;                        // the delegate doesn't see this call on Android
  controller.loadRequest(url);
}
```

## 2. flutter_inappwebview specifics

- **JavaScript is on by default** (`javaScriptEnabled: true`). Set it `false`
  unless you need it.
- `shouldOverrideUrlLoading` **only fires when
  `useShouldOverrideUrlLoading: true`** is set in the settings. Without it,
  your allow-list is dead code. SEC-007 reports that case.
- Keep `allowFileAccessFromFileURLs` and `allowUniversalAccessFromFileURLs`
  off, and don't enable `addJavaScriptHandler` for untrusted origins.

```dart
InAppWebView(
  initialUrlRequest: URLRequest(url: WebUri('https://help.shop.app')),
  initialSettings: InAppWebViewSettings(
    javaScriptEnabled: true,
    useShouldOverrideUrlLoading: true,
    allowFileAccessFromFileURLs: false,
    allowUniversalAccessFromFileURLs: false,
  ),
  shouldOverrideUrlLoading: (controller, action) async {
    final uri = action.request.url;
    return uri != null && isAllowedWebUrl(uri) ? NavigationActionPolicy.ALLOW : NavigationActionPolicy.CANCEL;
  },
)
```

## 3. Opening links with url_launcher

The `flutter-navigation` skill owns this check (NAV-005). The write-time
default is a single helper that every call site uses:

```dart
const _allowedSchemes = {'https', 'mailto', 'tel'};

Future<bool> openExternal(Uri uri) async {
  if (!_allowedSchemes.contains(uri.scheme)) return false;  // no intent:, file:, javascript:, custom schemes
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}
```

- `canLaunchUrl` is not validation. It only says some app can handle the
  scheme.
- Never put tokens or personal data in a URL you open, because browsers,
  analytics and the receiving site log it (NAV-006).

## 4. Permissions

- **Ask at the moment of need, with context.** Request the camera when the
  user taps "scan", not at startup. Explain why first, then call
  `permission_handler`'s `request()`.
- **Ask for the narrowest permission:** coarse location before fine,
  "while in use" before "always", the system photo picker
  (`image_picker` / Android Photo Picker) instead of storage permissions,
  `READ_MEDIA_IMAGES` instead of `READ_EXTERNAL_STORAGE`.
- **Handle denial** as a normal state, with a path to settings for
  "permanently denied". Never loop the prompt.
- **Remove what you don't use.** Plugins add permissions to the *merged*
  manifest (strip them with `tools:node="remove"`), and stale
  `NS…UsageDescription` keys draw App Review questions. The audit's
  `PRV-PERMS` and `PRV-IOS-PERMS` list them.

```dart
Future<bool> ensureCameraForScan(BuildContext context) async {
  final status = await Permission.camera.status;
  if (status.isGranted) return true;
  if (status.isPermanentlyDenied) {
    if (context.mounted) await showOpenSettingsDialog(context);
    return false;
  }
  return (await Permission.camera.request()).isGranted;
}
```

## 5. Review questions

- Does every WebView with JS have a working allow-list, and are URLs checked
  before `loadRequest`?
- Do JS channels only accept allow-listed origins, with validated messages?
- Do all external links go through one scheme-checking helper (NAV-005)?
- Is each permission requested in context, narrow, and handled when denied?
