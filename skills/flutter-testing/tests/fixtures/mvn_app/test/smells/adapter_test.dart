import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeAdapter implements HttpClientAdapter {
  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<List<int>>? body, Future<void>? cancel) async =>
      ResponseBody.fromString('{"total": 2}', 200);

  @override
  void close({bool force = false}) {}
}

void main() {
  test('dio with a fake adapter is not real network', () async {
    final dio = Dio()..httpClientAdapter = FakeAdapter();
    final res = await dio.get<String>('/cart');
    expect(res.statusCode, 200);
  });
}
