// adapt-ignore-file: ADAPT-002 a native-only debug overlay, never built for previews
import 'dart:io';

import 'package:flutter/material.dart';

class HostBanner extends StatelessWidget {
  const HostBanner({super.key});

  @override
  Widget build(BuildContext context) => Text(Platform.isAndroid ? 'Android' : 'other');
}

class HostFooter extends StatelessWidget {
  const HostFooter({super.key});

  @override
  Widget build(BuildContext context) => Text(Platform.isIOS ? 'iOS' : 'other');
}
