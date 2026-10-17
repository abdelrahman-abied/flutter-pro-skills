import 'package:flutter/foundation.dart';

class CartModel extends ChangeNotifier {
  final List<int> _ids = [];

  int get count => _ids.length;

  void add(int id) {
    if (_ids.contains(id)) return;
    _ids.add(id);
    notifyListeners();
  }
}
