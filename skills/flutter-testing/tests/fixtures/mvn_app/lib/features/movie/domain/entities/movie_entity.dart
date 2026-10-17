import 'package:meta/meta.dart';

@immutable
class MovieEntity {
  final String id;
  final String title;
  const MovieEntity({required this.id, required this.title});
}
