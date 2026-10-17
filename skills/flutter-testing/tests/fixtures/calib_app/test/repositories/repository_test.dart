import 'package:calib_app/data/repositories/user_repository_impl.dart';
import 'package:calib_app/data/sources/user_api.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class MockUserRepository extends Mock implements UserRepository {}

class MockUserApi extends Mock implements UserApi {}

void main() {
  late MockUserRepository mockUserRepository;
  late MockUserApi mockApi;

  setUp(() {
    mockUserRepository = MockUserRepository();
    mockApi = MockUserApi();
  });

  test('mock user repository should work', () async {
    when(() => mockUserRepository.name(any())).thenAnswer((_) async => 'Ada');

    final name = await mockUserRepository.name(1);

    expect(name, 'Ada');
    verify(() => mockUserRepository.name(1)).called(1);
  });

  test('impl over a mocked api', () async {
    when(() => mockApi.fetchName(any())).thenAnswer((_) async => 'Ada');
    final repo = UserRepositoryImpl(mockApi);

    expect(await repo.name(1), 'Ada');
    verify(() => mockApi.fetchName(1)).called(1);
  });

  test('stub then call the mock inside expect', () async {
    when(() => mockApi.fetchName(any())).thenAnswer((_) async => 'Bo');
    expect(await mockApi.fetchName(2), 'Bo');
  });
}
