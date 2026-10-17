import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/usecases/settings_usecase.dart';
import '../state/settings_state.dart';

part 'settings_notifier.g.dart';

@riverpod
class SettingsNotifier extends _$SettingsNotifier {
  @override
  Future<SettingsState> build() async {
    final settings = await ref.watch(loadSettingsProvider)();
    return SettingsSuccess(settings);
  }

  Future<void> rename(String nickname) async {
    final current = state.value;
    if (current is! SettingsSuccess) return;
    final next = current.settings.copyWith(nickname: nickname);
    state = AsyncData(SettingsSuccess(next, isSaving: true));
    await ref.read(saveSettingsProvider)(next);
    state = AsyncData(SettingsSuccess(next));
  }
}
