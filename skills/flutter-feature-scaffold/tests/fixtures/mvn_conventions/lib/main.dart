import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:mvn_conventions/features/movie/presentation/pages/movie_page.dart';

void main() => runApp(const ProviderScope(child: MaterialApp(home: MoviePage())));
