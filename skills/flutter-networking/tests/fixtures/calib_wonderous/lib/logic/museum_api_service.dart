import 'package:http/http.dart' as http;

class MuseumApiService {
  MuseumApiService(this._client);

  final http.Client _client;
  final String _baseApiUrl = 'https://api.museum-demo.org/public/v1';
  final String _imageHost = 'https://media.museum-demo.org/img/';

  Future<String> search(String query) async {
    // A String parameter in a request query string still fires (TP: NET-010).
    final res = await _client.get(Uri.parse('$_baseApiUrl/search?q=$query'));
    return res.body;
  }

  String imageFor(String id) => '$_imageHost$id.jpg';
}
