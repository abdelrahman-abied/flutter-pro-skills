import 'package:meta/meta.dart';

@immutable
class ProductEntity {
  const ProductEntity({
    required this.id,
    required this.title,
    required this.priceCents,
    required this.imageUrl,
  });

  final int id;
  final String title;
  final int priceCents;
  final String imageUrl;
}
