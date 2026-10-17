import 'auth_repository.dart';
import 'auth_repository_dev.dart';
import 'user_repository_impl.dart';

class RepositoryFactory {
  RepositoryFactory() {
    _auth = AuthRepositoryDev();
  }

  late final AuthRepository _auth;

  AuthRepository get auth => _auth;

  UserRepositoryImpl user() => UserRepositoryImpl();
}
