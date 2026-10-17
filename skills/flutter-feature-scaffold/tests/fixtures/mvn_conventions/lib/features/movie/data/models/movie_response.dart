import 'package:meta/meta.dart';

import 'package:mvn_conventions/features/movie/domain/entities/movie_entity.dart';

@immutable
class MovieResponse {
  final String id;
  final String title;
  const MovieResponse({required this.id, required this.title});

  MovieEntity toEntity() => MovieEntity(id: id, title: title);
}
