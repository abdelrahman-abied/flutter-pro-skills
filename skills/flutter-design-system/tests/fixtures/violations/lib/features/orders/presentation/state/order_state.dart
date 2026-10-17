import 'package:flutter/material.dart';

class OrderState {
  const OrderState({required this.title, required this.statusColor, required this.statusIcon});

  final String title;
  final Color statusColor;
  final IconData statusIcon;
}
