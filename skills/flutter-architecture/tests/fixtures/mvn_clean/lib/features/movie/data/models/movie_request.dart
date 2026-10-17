// lib/features/movie/data/models/movie_request.dart
import 'package:meta/meta.dart';

@immutable
class MovieRequest {
  final String query;
  const MovieRequest({required this.query});

  Map<String, dynamic> toJson() => {'query': query};
}
