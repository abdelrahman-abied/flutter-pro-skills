// K3 A13: watching another feature's provider only -> no ARCH-014
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../b/presentation/b_controller.dart';

class APage extends ConsumerWidget {
  const APage({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(bControllerProvider);
    return const SizedBox();
  }
}
