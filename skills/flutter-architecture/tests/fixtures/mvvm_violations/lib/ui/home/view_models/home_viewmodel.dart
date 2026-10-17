import 'package:flutter/material.dart';

import '../../../data/services/api/api_client.dart';
import '../../cart/view_models/cart_viewmodel.dart';

class HomeViewModel extends ChangeNotifier {
  HomeViewModel(this._api, this._cart);
  final ApiClient _api;
  final CartViewModel _cart;
  Color accent = Colors.blue;

  Future<void> load() async {
    await _api.fetchHome();
    _cart.count++;
    notifyListeners();
  }
}
