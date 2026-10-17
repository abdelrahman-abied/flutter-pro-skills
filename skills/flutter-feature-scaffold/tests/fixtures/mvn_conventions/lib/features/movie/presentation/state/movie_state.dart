import 'package:meta/meta.dart';

import 'package:mvn_conventions/features/movie/domain/entities/movie_entity.dart';

@immutable
sealed class MovieState {
  const MovieState();
}

final class MovieInitial extends MovieState {
  const MovieInitial();
}

final class MovieSuccess extends MovieState {
  final List<MovieEntity> movies;
  const MovieSuccess(this.movies);
}
