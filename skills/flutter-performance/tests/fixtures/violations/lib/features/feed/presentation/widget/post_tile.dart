import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

class PostTile extends StatelessWidget {
  const PostTile({super.key, required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return ClipPath(
      clipper: const ShapeBorderClipper(shape: StadiumBorder()),
      child: CachedNetworkImage(imageUrl: url, width: 80, height: 80),
    );
  }
}
