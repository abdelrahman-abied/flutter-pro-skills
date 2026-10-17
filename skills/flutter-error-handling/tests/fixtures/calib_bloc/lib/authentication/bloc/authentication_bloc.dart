import 'package:flutter_bloc/flutter_bloc.dart';

class User {
  const User(this.id);
  final String id;
}

abstract class UserRepository {
  Future<User> getUser();
}

class AuthenticationBloc extends Bloc<Object, Object?> {
  AuthenticationBloc(this._userRepository) : super(null);
  final UserRepository _userRepository;

  // K2/K3-E1: a `tryX` returning a nullable type: null-on-failure is its contract (info, not high).
  Future<User?> _tryGetUser() async {
    try {
      final user = await _userRepository.getUser();
      return user;
    } catch (_) {
      return null;
    }
  }

  Future<User?> current() => _tryGetUser();

  // Still high: an ordinary method that hides the failure behind null.
  Future<User?> currentUser() async {
    try {
      return await _userRepository.getUser();
    } catch (_) {
      return null;
    }
  }
}
