import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import '../../../../core/widgets/app_icon_button.dart';
import '../../../../core/widgets/fixed_scale.dart';

class ProfileView extends StatefulWidget {
  const ProfileView({super.key});

  @override
  State<ProfileView> createState() => _ProfileViewState();
}

class _ProfileViewState extends State<ProfileView> {
  final _otpController = TextEditingController();
  String _password = '';

  @override
  void dispose() {
    _otpController.dispose();
    super.dispose();
  }

  void _codeArrived(String otp) {
    SemanticsService.announce('Your code is $otp', TextDirection.ltr);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(icon: const Icon(Icons.share), onPressed: () {}),
          AppIconButton(icon: Icons.edit, onPressed: () {}),
        ],
      ),
      body: Column(
        children: [
          GestureDetector(onTap: () {}, child: const Icon(Icons.favorite)),
          Image.asset('assets/avatar.png'),
          Text('Name', textScaler: TextScaler.noScaling),
          SizedBox(width: 24, height: 24, child: IconButton(tooltip: 'Info', icon: const Icon(Icons.info), onPressed: () {})),
          TextButton(
            style: TextButton.styleFrom(tapTargetSize: MaterialTapTargetSize.shrinkWrap),
            onPressed: () {},
            child: const Text('More'),
          ),
          SizedBox(height: 20, child: Text('Fixed height label')),
          Semantics(label: 'One-time code', value: _otpController.text, child: const SizedBox()),
          Text('••••', semanticsLabel: _password),
          ExcludeSemantics(child: ElevatedButton(onPressed: () {}, child: const Text('Save'))),
          GestureDetector(excludeFromSemantics: true, onTap: () {}, child: const Text('Hidden action')),
          TextField(controller: _otpController, autofocus: true),
          TextField(autofocus: true, onChanged: (v) => _password = v),
          MediaQuery.withClampedTextScaling(maxScaleFactor: 1.5, child: const Text('Capped')),
          FixedScale(child: const Text('Never scales')),
        ],
      ),
    );
  }
}
