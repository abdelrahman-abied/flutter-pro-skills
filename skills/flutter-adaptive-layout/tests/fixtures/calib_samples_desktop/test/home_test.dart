import 'package:calib_samples_desktop/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('wide window', (tester) async {
    setWindow(tester, 1200);
    await tester.pumpWidget(const MaterialApp(home: SearchHome()));
  });
}

void setWindow(WidgetTester tester, double width) {
  tester.view.devicePixelRatio = 2;
  tester.view.physicalSize = Size(width * 2, 1600);
}
