import 'package:flutter/material.dart';

import '../../auth/data/session_cache.dart';
import '../../auth/domain/user.dart';
import '../domain/profile.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key, required this.cache});
  final SessionCache cache;

  @override
  Widget build(BuildContext context) {
    final User? user = cache.user;
    return Text(Profile(user?.name ?? '').displayName);
  }
}
