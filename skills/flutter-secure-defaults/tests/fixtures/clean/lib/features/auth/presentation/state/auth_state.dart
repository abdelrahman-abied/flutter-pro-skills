sealed class AuthState {
  const AuthState();
}

final class AuthSignedOut extends AuthState {
  const AuthSignedOut();
}

/// No token here: the UI only needs to know who is signed in.
final class AuthSignedIn extends AuthState {
  const AuthSignedIn({required this.displayName});
  final String displayName;
}
