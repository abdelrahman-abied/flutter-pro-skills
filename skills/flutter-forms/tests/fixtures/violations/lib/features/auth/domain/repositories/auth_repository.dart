abstract interface class AuthRepository {
  Future<void> signIn(String email, String password);
}
