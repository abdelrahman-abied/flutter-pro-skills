import 'package:flutter/material.dart';

import '../../domain/entities/movie_entity.dart';

class MovieList extends StatelessWidget {
  final List<MovieEntity> movies;
  const MovieList({required this.movies, super.key});

  @override
  Widget build(BuildContext context) => ListView.builder(
        itemCount: movies.length,
        itemBuilder: (context, i) => ListTile(title: Text(movies[i].title)),
      );
}
