import 'package:flutter/material.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _scroll = ScrollController();

  // K2: a best-effort scroll is low, not high.
  void _scrollToEnd() {
    try {
      _scroll.jumpTo(_scroll.position.maxScrollExtent);
    } catch (e) {
      return;
    }
  }

  @override
  Widget build(BuildContext context) =>
      ListView(controller: _scroll, children: [TextButton(onPressed: _scrollToEnd, child: const Text('end'))]);
}
