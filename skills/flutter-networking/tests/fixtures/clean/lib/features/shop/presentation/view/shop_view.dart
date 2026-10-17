import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../notifier/shop_notifier.dart';

class ShopView extends ConsumerStatefulWidget {
  const ShopView({super.key});

  @override
  ConsumerState<ShopView> createState() => _ShopViewState();
}

class _ShopViewState extends ConsumerState<ShopView> {
  final _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onScroll);
  }

  void _onScroll() {
    final state = ref.read(shopNotifierProvider);
    if (_controller.position.extentAfter < 300 && !state.isLoading) {
      ref.read(shopNotifierProvider.notifier).fetchNextPage();
    }
    ref.read(shopNotifierProvider.notifier).loadMore();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(shopNotifierProvider);
    return Column(children: [
      TextButton(
        onPressed: () => launchUrl(Uri.parse('https://api.goods-demo.io/v2/terms')),
        child: const Text('Terms'),
      ),
      Image.network('https://img.goods-demo.io/banner.png'),
      Expanded(child: ListView(controller: _controller, children: [for (final i in state.items) Text(i.name)])),
    ]);
  }
}
