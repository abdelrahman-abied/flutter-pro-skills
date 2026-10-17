import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../database/database.dart';

class BackupDialog extends ConsumerWidget {
  const BackupDialog({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return TextButton(
      onPressed: () async {
        final db = ref.read(AppDatabase.provider);
        await db.close();
        // ... replace the file with the restored backup, then re-open
        ref.read(AppDatabase.provider.notifier).state = AppDatabase();
      },
      child: const Text('Restore'),
    );
  }
}

class ExportButton extends StatelessWidget {
  const ExportButton({super.key});

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () async {
        final db = AppDatabase();
        await db.customStatement('VACUUM');
      },
      child: const Text('Export'),
    );
  }
}
