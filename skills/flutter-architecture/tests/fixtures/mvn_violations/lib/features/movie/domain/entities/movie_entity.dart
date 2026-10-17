import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../data/models/movie_response.dart';

@immutable
class MovieEntity {
  const MovieEntity({required this.id, required this.title, this.color = Colors.red});
  final String id;
  final String title;
  final Color color;

  factory MovieEntity.fromResponse(MovieResponse r) => MovieEntity(id: r.id, title: r.title);
}
