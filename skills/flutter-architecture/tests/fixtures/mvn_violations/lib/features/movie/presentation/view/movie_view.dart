import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// arch-ignore: ARCH-005 legacy client, removed in #42
import 'package:http/http.dart' as http;

import '../../data/models/movie_response.dart';
import '../../data/sources/movie_source.dart';
import '../../domain/repositories/movie_repository.dart';
import '../notifier/movie_notifier.dart';

class MovieView extends ConsumerStatefulWidget {
  const MovieView({super.key, this.repository});
  final MovieRepository? repository;

  @override
  ConsumerState<MovieView> createState() => _MovieViewState();
}

class _MovieViewState extends ConsumerState<MovieView> {
  MovieResponse? _last;
  http.Client? _client;
  DioException? _error;

  @override
  void initState() {
    super.initState();
    ref.read(movieNotifierProvider.notifier).load(context);
  }

  @override
  Widget build(BuildContext context) {
    final source = ref.watch(movieSourceProvider);
    return Text('${_last?.title} $_client $_error $source');
  }
}
