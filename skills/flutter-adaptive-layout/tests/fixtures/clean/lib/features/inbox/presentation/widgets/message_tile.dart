import 'package:flutter/material.dart';
import 'package:universal_io/io.dart';

class MessageTile extends StatefulWidget {
  const MessageTile({super.key, required this.onArchive});
  final VoidCallback onArchive;

  @override
  State<MessageTile> createState() => _MessageTileState();
}

class _MessageTileState extends State<MessageTile> {
  bool _hovered = false;
  bool _showActions = false;

  @override
  Widget build(BuildContext context) {
    final cupertino = Platform.isIOS;
    return Focus(
      onFocusChange: (focused) => setState(() => _showActions = focused),
      child: MouseRegion(
        onEnter: (_) => setState(() {
          _hovered = true;
          _showActions = true;
        }),
        onExit: (_) => setState(() {
          _hovered = false;
          _showActions = false;
        }),
        child: Container(
          color: _hovered ? Theme.of(context).hoverColor : null,
          child: Row(
            children: [
              Text(cupertino ? 'Message' : 'Message'),
              if (_showActions) IconButton(icon: const Icon(Icons.archive), onPressed: widget.onArchive),
            ],
          ),
        ),
      ),
    );
  }
}
