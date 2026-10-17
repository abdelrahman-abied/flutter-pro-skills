import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'auth_notifier.g.dart';

class AuthState {
  const AuthState({required this.isSignedIn, this.accessToken});
  final bool isSignedIn;
  final String? accessToken;
}

@riverpod
class AuthNotifier extends _$AuthNotifier {
  @override
  AuthState build() => const AuthState(isSignedIn: false);

  void signIn(String token) => state = AuthState(isSignedIn: true, accessToken: token);
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
