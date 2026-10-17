import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final pubRepositoryProvider = Provider((ref) => PubRepository(Dio()));

// K3-E6: read only through a FutureProvider, which catches into AsyncValue.error: ERR-004 low.
class PubRepository {
  PubRepository(this._dio);
  final Dio _dio;

  Future<List<String>> getPackages() async {
    final res = await _dio.get<List<String>>('https://pub.dev/api/packages');
    return res.data ?? const [];
  }
}

final packagesProvider = FutureProvider<List<String>>((ref) => ref.watch(pubRepositoryProvider).getPackages());
