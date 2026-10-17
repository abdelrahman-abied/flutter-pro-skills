import 'package:flutter/material.dart';

import '../../../../core/widgets/app_text_field.dart';

class SecurityView extends StatefulWidget {
  const SecurityView({super.key});

  @override
  State<SecurityView> createState() => _SecurityViewState();
}

class _SecurityViewState extends State<SecurityView> {
  final _pinController = TextEditingController();
  final _apiKeyController = TextEditingController();
  final _phoneController = TextEditingController();

  @override
  void dispose() {
    _pinController.dispose();
    _apiKeyController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AppTextField(label: 'PIN', controller: _pinController),
        TextField(
          controller: _apiKeyController,
          decoration: const InputDecoration(labelText: 'API key'),
        ),
        TextField(
          controller: _phoneController,
          keyboardType: TextInputType.text,
          decoration: const InputDecoration(labelText: 'Phone number'),
        ),
      ],
    );
  }
}
