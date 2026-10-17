import 'package:flutter/foundation.dart';

import '../../domain/entities/profile_entity.dart';

@immutable
sealed class ProfileState {
  const ProfileState();
}

final class ProfileLoading extends ProfileState {
  const ProfileLoading();
}

final class ProfileSuccess extends ProfileState {
  const ProfileSuccess(this.profile);

  final ProfileEntity profile;
}

final class ProfileError extends ProfileState {
  const ProfileError();
}
