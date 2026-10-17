import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/cart_notifier.dart';

enum Filter { all, open, done }

const _tabs = ['Home', 'Search', 'Profile'];

class ShopView extends ConsumerWidget {
  const ShopView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(cartProvider.select((s) => s.items));
    final total = ref.watch(cartProvider.select((s) => s.total));
    final orders = ref.watch(ordersProvider).valueOrNull ?? const [];
    final loading = ref.watch(ordersProvider).isLoading;
    final settings = ref.watch(settingsProvider);
    final notifier = ref.watch(cartProvider.notifier);
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(child: Text('${settings.title} ${settings.total} $total $loading $notifier')),
        SliverToBoxAdapter(
          child: Column(children: _tabs.map((t) => Text(t)).toList()),
        ),
        SliverToBoxAdapter(
          child: Wrap(children: Filter.values.map((f) => Chip(label: Text(f.name))).toList()),
        ),
        SliverToBoxAdapter(
          child: Row(children: List.generate(5, (i) => const Icon(Icons.star))),
        ),
        SliverList.builder(
          itemCount: items.length,
          itemBuilder: (context, index) => ListTile(
            leading: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.network(items[index], width: 48, cacheWidth: 144),
            ),
            title: Opacity(opacity: 1, child: Text(items[index])),
            trailing: CachedNetworkImage(imageUrl: items[index], memCacheWidth: 120),
          ),
        ),
        SliverGrid.builder(
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3),
          itemCount: orders.length,
          itemBuilder: (context, index) => Image(image: ResizeImage(NetworkImage(orders[index]), width: 200)),
        ),
      ],
    );
  }
}

class StaticPanel extends StatelessWidget {
  const StaticPanel({super.key, required this.lines});

  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    // Not a scroll view: a Column over a few lines is fine, and so is a shrink-wrapped dialog list.
    return Column(
      children: [
        const Opacity(opacity: 0.5, child: Text('static translucency is cheap enough here')),
        IntrinsicHeight(child: Row(children: lines.map(Text.new).toList())),
        ListView(shrinkWrap: true, children: const [Text('a'), Text('b')]),
        ListView(children: const [Text('literal'), Text('children')]),
      ],
    );
  }
}

class Pager extends StatelessWidget {
  const Pager({super.key, required this.urls});

  final List<String> urls;

  @override
  Widget build(BuildContext context) {
    // Pages are full-screen: full-size decode and a blur per page are expected.
    return PageView.builder(
      itemCount: urls.length,
      itemBuilder: (context, index) => Image.network(urls[index]),
    );
  }
}
