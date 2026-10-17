import '../../../domain/models/home_item.dart';
import '../../services/api/api_client.dart';
import '../../services/api/model/home_response.dart';
import '../cart/cart_repository.dart';
import 'home_repository.dart';

class HomeRepositoryRemote implements HomeRepository {
  HomeRepositoryRemote(this._api, this._cart);
  final ApiClient _api;
  final CartRepository _cart;

  @override
  Future<List<HomeItem>> items() async =>
      [for (final t in (await raw()).items) HomeItem('$t ${await _cart.count()}')];

  Future<HomeResponse> raw() => _api.fetchHome();
}
