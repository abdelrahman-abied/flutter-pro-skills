import '../../domain/entities/product_entity.dart';

class ProductResponse {
  const ProductResponse({
    required this.id,
    required this.title,
    required this.priceCents,
    required this.imageUrl,
  });

  factory ProductResponse.fromJson(Map<String, dynamic> json) =>
      ProductResponse(
        id: json['id'] as int,
        title: json['title'] as String,
        priceCents: json['price_cents'] as int,
        imageUrl: json['image_url'] as String,
      );

  final int id;
  final String title;
  final int priceCents;
  final String imageUrl;

  ProductEntity toEntity() => ProductEntity(
        id: id,
        title: title,
        priceCents: priceCents,
        imageUrl: imageUrl,
      );
}
