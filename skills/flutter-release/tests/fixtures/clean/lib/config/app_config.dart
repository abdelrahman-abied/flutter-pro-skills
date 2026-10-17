class AppConfig {
  const AppConfig(this.baseUrl);

  factory AppConfig.fromDefines() => const AppConfig(String.fromEnvironment('API_BASE_URL'));

  factory AppConfig.forFlavor(String flavor) =>
      AppConfig(flavor == 'prod' ? 'https://api.acme.example' : 'https://staging.acme.example');

  static const flavor = String.fromEnvironment('FLAVOR');

  final String baseUrl;
}
