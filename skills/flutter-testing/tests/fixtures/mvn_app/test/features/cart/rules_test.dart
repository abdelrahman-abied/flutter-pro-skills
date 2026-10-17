import 'package:flutter_test/flutter_test.dart';
import 'package:mvn_app/features/cart/domain/usecases/cart_rules.dart';

void main() {
  test('members get 10% off', () {
    expect(discountFor(200, member: true), 20);
    expect(discountFor(200), 0);
  });
}
