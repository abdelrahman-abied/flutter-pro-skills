import 'package:flutter/material.dart';

import '../../../data/repositories/habit_repository.dart';

class SyncScreen extends StatefulWidget {
  const SyncScreen({super.key, required this.repository});
  final HabitRepository repository;
  @override
  State<SyncScreen> createState() => _SyncScreenState();
}

class _SyncScreenState extends State<SyncScreen> {
  bool _isLoading = false;

  // K1-FN: under provider/setstate the State class is the logic. Stuck spinner on failure.
  Future<void> _check() async {
    setState(() => _isLoading = true);
    await widget.repository.plainAll();
    if (mounted) setState(() => _isLoading = false);
  }

  // Fine: the flag is reset in finally.
  Future<void> _checkSafely() async {
    setState(() => _isLoading = true);
    try {
      await widget.repository.plainAll();
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) => _isLoading
      ? const CircularProgressIndicator()
      : Row(children: [
          TextButton(onPressed: _check, child: const Text('sync')),
          TextButton(onPressed: _checkSafely, child: const Text('sync safely')),
        ]);
}
