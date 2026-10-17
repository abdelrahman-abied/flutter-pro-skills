import 'package:flutter/foundation.dart';

class HabitsManager extends ChangeNotifier {
  final List<String> _habits = [];

  List<String> get habits => List.unmodifiable(_habits);

  void add(String title) {
    if (title.isEmpty) return;
    _habits.add(title);
    notifyListeners();
  }
}
