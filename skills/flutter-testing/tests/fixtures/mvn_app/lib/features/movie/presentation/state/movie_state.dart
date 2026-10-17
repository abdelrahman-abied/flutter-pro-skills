import '../../domain/entities/movie_entity.dart';

sealed class MovieState {
  const MovieState();
}

final class MovieLoading extends MovieState {
  const MovieLoading();
}

final class MovieSuccess extends MovieState {
  final List<MovieEntity> movies;
  const MovieSuccess(this.movies);
}

final class MovieError extends MovieState {
  final String message;
  const MovieError(this.message);
}
