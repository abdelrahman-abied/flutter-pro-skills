import 'package:meta/meta.dart';

@immutable
class UserEntity {
  const UserEntity({required this.id, required this.email, required this.name});

  final int id;
  final String email;
  final String name;
}
