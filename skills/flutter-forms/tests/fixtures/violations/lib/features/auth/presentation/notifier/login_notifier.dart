import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/login_state.dart';

part 'login_notifier.g.dart';

@riverpod
class LoginNotifier extends _$LoginNotifier {
  @override
  LoginState build() => const LoginIdle();

  Future<void> submit(String email, String password) async {
    state = const LoginSubmitting();
    state = const LoginIdle();
  }
}

@riverpod
class SignUpNotifier extends _$SignUpNotifier {
  @override
  LoginState build() => const LoginIdle();
}

@riverpod
class ResetNotifier extends _$ResetNotifier {
  @override
  LoginState build() => const LoginIdle();
}
