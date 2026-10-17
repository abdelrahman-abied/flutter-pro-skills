import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

/// Factory: the caller owns the client it gets back.
http.Client createHttpClient() {
  final inner = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  return IOClient(inner);
}

class StatusProbe {
  StatusProbe({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<int> ping(Uri uri) async {
    final res = await _client.get(uri).timeout(const Duration(seconds: 5));
    return res.statusCode;
  }

  /// One-off client, closed in finally (the Flutter compass sample's style).
  Future<int> pingOnce(Uri uri) async {
    final client = http.Client();
    try {
      return (await client.head(uri)).statusCode;
    } finally {
      client.close();
    }
  }

  void close() => _client.close();
}
