import 'package:flutter/material.dart';

import '../../../../l10n/gen/app_localizations.dart';

class EditNameField extends StatefulWidget {
  const EditNameField({
    super.key,
    required this.initialName,
    required this.onSave,
  });

  final String initialName;
  final ValueChanged<String> onSave;

  @override
  State<EditNameField> createState() => _EditNameFieldState();
}

class _EditNameFieldState extends State<EditNameField> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.initialName);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _controller,
            decoration: InputDecoration(labelText: l10n.nameLabel),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: () => widget.onSave(_controller.text.trim()),
          child: Text(l10n.saveButton),
        ),
      ],
    );
  }
}
