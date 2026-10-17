import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(dartOut: 'lib/platform/upload_lock_api.g.dart'))
@HostApi()
abstract class UploadLockApi {
  void lock();
  void unlock();
}
