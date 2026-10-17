import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:pretty_dio_logger/pretty_dio_logger.dart';

// SEC-005 (PrettyDioLogger prints response bodies by default) and SEC-006 (validateCertificate => true).
Dio createClient() {
  final dio = Dio()..interceptors.add(PrettyDioLogger(requestHeader: true));
  dio.httpClientAdapter = IOHttpClientAdapter(validateCertificate: (cert, host, port) => true);
  return dio;
}
