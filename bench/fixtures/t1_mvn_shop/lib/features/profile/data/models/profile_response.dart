import '../../domain/entities/profile_entity.dart';

class ProfileResponse {
  const ProfileResponse({required this.name, required this.email});

  factory ProfileResponse.fromJson(Map<String, dynamic> json) =>
      ProfileResponse(
        name: json['name'] as String,
        email: json['email'] as String,
      );

  final String name;
  final String email;

  ProfileEntity toEntity() => ProfileEntity(name: name, email: email);
}
