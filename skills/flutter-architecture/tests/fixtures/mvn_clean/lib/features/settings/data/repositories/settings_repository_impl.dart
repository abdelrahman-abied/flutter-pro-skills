import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/settings_entity.dart';
import '../../domain/repositories/settings_repository.dart';
import '../sources/settings_source.dart';

part 'settings_repository_impl.g.dart';

class SettingsRepositoryImpl implements SettingsRepository {
  const SettingsRepositoryImpl(this._source);
  final SettingsSource _source;

  @override
  Future<SettingsEntity> load() async {
    final v = await _source.read();
    return SettingsEntity(
      darkMode: v['darkMode'] as bool? ?? false,
      nickname: v['nickname'] as String? ?? '',
    );
  }

  @override
  Future<void> save(SettingsEntity s) =>
      _source.write({'darkMode': s.darkMode, 'nickname': s.nickname});
}

@riverpod
SettingsRepository settingsRepository(Ref ref) =>
    SettingsRepositoryImpl(ref.watch(settingsSourceProvider));
