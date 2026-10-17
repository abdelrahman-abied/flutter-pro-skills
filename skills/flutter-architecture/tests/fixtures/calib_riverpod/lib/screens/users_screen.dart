// K3 A2/A3/A15: watching a FutureProvider, a static namespace and a value class -> no ARCH-005
import 'package:flutter/widgets.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import '../api/config_options.dart';
import '../api/menu_item_source.dart';
import '../api/user_service.dart';

class UsersScreen extends ConsumerWidget {
  const UsersScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(usersProvider);
    ref.watch(ConfigOptions.mode);
    const MenuItem(null);
    return const SizedBox();
  }
}
