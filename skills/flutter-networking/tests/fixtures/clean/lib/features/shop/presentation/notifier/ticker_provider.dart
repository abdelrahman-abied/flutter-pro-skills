import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'ticker_provider.g.dart';

@riverpod
Future<String> itemDetail(Ref ref, String id) async {
  final cancelToken = CancelToken();
  ref.onDispose(cancelToken.cancel);
  final res = await ref.watch(dioForDetailProvider).get<String>('/items/$id', cancelToken: cancelToken);
  return res.data ?? '';
}

extension CancelTokenX on Ref {
  CancelToken cancelToken() {
    final token = CancelToken();
    onDispose(token.cancel);
    return token;
  }
}

@riverpod
Dio dioForDetail(Ref ref) => throw UnimplementedError('overridden in main');
