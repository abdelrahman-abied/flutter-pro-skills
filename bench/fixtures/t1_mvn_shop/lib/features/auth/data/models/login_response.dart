import '../../domain/entities/user_entity.dart';

class LoginResponse {
  const LoginResponse({
    required this.token,
    required this.userId,
    required this.email,
    required this.name,
  });

  factory LoginResponse.fromJson(Map<String, dynamic> json) => LoginResponse(
        token: json['token'] as String,
        userId: json['user']['id'] as int,
        email: json['user']['email'] as String,
        name: json['user']['name'] as String,
      );

  final String token;
  final int userId;
  final String email;
  final String name;

  UserEntity toEntity() => UserEntity(id: userId, email: email, name: name);
}
