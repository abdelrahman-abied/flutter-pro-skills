import '../sources/user_api.dart';

abstract class UserRepository {
  Future<String> name(int id);
}

class UserRepositoryImpl implements UserRepository {
  UserRepositoryImpl([UserApi? api]) : _api = api ?? UserApi();
  final UserApi _api;

  @override
  Future<String> name(int id) => _api.fetchName(id);
}
