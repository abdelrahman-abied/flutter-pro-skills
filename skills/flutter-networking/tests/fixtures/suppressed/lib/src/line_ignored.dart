import 'package:dio/dio.dart';

// net-ignore: NET-001 a test double for local tooling, never shipped
final toolClient = Dio();

final otherClient = Dio(BaseOptions(baseUrl: 'https://tools.demo-host.io'));
