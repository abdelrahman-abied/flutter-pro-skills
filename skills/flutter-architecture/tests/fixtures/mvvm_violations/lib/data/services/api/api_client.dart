import 'package:http/http.dart' as http;

import 'model/home_response.dart';

class ApiClient {
  Future<HomeResponse> fetchHome() async {
    final res = await http.get(Uri.parse('https://example.com/home'));
    return HomeResponse(res.body.split(','));
  }
}
