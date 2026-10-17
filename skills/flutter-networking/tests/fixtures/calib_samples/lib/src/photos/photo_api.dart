import 'package:http/http.dart' as http;

import '../../access_key.dart';

final _apiBase = Uri.parse('https://api.photos-demo.io/');

/// The class holds an injected client but two calls bypass it (TP: NET-009, with the injected-client note).
class PhotoApi {
  PhotoApi({http.Client? httpClient}) : _client = httpClient ?? http.Client();

  final http.Client _client;

  Future<String> search(String term) async =>
      (await _client.get(_apiBase.replace(path: '/search/photos', queryParameters: {'query': term}))).body;

  Future<List<int>> download(Uri uri) => http.readBytes(uri);

  Future<int> track(Uri uri) async => (await http.get(uri)).statusCode;

  /// A constant interpolated into a query is safe (FP cause: NET-010 on constants).
  String credit() => 'https://photos-demo.io/?utm_source=$photoAppName&utm_medium=referral';
}
