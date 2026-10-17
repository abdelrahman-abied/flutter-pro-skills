import 'package:meta/meta.dart';

@immutable
class OrderEntity {
  const OrderEntity({
    required this.id,
    required this.totalCents,
    required this.placedAt,
  });

  final int id;
  final int totalCents;
  final DateTime placedAt;
}
