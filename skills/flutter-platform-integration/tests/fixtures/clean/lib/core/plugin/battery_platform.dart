import 'package:plugin_platform_interface/plugin_platform_interface.dart';

abstract class BatteryPlatform extends PlatformInterface {
  BatteryPlatform() : super(token: _token);

  static final Object _token = Object();

  static BatteryPlatform _instance = _DefaultBattery();

  static BatteryPlatform get instance => _instance;

  static set instance(BatteryPlatform instance) {
    PlatformInterface.verifyToken(instance, _token);
    _instance = instance;
  }

  Future<int> level() => throw UnimplementedError('level() has not been implemented.');
}

class _DefaultBattery extends BatteryPlatform {}

class DesktopBattery extends BatteryPlatform {
  @override
  Future<int> level() async => 100;
}
