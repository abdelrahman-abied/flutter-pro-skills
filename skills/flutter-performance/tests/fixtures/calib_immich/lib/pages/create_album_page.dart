import 'package:flutter/material.dart';
import 'package:flutter_hooks/flutter_hooks.dart';

// FP 3: a TextEditingController listener named *Controller is not an animation (PERF-009 must not fire).
class CreateAlbumPage extends StatefulWidget {
  const CreateAlbumPage({super.key});

  @override
  State<CreateAlbumPage> createState() => _CreateAlbumPageState();
}

class _CreateAlbumPageState extends State<CreateAlbumPage> {
  final albumTitleController = TextEditingController();
  final inputController = TextEditingController();

  @override
  void initState() {
    super.initState();
    albumTitleController.addListener(_onTitleChanged);
    inputController.addListener(() {
      setState(() {});
    });
  }

  void _onTitleChanged() {
    setState(() {});
  }

  @override
  void dispose() {
    albumTitleController.dispose();
    inputController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(controller: albumTitleController);
}

// TP 3: a hook widget that makes a new form key on every build (PERF-007 still fires, with the hooks fix).
class LoginForm extends HookWidget {
  const LoginForm({super.key});

  @override
  Widget build(BuildContext context) {
    final isSecretFieldOn = useState<bool>(false);
    final loginFormKey = GlobalKey<FormState>();
    return Form(key: loginFormKey, child: Text('${isSecretFieldOn.value}'));
  }
}
