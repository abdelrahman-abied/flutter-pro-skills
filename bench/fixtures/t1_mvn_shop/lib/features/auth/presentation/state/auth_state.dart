import 'package:flutter/foundation.dart';

import '../../domain/entities/user_entity.dart';

@immutable
sealed class AuthState {
  const AuthState();
}

final class AuthInitial extends AuthState {
  const AuthInitial();
}

final class AuthLoading extends AuthState {
  const AuthLoading();
}

final class AuthSuccess extends AuthState {
  const AuthSuccess(this.user);

  final UserEntity user;
}

final class AuthError extends AuthState {
  const AuthError();
}
