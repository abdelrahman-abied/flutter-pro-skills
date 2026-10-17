import '../../domain/entities/movie.dart';

sealed class MovieState {
  const MovieState();
}

final class MovieInitial extends MovieState {
  const MovieInitial();
}

final class MovieLoading extends MovieState {
  const MovieLoading();
}

final class MovieSuccess extends MovieState {
  const MovieSuccess(this.movies);
  final List<Movie> movies;
}

final class MovieError extends MovieState {
  const MovieError(this.message);
  final String message;
}
