// K2 P5: lib/app.dart holds the providers, so it is the composition root
import 'package:flutter/widgets.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:calib_bloc_mixed/shopping_repository.dart';
import 'package:http/http.dart' as http;

class App extends StatelessWidget {
  const App({super.key});
  @override
  Widget build(BuildContext context) => RepositoryProvider(
        create: (_) => ShoppingRepository(),
        child: Text('${http.Client()}'),
      );
}
