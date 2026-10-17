import '../entities/user_entity.dart';

abstract interface class AuthRepository {
  Future<UserEntity> login({required String email, required String password});

  Future<void> logout();
}
