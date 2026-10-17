import 'package:flutter/material.dart';
import 'package:flutter_hooks/flutter_hooks.dart';

/// Hooks own the controller and focus node; a phone field with the phone keyboard.
class SearchPage extends HookWidget {
  const SearchPage({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = useTextEditingController();
    final focus = useFocusNode();
    final phone = useTextEditingController();
    return Column(
      children: [
        TextField(controller: controller, focusNode: focus, decoration: const InputDecoration(hintText: 'Search email')),
        TextField(
          controller: phone,
          keyboardType: TextInputType.phone,
          autofillHints: const [AutofillHints.telephoneNumber],
          decoration: const InputDecoration(labelText: 'Phone'),
        ),
        Text('typed: $controller.text'),
      ],
    );
  }
}
