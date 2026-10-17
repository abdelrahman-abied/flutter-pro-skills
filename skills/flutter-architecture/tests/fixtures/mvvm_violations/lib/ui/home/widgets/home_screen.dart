import 'package:flutter/material.dart';
import 'package:get_it/get_it.dart';

import '../../../data/repositories/home/home_repository.dart';
import '../../../data/services/api/api_client.dart';
import '../../../data/services/api/model/home_response.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, this.repository});
  final HomeRepository? repository;

  @override
  Widget build(BuildContext context) {
    final api = GetIt.I<ApiClient>();
    return FutureBuilder<HomeResponse>(
      future: api.fetchHome(),
      builder: (context, snap) => Text('${snap.data?.items}'),
    );
  }
}
