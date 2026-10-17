// GUARD: `Route<dynamic>` and `Map<String, dynamic>` are type arguments,
// not `dynamic` declarations (dynamic-in-api must not fire).
import 'package:flutter/material.dart';

import '../features/cart/presentation/view/checkout_form.dart';

Route<dynamic> buildRoute(RouteSettings settings) {
  final args = settings.arguments as Map<String, dynamic>? ?? const {};
  return MaterialPageRoute<dynamic>(
    builder: (_) => CheckoutForm(initialName: '${args['name'] ?? ''}'),
  );
}
