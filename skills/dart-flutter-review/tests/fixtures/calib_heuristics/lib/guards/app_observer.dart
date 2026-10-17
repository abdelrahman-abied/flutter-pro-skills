// K2 R1 / K3 R4: framework overrides are named by the framework (BlocObserver, PageRoute, GetX, Dio).
import 'package:flutter/material.dart';

class AppObserver extends BlocObserver {
  @override
  void onChange(BlocBase<dynamic> bloc, Change<dynamic> change) {
    super.onChange(bloc, change);
  }

  @override
  void onError(BlocBase<dynamic> bloc, Object error, StackTrace stackTrace) {}
}

class FadeRoute<T> extends PageRoute<T> {
  @override
  Widget buildPage(BuildContext context, Animation<double> a, Animation<double> b) => const SizedBox();

  @override
  @protected
  Widget buildTransitions(BuildContext context, Animation<double> a, Animation<double> b, Widget child) => child;
}

class HomeController extends GetxController {
  @override
  void onInit() {
    super.onInit();
  }
}

class AuthInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {}
}
