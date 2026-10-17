import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'token_storage.g.dart';

/// The only place tokens live: Keychain / Keystore-backed storage.
final class TokenStorage {
  const TokenStorage(this._secure);

  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';

  final FlutterSecureStorage _secure;

  Future<String?> readAccessToken() => _secure.read(key: _accessKey);
  Future<String?> readRefreshToken() => _secure.read(key: _refreshKey);

  Future<void> save({required String access, required String refresh}) async {
    await _secure.write(key: _accessKey, value: access);
    await _secure.write(key: _refreshKey, value: refresh);
  }

  Future<void> clear() => _secure.deleteAll();
}

@riverpod
TokenStorage tokenStorage(Ref ref) => const TokenStorage(
      FlutterSecureStorage(iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device)),
    );
