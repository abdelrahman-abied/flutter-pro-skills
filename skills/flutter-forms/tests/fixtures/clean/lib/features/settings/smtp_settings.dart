import 'package:flutter/material.dart';

/// Third-party credentials: obscured, but no account autofill hints (they are not the user's login).
class SmtpSettings extends StatefulWidget {
  const SmtpSettings({super.key, required this.apiKey});

  final String apiKey;

  @override
  State<SmtpSettings> createState() => _SmtpSettingsState();
}

class _SmtpSettingsState extends State<SmtpSettings> {
  final _smtpPasswordController = TextEditingController();
  final _templateController = TextEditingController();

  @override
  void dispose() {
    _smtpPasswordController.dispose();
    _templateController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextField(
          controller: _smtpPasswordController,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'SMTP password'),
        ),
        TextField(
          controller: _templateController,
          keyboardType: TextInputType.multiline,
          maxLines: null,
          decoration: const InputDecoration(labelText: 'Email template'),
        ),
        TextFormField(
          readOnly: true,
          initialValue: widget.apiKey,
          decoration: const InputDecoration(labelText: 'API key'),
        ),
        TextFormField(
          initialValue: '',
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Password minimum length'),
        ),
      ],
    );
  }
}
