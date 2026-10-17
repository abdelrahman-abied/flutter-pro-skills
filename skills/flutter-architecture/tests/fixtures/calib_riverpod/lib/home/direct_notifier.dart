// true positive kept: the notifier constructs the concrete service -> ARCH-007
import 'package:hooks_riverpod/hooks_riverpod.dart';
import '../api/user_service.dart';

class DirectNotifier extends Notifier<int> {
  @override
  int build() {
    UserService().fetch();
    return 0;
  }
}
