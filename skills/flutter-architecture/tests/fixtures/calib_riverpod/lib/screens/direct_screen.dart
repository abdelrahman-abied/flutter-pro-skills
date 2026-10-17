// true positive kept: the widget constructs the service -> ARCH-005 high
import 'package:flutter/widgets.dart';
import '../api/user_service.dart';

class DirectScreen extends StatelessWidget {
  const DirectScreen({super.key});
  @override
  Widget build(BuildContext context) {
    UserService().fetch();
    return const SizedBox();
  }
}
