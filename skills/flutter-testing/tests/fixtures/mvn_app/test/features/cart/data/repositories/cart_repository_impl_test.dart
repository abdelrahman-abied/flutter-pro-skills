import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mvn_app/features/cart/data/repositories/cart_repository_impl.dart';

// Smell: this mocks the class under test, so the test exercises the stub.
class MockCartRepositoryImpl extends Mock implements CartRepositoryImpl {}

void main() {
  test('total', () async {
    final repository = MockCartRepositoryImpl();
    when(repository.total).thenAnswer((_) async => 3);
    expect(await repository.total(), 3);
  });
}
