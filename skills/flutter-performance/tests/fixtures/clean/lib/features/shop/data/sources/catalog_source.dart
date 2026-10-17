import 'dart:convert';
import 'dart:isolate';

import 'package:flutter/foundation.dart';

List<Map<String, dynamic>> parseProducts(String body) =>
    (jsonDecode(body) as List<dynamic>).cast<Map<String, dynamic>>();

class CatalogSource {
  // A Map payload (one object) is cheap to decode inline.
  Map<String, dynamic> decodeProduct(String body) => jsonDecode(body) as Map<String, dynamic>;

  // List payloads are parsed off the UI isolate.
  Future<List<Map<String, dynamic>>> decodeProducts(String body) =>
      Isolate.run(() => (jsonDecode(body) as List<dynamic>).cast<Map<String, dynamic>>());

  Future<List<Map<String, dynamic>>> decodeWithCompute(String body) => compute(parseProducts, body);
}
