import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class OtpField extends StatelessWidget {
  const OtpField({super.key, required this.analytics, required this.onCompleted});

  final dynamic analytics;
  final ValueChanged<String> onCompleted;

  @override
  Widget build(BuildContext context) {
    return TextField(
      keyboardType: TextInputType.number,
      decoration: const InputDecoration(labelText: 'One-time code'),
      onChanged: (code) {
        analytics.logEvent(name: 'otp_typed', parameters: {'code': code});
        if (kDebugMode) {
          debugPrint('otp: $code');
        }
        if (code.length == 6) onCompleted(code);
      },
    );
  }
}
