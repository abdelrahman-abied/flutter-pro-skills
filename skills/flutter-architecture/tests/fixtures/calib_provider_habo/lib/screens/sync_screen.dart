// K1 FN2: a hand-rolled locator in the UI -> ARCH-104
import 'package:flutter/material.dart';
import '../services/service_locator.dart';

class SyncScreen extends StatefulWidget {
  const SyncScreen({super.key});
  @override
  State<SyncScreen> createState() => _SyncScreenState();
}

class _SyncScreenState extends State<SyncScreen> {
  bool _isLoading = false;
  Future<void> _check() async {
    setState(() => _isLoading = true);
    await ServiceLocator.instance.syncService.sync();
    if (mounted) setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) =>
      _isLoading ? const CircularProgressIndicator() : TextButton(onPressed: _check, child: const Text('x'));
}
