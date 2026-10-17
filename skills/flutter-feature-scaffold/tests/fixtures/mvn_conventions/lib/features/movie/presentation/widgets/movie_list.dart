import 'package:flutter/material.dart';

import 'package:mvn_conventions/features/movie/domain/entities/movie_entity.dart';

class MovieList extends StatelessWidget {
  final List<MovieEntity> movies;
  const MovieList({required this.movies, super.key});

  @override
  Widget build(BuildContext context) => ListView(
        children: [for (final m in movies) ListTile(title: Text(m.title))],
      );
}
