import 'package:calib_app/habits/habits_manager.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('add', () {
    final m = HabitsManager()..add('Run');
    expect(m.habits, ['Run']);
  });
}
