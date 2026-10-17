import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/feed_notifier.dart';
import '../widget/post_tile.dart';

class GalleryView extends ConsumerWidget {
  const GalleryView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final urls = ref.watch(galleryNotifierProvider.select((s) => s.items));
    return ListView.builder(
      itemCount: urls.length,
      itemBuilder: (context, index) {
        if (index.isOdd) {
          return PostTile(url: urls[index]);
        }
        return IntrinsicHeight(
          child: Row(
            children: [
              Image.network(urls[index], width: 64, height: 64),
              Expanded(
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                  child: Opacity(
                    opacity: 0.6,
                    child: ShaderMask(
                      shaderCallback: (rect) => const LinearGradient(colors: [Colors.black, Colors.white])
                          .createShader(rect),
                      child: Text(urls[index]),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
