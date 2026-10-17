import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../c/presentation/c_controller.dart';
import '../../a/presentation/a_controller.dart';

@riverpod
class BController extends _$BController {
  @override
  int build() => ref.watch(cControllerProvider) + ref.watch(aControllerProvider);
}
