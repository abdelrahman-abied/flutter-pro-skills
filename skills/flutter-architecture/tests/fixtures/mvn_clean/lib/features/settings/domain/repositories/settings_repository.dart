import '../entities/settings_entity.dart';

abstract interface class SettingsRepository {
  Future<SettingsEntity> load();
  Future<void> save(SettingsEntity settings);
}
