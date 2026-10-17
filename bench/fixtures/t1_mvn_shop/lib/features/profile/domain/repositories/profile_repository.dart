import '../entities/profile_entity.dart';

abstract interface class ProfileRepository {
  Future<ProfileEntity> fetchProfile();

  Future<ProfileEntity> updateName(String name);
}
