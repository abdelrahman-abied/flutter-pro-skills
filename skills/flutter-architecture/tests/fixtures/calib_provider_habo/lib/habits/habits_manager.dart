// K1 FN1: a ChangeNotifier "manager" is presentation logic (ARCH-102 and ARCH-009 are true positives)
import 'package:flutter/material.dart';
import '../services/sync_service.dart';

class HabitsManager extends ChangeNotifier {
  HabitsManager(this._sync);
  final SyncService _sync;
  BuildContext? _context;
  void setContext(BuildContext c) => _context = c;
  Future<void> save() async {
    await _sync.sync();
    ScaffoldMessenger.of(_context!).showSnackBar(const SnackBar(content: Text('ok')));
  }
}
