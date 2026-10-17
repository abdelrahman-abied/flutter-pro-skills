import 'package:flutter/material.dart';

class FadeBanner extends StatefulWidget {
  const FadeBanner({super.key});

  @override
  State<FadeBanner> createState() => _FadeBannerState();
}

class _FadeBannerState extends State<FadeBanner> with SingleTickerProviderStateMixin {
  late final AnimationController _fade = AnimationController(vsync: this, duration: const Duration(seconds: 1));
  final ScrollController _scroll = ScrollController();
  double _offset = 0;

  @override
  void initState() {
    super.initState();
    _fade.addListener(() => setState(() {}));
    _scroll.addListener(_handleScroll);
  }

  void _handleScroll() {
    setState(() => _offset = _scroll.offset);
  }

  @override
  void dispose() {
    _fade.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _fade,
      builder: (context, child) => Opacity(opacity: _fade.value, child: child),
      child: ListView(controller: _scroll, children: [Text('$_offset')]),
    );
  }
}
