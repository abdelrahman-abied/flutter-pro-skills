class CartRemoteSource {
  static const _env = String.fromEnvironment('ENV');

  String get baseUrl => _env == 'prod' ? 'https://api.shop.example.com' : 'https://staging.shop.example.com';
}
