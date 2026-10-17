@Tags(['real'])
library;

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

// Deliberately hits the real backend; exempt from TEST-real-network (path real/ and the tag).
void main() {
  test('backend is up', () async {
    final res = await Dio().get<Object?>('https://example.com/health');
    expect(res.statusCode, 200);
  }, skip: 'needs network; run with --run-skipped');
}
