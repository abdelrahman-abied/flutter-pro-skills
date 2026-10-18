import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'board_notifier.g.dart';

@riverpod
class BoardNotifier extends _$BoardNotifier {
  double screenWidth = 0;

  @override
  int build() => 0;
}
