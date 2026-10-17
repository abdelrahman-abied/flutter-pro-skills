import 'package:dio/dio.dart';

import '../../../core/http/proxy_aware_client.dart';

/// Public content on a code host is not the app's API base (FP cause: NET-008 on shared content hosts).
class ListDownloader {
  ListDownloader(this._client);

  final ProxyAwareClient _client;
  static const _baseUrl = 'https://raw.githubusercontent.com/demo-org/block-lists/main/';

  Future<String?> fetch(String name, {CancelToken? cancelToken}) async {
    // A default for a caller-supplied token (FP cause: NET-006 on `?? CancelToken()`).
    final res = await _client.get('$_baseUrl$name.txt', cancelToken: cancelToken ?? CancelToken());
    return res.data;
  }

  Future<String?> fetchFresh(String name) async {
    // An inline token nobody can cancel still fires (TP).
    final res = await _client.get('$_baseUrl$name.txt', cancelToken: CancelToken());
    return res.data;
  }
}
