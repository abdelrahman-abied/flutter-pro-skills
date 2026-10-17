sealed class BatteryFailure {
  const BatteryFailure();
}

class BatteryUnsupported extends BatteryFailure {
  const BatteryUnsupported();
}

abstract class BatteryRepository {
  Future<int?> batteryLevel();
}
