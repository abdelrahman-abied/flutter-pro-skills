// K3 A4: dio only for CancelToken, a service reached through its provider -> no ARCH-007 under riverpod
// K3 A17: an extension on BuildContext is not logic -> no ARCH-102
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import '../api/user_service.dart';

class HomeNotifier extends Notifier<int> {
  CancelToken? _token;
  @override
  int build() {
    ref.watch(userServiceProvider);
    return 0;
  }
}

extension HomeX on BuildContext {
  bool get wide => MediaQuery.sizeOf(this).width > 600;
}
