import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../../utils/result.dart';
import 'model/booking_api_model.dart';

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  Future<Result<List<BookingApiModel>>> getBookings() async {
    try {
      final res = await _client.get(Uri.parse('https://example.com/booking'));
      final list = jsonDecode(res.body) as List<dynamic>;
      return Result.ok([for (final j in list) BookingApiModel.fromJson(j as Map<String, dynamic>)]);
    } on Exception catch (e) {
      return Result.error(e);
    }
  }
}
