import 'package:calib_app/src/model/game_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('over', () => expect(GameService().isOver(['e4', '#']), isTrue));
}
