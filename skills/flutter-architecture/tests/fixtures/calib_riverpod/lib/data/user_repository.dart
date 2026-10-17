// K3 FN-7: a repository returning a Firebase SDK type -> ARCH-107
import 'package:firebase_auth/firebase_auth.dart';

class UserRepository {
  static String usersPath() => 'users';
  Future<User?> current() async => null;
}
