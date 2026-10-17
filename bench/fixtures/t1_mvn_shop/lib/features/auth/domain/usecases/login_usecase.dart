import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/auth_repository_impl.dart';
import '../entities/user_entity.dart';
import '../repositories/auth_repository.dart';

part 'login_usecase.g.dart';

class Login {
  const Login(this._repository);

  final AuthRepository _repository;

  Future<UserEntity> call({required String email, required String password}) =>
      _repository.login(email: email, password: password);
}

@riverpod
Login login(Ref ref) => Login(ref.watch(authRepositoryProvider));
