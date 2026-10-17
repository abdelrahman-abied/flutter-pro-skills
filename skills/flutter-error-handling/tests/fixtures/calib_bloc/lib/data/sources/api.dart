import 'package:http/http.dart' as http;

class Api {
  Api(this._c);
  final http.Client _c;
  Future<String> get() async => (await _c.get(Uri.parse('https://example.com'))).body;
}
