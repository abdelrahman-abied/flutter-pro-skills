import 'package:permission_handler/permission_handler.dart';

enum CameraAccess { granted, denied, blocked }

class PermissionService {
  Future<CameraAccess> requestCamera() async {
    final status = await Permission.camera.request();
    if (status.isGranted) return CameraAccess.granted;
    if (status.isPermanentlyDenied || status.isRestricted) return CameraAccess.blocked;
    return CameraAccess.denied;
  }

  Future<bool> openSettings() => openAppSettings();
}
