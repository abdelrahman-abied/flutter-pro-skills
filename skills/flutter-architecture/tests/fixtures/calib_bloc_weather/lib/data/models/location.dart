import 'package:equatable/equatable.dart';

class Location extends Equatable {
  const Location({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  factory Location.fromJson(Map<String, dynamic> json) => Location(
        id: json['id'] as int,
        name: json['name'] as String,
        latitude: (json['latitude'] as num).toDouble(),
        longitude: (json['longitude'] as num).toDouble(),
      );

  final int id;
  final String name;
  final double latitude;
  final double longitude;

  @override
  List<Object> get props => [id, name, latitude, longitude];
}
