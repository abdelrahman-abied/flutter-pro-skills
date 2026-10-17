import 'auth_repository.dart';

class AuthRepositoryDev extends AuthRepository {
  @override
  Future<bool> get isAuthenticated => Future.value(true);

  @override
  Future<void> login(String email) async {
    return;
  }
}
