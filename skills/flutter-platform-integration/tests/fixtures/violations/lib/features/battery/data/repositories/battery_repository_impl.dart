import '../../domain/repositories/battery_repository.dart';
import '../sources/battery_platform_source.dart';

class BatteryRepositoryImpl implements BatteryRepository {
  BatteryRepositoryImpl(this._source);

  final BatteryPlatformSource _source;

  @override
  Future<int> batteryLevel() => _source.level();
}
