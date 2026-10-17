import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'settings_source.g.dart';

abstract interface class SettingsSource {
  Future<Map<String, Object?>> read();
  Future<void> write(Map<String, Object?> values);
}

class InMemorySettingsSource implements SettingsSource {
  final _values = <String, Object?>{};

  @override
  Future<Map<String, Object?>> read() async => Map.of(_values);

  @override
  Future<void> write(Map<String, Object?> values) async => _values
    ..clear()
    ..addAll(values);
}

@Riverpod(keepAlive: true)
SettingsSource settingsSource(Ref ref) => InMemorySettingsSource();
