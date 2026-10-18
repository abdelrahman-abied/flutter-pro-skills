import 'package:adapt_violations/features/catalog/presentation/view/catalog_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows two panes on a tablet', (tester) async {
    tester.view.physicalSize = const Size(2048, 1536);
    await tester.pumpWidget(const MaterialApp(home: CatalogView()));
    expect(find.byType(Row), findsOneWidget);
  });
}
