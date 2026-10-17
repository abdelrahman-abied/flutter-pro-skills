import '../repositories/profile_repository.dart';

class SendCodeUseCase {
  const SendCodeUseCase(this._repository);

  final ProfileRepository _repository;

  Future<void> call(String phone) => _repository.sendCode(phone);
}
