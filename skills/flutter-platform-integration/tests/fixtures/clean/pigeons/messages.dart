import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/src/messages.dart',
  kotlinOut: 'android/app/src/main/kotlin/Messages.g.kt',
))
@HostApi()
abstract class DeviceInfoApi {
  @async
  String model();
}
