import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/layout/window_size_class.dart';
import '../widgets/message_tile.dart';

class InboxView extends StatefulWidget {
  const InboxView({super.key});

  @override
  State<InboxView> createState() => _InboxViewState();
}

class _InboxViewState extends State<InboxView> {
  String? _selectedId;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final tall = size.height > 700;
    final isTablet = WindowSizeClass.fromWidth(size.width) != WindowSizeClass.compact;
    final cupertino = defaultTargetPlatform == TargetPlatform.iOS;
    final turns = _quarterTurns(MediaQuery.orientationOf(context));
    return LayoutBuilder(
      builder: (context, constraints) {
        final sizeClass = WindowSizeClass.fromWidth(constraints.maxWidth);
        final tile = MessageTile(onArchive: () => setState(() => _selectedId = null));
        if (sizeClass == WindowSizeClass.expanded) {
          return Row(children: [Expanded(child: tile), Expanded(child: Text(_selectedId ?? ''))]);
        }
        return RotatedBox(quarterTurns: turns, child: tall || isTablet || cupertino ? tile : const SizedBox());
      },
    );
  }

  int _quarterTurns(Orientation o) => 0;
}

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key, required this.photo});
  final Size photo;

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  }

  @override
  void dispose() {
    SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final big = widget.photo.width > 1000;
    final sideWidth = MediaQuery.sizeOf(context).width / 2;
    return Text(big && sideWidth >= 250 ? 'large' : 'small');
  }
}
