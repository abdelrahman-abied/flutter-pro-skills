import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../models/severity.dart';

class OrdersState {
  const OrdersState({required this.severity});
  final Severity severity;
}

class OrdersCubit extends Cubit<OrdersState> {
  OrdersCubit() : super(const OrdersState(severity: Severity.ok));

  static Color blend(Color a, Color b) => Color.lerp(a, b, 0.5)!;
}
