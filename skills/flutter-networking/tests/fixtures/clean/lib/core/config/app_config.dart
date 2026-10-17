/// The one place the API host lives (per flavor).
class AppConfig {
  const AppConfig({required this.apiBaseUrl});

  static const production = AppConfig(apiBaseUrl: 'https://api.goods-demo.io/v2');

  final String apiBaseUrl;
}

const kSupportPage = 'https://goods-demo.io/support';
const appName = 'goods';
