// GUARDS: private `_onTap` handler (on-named-method must not fire) and
// controllers released generically with
// `for (final c in [a, b]) c.dispose()` (undisposed-resource must not fire).
import 'package:flutter/material.dart';

class CheckoutForm extends StatefulWidget {
  const CheckoutForm({super.key, required this.initialName});

  final String initialName;

  @override
  State<CheckoutForm> createState() => _CheckoutFormState();
}

class _CheckoutFormState extends State<CheckoutForm> {
  late final _name = TextEditingController(text: widget.initialName);
  final _email = TextEditingController();

  void _onTap() {
    FocusScope.of(context).unfocus();
  }

  @override
  void dispose() {
    for (final c in [_name, _email]) c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _onTap,
      child: Column(
        children: [
          TextField(controller: _name),
          TextField(controller: _email),
        ],
      ),
    );
  }
}
