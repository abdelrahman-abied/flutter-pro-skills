import 'package:flutter/semantics.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/profile_state.dart';

part 'profile_notifier.g.dart';

@riverpod
class ProfileNotifier extends _$ProfileNotifier {
  @override
  ProfileState build() => const ProfileIdle();

  Future<void> sendCode(String phone) async {
    state = const ProfileCodeSent();
    SemanticsService.announce('Code sent', TextDirection.ltr);
  }
}

@riverpod
class AvatarNotifier extends _$AvatarNotifier {
  @override
  ProfileState build() => const ProfileIdle();
}

@riverpod
class PrivacyNotifier extends _$PrivacyNotifier {
  @override
  ProfileState build() => const ProfileIdle();
}
