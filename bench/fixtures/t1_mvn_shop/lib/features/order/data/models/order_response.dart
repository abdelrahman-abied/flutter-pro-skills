import '../../domain/entities/order_entity.dart';

class OrderResponse {
  const OrderResponse({
    required this.id,
    required this.totalCents,
    required this.placedAt,
  });

  factory OrderResponse.fromJson(Map<String, dynamic> json) => OrderResponse(
        id: json['id'] as int,
        totalCents: json['total_cents'] as int,
        placedAt: DateTime.parse(json['placed_at'] as String),
      );

  final int id;
  final int totalCents;
  final DateTime placedAt;

  OrderEntity toEntity() =>
      OrderEntity(id: id, totalCents: totalCents, placedAt: placedAt);
}
