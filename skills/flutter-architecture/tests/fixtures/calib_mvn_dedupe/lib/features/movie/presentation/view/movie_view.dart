// ARCH-005 + ARCH-008 on one import line -> reported once (ARCH-005, high)
import 'package:flutter/widgets.dart';
import '../../data/repositories/movie_repository_impl.dart';

class MovieView extends StatelessWidget {
  const MovieView({super.key});
  @override
  Widget build(BuildContext context) {
    MovieRepositoryImpl().all();
    return const SizedBox();
  }
}
