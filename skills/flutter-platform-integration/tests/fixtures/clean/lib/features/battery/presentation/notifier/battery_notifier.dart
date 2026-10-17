import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/repositories/battery_repository.dart';

part 'battery_notifier.g.dart';

@riverpod
class BatteryNotifier extends _$BatteryNotifier {
  @override
  Future<int?> build() => ref.watch(batteryRepositoryProvider).batteryLevel();
}
