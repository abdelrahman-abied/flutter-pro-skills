import 'package:flutter/material.dart';

class ShareLinkForm extends StatelessWidget {
  const ShareLinkForm({super.key, required this.passwordController, required this.emailController});

  final TextEditingController passwordController;
  final TextEditingController emailController;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // form-ignore: FORM-001 the owner sets a share-link password and must be able to read it back
        TextField(controller: passwordController),
        TextField(
          // form-ignore: FORM-007 legacy accounts log in with a username in this field
          controller: emailController,
        ),
        TextField(controller: TextEditingController()),
      ],
    );
  }
}
