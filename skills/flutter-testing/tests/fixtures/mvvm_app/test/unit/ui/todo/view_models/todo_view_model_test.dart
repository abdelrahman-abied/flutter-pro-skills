import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mvvm_app/data/repositories/todo_repository.dart';
import 'package:mvvm_app/domain/models/todo.dart';
import 'package:mvvm_app/ui/todo/view_models/todo_view_model.dart';

// Smell: generating a mock of the view model inside the view model's own test.
@GenerateMocks([TodoViewModel])
class FakeTodoRepository implements TodoRepository {
  @override
  Future<List<Todo>> fetchTodos() async => const [Todo(id: 1, title: 'Write tests')];
}

void main() {
  test('load fills todos from the repository', () async {
    final viewModel = TodoViewModel(todoRepository: FakeTodoRepository());
    await viewModel.load();
    expect(viewModel.todos.single.title, 'Write tests');
  });
}
