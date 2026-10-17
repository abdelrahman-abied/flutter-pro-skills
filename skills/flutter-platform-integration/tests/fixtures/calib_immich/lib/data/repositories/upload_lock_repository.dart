import 'package:flutter/services.dart';

import '../../platform/upload_lock_api.g.dart';

class UploadLockRepository {
  UploadLockRepository(this._api);

  final UploadLockApi _api;

  Future<bool> lock() async {
    try {
      await _api.lock();
      return true;
    } on PlatformException {
      return false;
    }
  }
}
