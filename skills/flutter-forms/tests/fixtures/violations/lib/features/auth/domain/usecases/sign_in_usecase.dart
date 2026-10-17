import '../repositories/auth_repository.dart';

class SignInUseCase {
  const SignInUseCase(this._repository);

  final AuthRepository _repository;

  Future<void> call(String email, String password) => _repository.signIn(email.trim(), password);
}
