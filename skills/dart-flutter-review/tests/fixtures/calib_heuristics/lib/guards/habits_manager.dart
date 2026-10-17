// K1 H1: get* with parameters / async is a repository convention, not a getter candidate.
// K1 H5: a file named after its only class is not a grab-bag file.
import 'package:flutter/foundation.dart';

class HabitsManager extends ChangeNotifier {
  Future<List<String>> getHabitsByCategory(String category) async => [];
  Future<String> getTitle() async => '';
  String getLabel(int index) => '$index';
}
