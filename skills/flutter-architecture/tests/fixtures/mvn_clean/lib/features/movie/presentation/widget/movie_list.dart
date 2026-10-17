// lib/features/movie/presentation/widget/movie_list.dart
import 'package:flutter/material.dart';

import '../../domain/entities/movie_entity.dart';

class MovieList extends StatelessWidget {
  final List<MovieEntity> movies;
  const MovieList({required this.movies, super.key});

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: movies.length,
      itemBuilder: (context, index) => ListTile(
        title: Text(movies[index].title),
      ),
    );
  }
}
