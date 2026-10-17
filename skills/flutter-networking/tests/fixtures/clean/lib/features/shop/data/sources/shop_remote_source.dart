import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class ShopRemoteSource {
  ShopRemoteSource(this._dio);

  final Dio _dio;
  WebSocketChannel? _prices;

  Future<List<dynamic>> page(int page, {CancelToken? cancelToken}) async {
    final res = await _dio.get<List<dynamic>>('/items',
        queryParameters: {'page': page}, cancelToken: cancelToken ?? CancelToken());
    return res.data ?? const [];
  }

  Future<List<dynamic>> search(String query) async {
    final uri = Uri.parse(_dio.options.baseUrl).replace(path: '/v2/search', queryParameters: {'q': query});
    final res = await _dio.getUri<List<dynamic>>(uri);
    return res.data ?? const [];
  }

  Future<List<dynamic>> byId(String id, int limit, String term) async {
    final a = await _dio.get<List<dynamic>>('${_dio.options.baseUrl}/items?id=$id&limit=$limit');
    final b = await _dio.get<List<dynamic>>(
        '${_dio.options.baseUrl}/find?q=${Uri.encodeQueryComponent(term)}&app=$appName');
    return [...?a.data, ...?b.data];
  }

  Stream<dynamic> prices(Uri uri) {
    _prices = WebSocketChannel.connect(uri);
    return _prices!.stream;
  }

  Future<void> close() async => _prices?.sink.close();
}

const appName = 'goods';

/// A connector: the caller owns the channel it gets back.
WebSocketChannel openTicker(Uri uri) => WebSocketChannel.connect(uri);
