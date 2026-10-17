import '../repositories/battery_repository.dart';

class GetBatteryLevel {
  GetBatteryLevel(this._repository);

  final BatteryRepository _repository;

  Future<int> execute() => _repository.batteryLevel();
}
