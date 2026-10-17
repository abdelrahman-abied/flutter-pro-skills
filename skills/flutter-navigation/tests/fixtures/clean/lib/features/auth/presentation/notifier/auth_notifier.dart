import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'auth_notifier.g.dart';

class AuthState {
  const AuthState({required this.isSignedIn});
  final bool isSignedIn;
}

@riverpod
class AuthNotifier extends _$AuthNotifier {
  @override
  AuthState build() => const AuthState(isSignedIn: false);

  void signOut() => state = const AuthState(isSignedIn: false);
}

@riverpod
class CartNotifier extends _$CartNotifier {
  @override
  int build() => 0;
}

@riverpod
class ProfileNotifier extends _$ProfileNotifier {
  @override
  int build() => 0;
}
