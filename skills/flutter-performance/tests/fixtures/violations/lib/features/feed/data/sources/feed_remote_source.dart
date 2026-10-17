import 'dart:convert';

import 'package:http/http.dart' as http;

class FeedRemoteSource {
  FeedRemoteSource(this._client);

  final http.Client _client;

  Future<List<Map<String, dynamic>>> fetchPosts() async {
    final response = await _client.get(Uri.parse('https://api.example.com/posts'));
    final list = jsonDecode(response.body) as List<dynamic>;
    return list.cast<Map<String, dynamic>>();
  }
}
