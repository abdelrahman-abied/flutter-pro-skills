import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../data/repositories/profile_repository_impl.dart';
import '../../domain/usecases/profile_usecase.dart';
import '../state/profile_state.dart';

part 'profile_notifier.g.dart';

@riverpod
class ProfileNotifier extends _$ProfileNotifier {
  @override
  ProfileState build() {
    Future.microtask(load);
    return const ProfileLoading();
  }

  Future<void> load() async {
    state = const ProfileLoading();
    try {
      final profile = await ref.read(fetchProfileProvider)();
      state = ProfileSuccess(profile);
    } on AppException {
      state = const ProfileError();
    }
  }

  Future<void> updateName(String name) async {
    try {
      final profile =
          await ref.read(profileRepositoryProvider).updateName(name);
      state = ProfileSuccess(profile);
    } on AppException {
      state = const ProfileError();
    }
  }
}
