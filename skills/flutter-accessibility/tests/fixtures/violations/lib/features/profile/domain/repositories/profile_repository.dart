abstract interface class ProfileRepository {
  Future<void> sendCode(String phone);
}
