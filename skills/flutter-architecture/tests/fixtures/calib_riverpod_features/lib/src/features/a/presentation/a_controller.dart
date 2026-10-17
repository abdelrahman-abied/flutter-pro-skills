import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../c/presentation/c_controller.dart';

@riverpod
class AController extends _$AController {
  @override
  int build() => ref.watch(cControllerProvider);
}
