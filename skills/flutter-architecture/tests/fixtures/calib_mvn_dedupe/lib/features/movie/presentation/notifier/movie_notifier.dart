// ARCH-012 + ARCH-007 on one import line -> reported once (ARCH-012)
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../data/repositories/movie_repository_impl.dart';

@riverpod
class MovieNotifier extends _$MovieNotifier {
  @override
  Future<List<String>> build() => MovieRepositoryImpl().all();
}
