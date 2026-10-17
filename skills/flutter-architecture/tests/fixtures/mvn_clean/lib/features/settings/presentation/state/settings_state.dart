import 'package:meta/meta.dart';

import '../../domain/entities/settings_entity.dart';

@immutable
sealed class SettingsState {
  const SettingsState();
}

final class SettingsLoading extends SettingsState {
  const SettingsLoading();
}

final class SettingsSuccess extends SettingsState {
  const SettingsSuccess(this.settings, {this.isSaving = false});
  final SettingsEntity settings;
  final bool isSaving;
}
