import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../model/list_controllers.dart';

class ArchiveScreen extends ConsumerStatefulWidget {
  const ArchiveScreen({super.key});

  @override
  ConsumerState<ArchiveScreen> createState() => _ArchiveScreenState();
}

class _ArchiveScreenState extends ConsumerState<ArchiveScreen> {
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 300) {
      final current = ref.read(archiveProvider).value;
      if (current != null && !current.isLoading) {
        ref.read(archiveProvider.notifier).fetchNext();
      }
      ref.read(timelineProvider.notifier).fetchNext();
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final rows = ref.watch(threadProvider).value?.rows ?? const <String>[];
    return ListView.builder(
      controller: _scroll,
      itemCount: rows.length + 1,
      itemBuilder: (context, index) {
        if (index == 0) {
          return TextButton(
            onPressed: () => ref.read(threadProvider.notifier).fetchMore(),
            child: const Text('Older'),
          );
        }
        return Text(rows[index - 1]);
      },
    );
  }
}

/// Browser links to the app's own website (FP cause: NET-008 on url_launcher links).
class AboutLinks extends StatelessWidget {
  const AboutLinks({super.key});

  @override
  Widget build(BuildContext context) => TextButton(
        onPressed: () => launchUrl(Uri.parse('https://board-demo.org/about')),
        child: const Text('About'),
      );
}
