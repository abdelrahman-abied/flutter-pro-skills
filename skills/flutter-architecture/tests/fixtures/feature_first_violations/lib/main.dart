import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/widgets/app_scaffold.dart';

void main() => runApp(const ProviderScope(child: MaterialApp(home: AppScaffold())));
