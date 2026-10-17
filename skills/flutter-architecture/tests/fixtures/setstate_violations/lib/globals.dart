// Global state, the setState way.
var counter = 0;
List<String> cart = [];
String? lastError;
final cache = <String, String>{};
const appName = 'demo';
late final DateTime startedAt;
void Function()? onLogout;

int bump() => ++counter;

class Config {
  static String baseUrl = 'https://example.com';
  static const timeout = Duration(seconds: 5);
  static final created = DateTime.now();
  String instanceField = 'not global';
}

enum Flavor { dev, prod }
