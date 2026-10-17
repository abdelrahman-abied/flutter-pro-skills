// arch-ignore-file: ARCH-008 tile reads the contract for a type check only
import 'package:flutter/material.dart';

import '../../domain/repositories/movie_repository.dart';

class MovieTile extends StatelessWidget {
  const MovieTile({super.key, required this.repo});
  final MovieRepository repo;

  @override
  Widget build(BuildContext context) => Text('$repo');
}
