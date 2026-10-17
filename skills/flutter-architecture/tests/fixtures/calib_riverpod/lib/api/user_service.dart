// K3 A2: a FutureProvider declared next to a service is neutral, the service's own provider is primary
import 'package:hooks_riverpod/hooks_riverpod.dart';

class UserService {
  Future<List<String>> fetch() async => const [];
}

final userServiceProvider = Provider<UserService>((ref) => UserService());
final usersProvider = FutureProvider<List<String>>((ref) => ref.watch(userServiceProvider).fetch());
