import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

class OtpCubit extends Cubit<bool> {
  OtpCubit() : super(false);
  Future<void> verify(String code) async {}
}

/// Bloc version: the button dispatches to the cubit and is disabled while busy.
class OtpPage extends StatelessWidget {
  const OtpPage({super.key});

  @override
  Widget build(BuildContext context) {
    final isSubmitting = context.watch<OtpCubit>().state;
    return Column(
      children: [
        TextField(
          keyboardType: TextInputType.number,
          autofillHints: const [AutofillHints.oneTimeCode],
          inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
          decoration: const InputDecoration(labelText: 'Verification code'),
          onChanged: (code) {
            debugPrint('otp length: ${code.length}');
            if (code.length == 6) context.read<OtpCubit>().verify(code);
          },
        ),
        ElevatedButton(
          onPressed: isSubmitting ? null : () => context.read<OtpCubit>().verify(''),
          child: const Text('Verify'),
        ),
      ],
    );
  }
}
