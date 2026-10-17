import 'package:flutter/services.dart';

import '../../domain/repositories/battery_repository.dart';
import '../sources/battery_platform_source.dart';

class BatteryRepositoryImpl implements BatteryRepository {
  BatteryRepositoryImpl(this._source);

  final BatteryPlatformSource _source;

  @override
  Future<int?> batteryLevel() async {
    try {
      return await _source.level();
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }
}
