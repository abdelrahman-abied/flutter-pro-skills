import 'package:flutter/material.dart';

class TiltedCards extends StatelessWidget {
  const TiltedCards({super.key});

  @override
  Widget build(BuildContext context) => const _Card(imageUrl: 'https://img-cdn-demo.io/travel/hills.jpg');
}

class _Card extends StatelessWidget {
  const _Card({required this.imageUrl});

  final String imageUrl;

  @override
  Widget build(BuildContext context) => Image.network(imageUrl);
}
