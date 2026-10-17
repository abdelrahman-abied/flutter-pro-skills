import 'package:flutter/material.dart';

import '../../platform/upload_lock_api.g.dart';

class UploadPage extends StatefulWidget {
  const UploadPage({super.key});

  @override
  State<UploadPage> createState() => _UploadPageState();
}

class _UploadPageState extends State<UploadPage> {
  final _api = UploadLockApi();

  @override
  Widget build(BuildContext context) {
    return TextButton(onPressed: () => _api.unlock(), child: const Text('Unlock'));
  }
}
