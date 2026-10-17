import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/error/app_exception.dart';
import '../../domain/usecases/login_usecase.dart';
import '../state/auth_state.dart';

part 'auth_notifier.g.dart';

@Riverpod(keepAlive: true)
class AuthNotifier extends _$AuthNotifier {
  @override
  AuthState build() => const AuthInitial();

  Future<void> login({required String email, required String password}) async {
    state = const AuthLoading();
    try {
      final user = await ref.read(loginProvider)(
        email: email,
        password: password,
      );
      state = AuthSuccess(user);
    } on AppException {
      state = const AuthError();
    }
  }
}
