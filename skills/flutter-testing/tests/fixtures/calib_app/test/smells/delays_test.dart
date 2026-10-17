import 'package:flutter_test/flutter_test.dart';

void main() {
  test('event-loop flushes are fine', () async {
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(.zero);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(microseconds: 500));
    await Future<void>.delayed(const Duration(milliseconds: 0));
    expect(1, 1);
  });

  test('a real wait still fires', () async {
    await Future<void>.delayed(const Duration(milliseconds: 2));
    expect(1, 1);
  });
}
