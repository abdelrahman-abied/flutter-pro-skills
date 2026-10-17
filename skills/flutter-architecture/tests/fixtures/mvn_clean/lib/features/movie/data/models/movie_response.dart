// lib/features/movie/data/models/movie_response.dart
import 'package:meta/meta.dart';

import '../../domain/entities/movie_entity.dart';

@immutable
class MovieResponse {
  final String id;
  final String title;
  const MovieResponse({required this.id, required this.title});

  factory MovieResponse.fromJson(Map<String, dynamic> json) => MovieResponse(
        id: json['id'] as String,
        title: json['title'] as String,
      );

  MovieEntity toEntity() => MovieEntity(id: id, title: title);
}
