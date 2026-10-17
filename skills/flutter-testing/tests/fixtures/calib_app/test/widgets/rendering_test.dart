import 'package:calib_app/widgets/board.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('board renders', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Board(size: 8)));
    expect(find.byType(Board), findsOneWidget);
  });
}
