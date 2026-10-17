import 'package:flutter/material.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/sources/movie_source.dart';
import '../../domain/repositories/movie_repository.dart';
import '../state/movie_state.dart';

part 'movie_notifier.g.dart';

const kFirstPage = 1;

@riverpod
class MovieNotifier extends _$MovieNotifier {
  final search = TextEditingController(); // ARCH-109

  @override
  MovieState build() => MovieState();

  Future<void> load(BuildContext context) async {
    final source = ref.read(movieSourceProvider);
    final MovieRepository? repo = null;
    await source.getTrending();
    if (repo == null) {
      Navigator.of(context).pop();
    }
  }
}
