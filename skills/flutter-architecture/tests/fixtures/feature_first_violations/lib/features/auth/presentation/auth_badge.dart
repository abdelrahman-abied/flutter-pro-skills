import 'package:flutter/material.dart';

import '../../profile/domain/profile.dart';

class AuthBadge extends StatelessWidget {
  const AuthBadge({super.key, this.profile});
  final Profile? profile;

  @override
  Widget build(BuildContext context) => Text(profile?.displayName ?? 'guest');
}
