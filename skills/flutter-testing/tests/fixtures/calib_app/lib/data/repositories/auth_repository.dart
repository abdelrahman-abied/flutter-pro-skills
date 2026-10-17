abstract class AuthRepository {
  Future<bool> get isAuthenticated;
  Future<void> login(String email);
}
