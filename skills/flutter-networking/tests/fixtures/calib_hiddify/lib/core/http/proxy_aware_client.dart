import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';

/// Several pre-configured clients; the dart:io HttpClient only sets the proxy (FP cause: NET-001 on an
/// adapter factory, where Dio's own timeouts apply).
class ProxyAwareClient {
  ProxyAwareClient({required Duration timeout}) {
    for (final route in ['plain', 'tunnel']) {
      final dio = Dio(BaseOptions(connectTimeout: timeout, receiveTimeout: timeout));
      dio.httpClientAdapter = IOHttpClientAdapter(
        createHttpClient: () {
          final client = HttpClient();
          client.findProxy = (uri) => route == 'tunnel' ? 'PROXY 127.0.0.1:$port' : 'DIRECT';
          return client;
        },
      );
      _clients[route] = dio;
    }
  }

  final Map<String, Dio> _clients = {};
  int port = 0;

  Future<Response<String>> get(String url, {CancelToken? cancelToken}) =>
      _clients['plain']!.get<String>(url, cancelToken: cancelToken);
}

/// A bare dart:io client with no timeout anywhere in the file still fires (TP).
Future<int> probe(Uri uri) async {
  final client = HttpClient();
  try {
    final request = await client.getUrl(uri);
    return (await request.close()).statusCode;
  } finally {
    client.close();
  }
}
