import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mvvm_app/data/repositories/todo_repository.dart';
import 'package:mvvm_app/data/services/api_client.dart';

void main() {
  test('drops todos without a title', () async {
    final client = MockClient((_) async => http.Response('[{"id":1,"title":"a"},{"id":2}]', 200));
    final repository = TodoRepositoryRemote(ApiClient(client));
    expect((await repository.fetchTodos()).map((t) => t.id), [1]);
  });
}
