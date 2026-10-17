/// MVN requires use cases (flutter-architecture detect.md): this keeps the
/// fixture detected as MVN, so NAV notes carry the MVN fix.
class SignIn {
  const SignIn();

  Future<bool> call(String email, String password) async => email.isNotEmpty;
}
