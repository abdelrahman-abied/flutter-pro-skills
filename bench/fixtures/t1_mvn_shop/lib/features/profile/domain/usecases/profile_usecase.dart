import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/profile_repository_impl.dart';
import '../entities/profile_entity.dart';
import '../repositories/profile_repository.dart';

part 'profile_usecase.g.dart';

class FetchProfile {
  const FetchProfile(this._repository);

  final ProfileRepository _repository;

  Future<ProfileEntity> call() => _repository.fetchProfile();
}

class UpdateProfileName {
  const UpdateProfileName(this._repository);

  final ProfileRepository _repository;

  Future<ProfileEntity> call(String name) => _repository.updateName(name);
}

@riverpod
FetchProfile fetchProfile(Ref ref) =>
    FetchProfile(ref.watch(profileRepositoryProvider));

@riverpod
UpdateProfileName updateProfileName(Ref ref) =>
    UpdateProfileName(ref.watch(profileRepositoryProvider));
