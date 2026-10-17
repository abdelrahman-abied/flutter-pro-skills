// K3 A7: a base class and a static helper of another repository are not ARCH-011
import 'api_repository.dart';
import 'user_repository.dart';

class EntriesRepository extends ApiRepository {
  String path() => '$base/${UserRepository.usersPath()}/entries';
}
