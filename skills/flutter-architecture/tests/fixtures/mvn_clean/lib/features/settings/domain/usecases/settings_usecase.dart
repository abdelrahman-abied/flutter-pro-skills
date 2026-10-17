import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../entities/settings_entity.dart';
import '../repositories/settings_repository.dart';
import '../../data/repositories/settings_repository_impl.dart';

part 'settings_usecase.g.dart';

class LoadSettings {
  const LoadSettings(this._repository);
  final SettingsRepository _repository;

  Future<SettingsEntity> call() => _repository.load();
}

class SaveSettings {
  const SaveSettings(this._repository);
  final SettingsRepository _repository;

  Future<void> call(SettingsEntity settings) => _repository.save(settings);
}

@riverpod
LoadSettings loadSettings(Ref ref) => LoadSettings(ref.watch(settingsRepositoryProvider));

@riverpod
SaveSettings saveSettings(Ref ref) => SaveSettings(ref.watch(settingsRepositoryProvider));
