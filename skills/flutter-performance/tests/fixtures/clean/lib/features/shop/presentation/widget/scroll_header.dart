import 'package:flutter/material.dart';
import 'package:flutter_hooks/flutter_hooks.dart';

class ScrollHeader extends StatefulWidget {
  const ScrollHeader({super.key, required this.panel});

  final ValueNotifier<bool> panel;

  @override
  State<ScrollHeader> createState() => _ScrollHeaderState();
}

class _ScrollHeaderState extends State<ScrollHeader> with SingleTickerProviderStateMixin {
  final ScrollController _scroll = ScrollController();
  final TextEditingController _searchController = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final AnimationController _fade = AnimationController(vsync: this, duration: const Duration(seconds: 1));
  GlobalKey? _lazyKey;
  bool _collapsed = false;
  List<String> _names = [];

  @override
  void initState() {
    super.initState();
    _names = ['b', 'a']..sort();
    _scroll.addListener(() {
      final collapsed = _scroll.offset > 120;
      if (collapsed != _collapsed) {
        setState(() => _collapsed = collapsed);
      }
    });
    _searchController.addListener(() => setState(() {}));
    widget.panel.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _scroll.dispose();
    _searchController.dispose();
    _fade.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _lazyKey ??= GlobalKey();
    return Form(
      key: _formKey,
      child: Column(
        children: [
          FadeTransition(opacity: _fade, child: Text('${_names.length} $_collapsed', key: _lazyKey)),
          AnimatedOpacity(opacity: _collapsed ? 0 : 1, duration: const Duration(milliseconds: 200), child: const Text('hi')),
          Expanded(child: ListView.builder(controller: _scroll, itemBuilder: (c, i) => Text('$i'))),
        ],
      ),
    );
  }
}

class HookForm extends HookWidget {
  const HookForm({super.key});

  @override
  Widget build(BuildContext context) {
    final formKey = useMemoized(() => GlobalKey<FormState>());
    return Form(key: formKey, child: const SizedBox());
  }
}
