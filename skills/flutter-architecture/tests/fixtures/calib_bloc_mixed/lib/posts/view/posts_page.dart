// K2 C2: transport built only for injection -> ARCH-005 low
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:http/http.dart' as http;
import 'package:calib_bloc_mixed/posts/bloc/post_bloc.dart';

class PostsPage extends StatelessWidget {
  const PostsPage({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        body: BlocProvider(
          create: (_) => PostBloc(httpClient: http.Client()),
          child: const SizedBox(),
        ),
      );
}
