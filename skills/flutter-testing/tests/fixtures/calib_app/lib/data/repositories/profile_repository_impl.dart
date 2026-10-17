import '../sources/user_api.dart';

abstract class ProfileRepository {
  Future<String> displayName(int id);
}

class ProfileRepositoryImpl implements ProfileRepository {
  ProfileRepositoryImpl(this._api);
  final UserApi _api;

  @override
  Future<String> displayName(int id) => _api.fetchName(id);
}
