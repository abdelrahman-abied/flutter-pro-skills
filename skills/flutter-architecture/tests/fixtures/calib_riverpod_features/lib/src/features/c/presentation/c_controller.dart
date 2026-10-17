// three features importing each other: one ARCH-015 per strongly connected component
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../a/presentation/a_page.dart';

@riverpod
class CController extends _$CController {
  @override
  int build() => 0;
  Object page() => const APage();
}
