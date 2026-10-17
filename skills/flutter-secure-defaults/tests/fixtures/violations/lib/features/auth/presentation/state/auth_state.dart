sealed class AuthState {
  const AuthState();
}

final class AuthSignedOut extends AuthState {
  const AuthSignedOut();
}

final class AuthSignedIn extends AuthState {
  const AuthSignedIn({required this.name, this.accessToken});
  final String name;
  // SEC-010 low: the raw token in UI state.
  final String? accessToken;
}
