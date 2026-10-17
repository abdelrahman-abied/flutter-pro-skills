import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/auth_state.dart';

part 'auth_notifier.g.dart';

@riverpod
class AuthNotifier extends _$AuthNotifier {
  @override
  AuthState build() => const AuthSignedOut();

  void signedIn(String displayName) => state = AuthSignedIn(displayName: displayName);
}
