import 'package:meta/meta.dart';

@immutable
class ProfileEntity {
  const ProfileEntity({required this.name, required this.email});

  final String name;
  final String email;
}
