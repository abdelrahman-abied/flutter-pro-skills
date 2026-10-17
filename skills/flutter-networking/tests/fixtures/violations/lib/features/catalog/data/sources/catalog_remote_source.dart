import 'package:dio/dio.dart';
import 'package:http/http.dart' as http;

class CatalogRemoteSource {
  Future<List<Map<String, dynamic>>> fetchProducts(int page) async {
    final dio = Dio();
    final res = await dio.get<List<dynamic>>('https://api.shop-demo.io/v1/products', queryParameters: {'page': page});
    return (res.data ?? const []).cast<Map<String, dynamic>>();
  }

  Future<String> search(String query) async {
    final client = http.Client();
    final res = await client.get(Uri.parse('https://api.shop-demo.io/v1/search?q=$query'));
    return res.body;
  }

  Future<String> legacyBanner() async {
    final res = await http.get(Uri.https('cdn.shop-demo.io', '/banner.json'));
    return res.body;
  }

  Future<Response<dynamic>> detail(Dio dio, String id) =>
      dio.get<dynamic>('/products/$id', cancelToken: CancelToken());
}
