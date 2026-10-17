import 'package:calib_app/main.dart' as app;
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('login page', (tester) async {
    app.main();
    await tester.pump();
    expect(find.text('ENTER'), findsOneWidget);
  });
}
