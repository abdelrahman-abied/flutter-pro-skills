import 'package:meta/meta.dart';

@immutable
class SettingsEntity {
  const SettingsEntity({required this.darkMode, required this.nickname});

  final bool darkMode;
  final String nickname;

  SettingsEntity copyWith({bool? darkMode, String? nickname}) => SettingsEntity(
        darkMode: darkMode ?? this.darkMode,
        nickname: nickname ?? this.nickname,
      );
}
