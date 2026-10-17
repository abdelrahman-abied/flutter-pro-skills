import 'dart:async';

import 'package:flutter/material.dart';

import 'data/repositories/upload_lock_repository.dart';
import 'platform/upload_lock_api.g.dart';
import 'presentation/pages/upload_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  unawaited(UploadLockRepository(UploadLockApi()).lock());
  runApp(const MaterialApp(home: UploadPage()));
}
