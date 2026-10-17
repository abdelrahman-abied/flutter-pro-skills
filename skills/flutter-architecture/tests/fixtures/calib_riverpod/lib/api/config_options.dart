// K3 A3: an abstract class with only static members is a namespace, not a contract
import 'package:hooks_riverpod/hooks_riverpod.dart';

abstract class ConfigOptions {
  static final mode = Provider<int>((ref) => 0);
}
