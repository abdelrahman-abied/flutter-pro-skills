import '../../../domain/models/home_item.dart';

abstract class HomeRepository {
  Future<List<HomeItem>> items();
}
