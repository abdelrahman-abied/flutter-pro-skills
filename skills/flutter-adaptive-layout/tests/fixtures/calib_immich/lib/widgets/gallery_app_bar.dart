import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_ui/shared_ui.dart';

class GalleryAppBar extends StatelessWidget {
  const GalleryAppBar({super.key});

  @override
  Widget build(BuildContext context) {
    final wideApple = defaultTargetPlatform == TargetPlatform.iOS && !context.isNarrow;
    return SizedBox(height: wideApple ? 72 : 56);
  }
}

class AlbumHeader extends StatelessWidget {
  const AlbumHeader({super.key});

  @override
  Widget build(BuildContext context) {
    final isTablet = defaultTargetPlatform == TargetPlatform.iOS;
    return SizedBox(height: isTablet ? 120 : 80);
  }
}
