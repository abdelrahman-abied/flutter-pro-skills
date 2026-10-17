import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../notifier/feed_notifier.dart';

class FeedView extends ConsumerWidget {
  const FeedView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(feedNotifierProvider);
    final title = ref.watch(bannerNotifierProvider).title;
    final formKey = GlobalKey<FormState>();
    final sorted = state.items..sort();
    return Form(
      key: formKey,
      child: Column(
        children: [
          Text(title),
          Expanded(
            child: ListView(
              children: sorted.map((item) => ListTile(title: Text(item))).toList(),
            ),
          ),
          SizedBox(
            height: 200,
            child: SingleChildScrollView(
              child: Column(
                children: [
                  const Text('Recent'),
                  ListView.builder(
                    shrinkWrap: true,
                    itemCount: state.items.length,
                    itemBuilder: (context, index) => Text(state.items[index]),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
