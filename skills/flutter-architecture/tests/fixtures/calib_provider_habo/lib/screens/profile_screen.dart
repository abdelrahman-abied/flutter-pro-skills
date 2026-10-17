// K1 FN3: SDK-singleton I/O in a widget -> ARCH-101 (and ARCH-005 for the import)
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) => TextButton(
        onPressed: () async => Supabase.instance.client.auth.signOut(),
        child: const Text('out'),
      );
}
