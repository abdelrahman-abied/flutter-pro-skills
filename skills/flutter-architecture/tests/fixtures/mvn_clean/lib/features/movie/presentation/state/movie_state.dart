// lib/features/movie/presentation/state/movie_state.dart
import 'package:meta/meta.dart';

import '../../domain/entities/movie_entity.dart';

@immutable
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
  final List<MovieEntity> movies;
  const MovieSuccess(this.movies);
}

final class MovieError extends MovieState {
  final String message;
  const MovieError(this.message);
}
