import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/profile_entity.dart';
import '../../domain/repositories/profile_repository.dart';
import '../sources/profile_remote_source.dart';

part 'profile_repository_impl.g.dart';

class ProfileRepositoryImpl implements ProfileRepository {
  const ProfileRepositoryImpl(this._source);

  final ProfileRemoteSource _source;

  @override
  Future<ProfileEntity> fetchProfile() async =>
      (await _source.fetchProfile()).toEntity();

  @override
  Future<ProfileEntity> updateName(String name) async =>
      (await _source.updateName(name)).toEntity();
}

@riverpod
ProfileRepository profileRepository(Ref ref) =>
    ProfileRepositoryImpl(ref.watch(profileRemoteSourceProvider));
