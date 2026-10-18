import 'package:adapt_clean/features/inbox/presentation/view/inbox_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void setTabletSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1600, 2560);
  tester.view.devicePixelRatio = 2;
}

void main() {
  testWidgets('two panes when expanded', (tester) async {
    tester.view.physicalSize = const Size(2880, 1800);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: InboxView()));
    expect(find.byType(Row), findsWidgets);
  });

  testWidgets('tablet helper is reset by the caller', (tester) async {
    setTabletSize(tester);
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: InboxView()));
  });
}
