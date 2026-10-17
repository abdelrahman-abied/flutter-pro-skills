import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiClient {
  final http.Client _client;
  ApiClient(this._client);

  Future<List<Map<String, Object?>>> getTodos() async {
    final res = await _client.get(Uri.parse('https://example.com/todos'));
    if (res.statusCode != 200) throw http.ClientException('status ${res.statusCode}');
    return (jsonDecode(res.body) as List).cast<Map<String, Object?>>();
  }
}
