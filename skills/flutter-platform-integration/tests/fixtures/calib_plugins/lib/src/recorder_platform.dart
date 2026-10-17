import 'package:plugin_platform_interface/plugin_platform_interface.dart';

abstract class RecorderPlatform extends PlatformInterface {
  RecorderPlatform() : super(token: _token);

  static final Object _token = Object();
  static RecorderPlatform? _instance;

  static RecorderPlatform get instance => _instance!;

  static set instance(RecorderPlatform instance) {
    PlatformInterface.verify(instance, _token);
    _instance = instance;
  }

  Future<void> dispose(int id);

  Future<bool> purgeCache(String key);
}
