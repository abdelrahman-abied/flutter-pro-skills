abstract class TodosRepository {
  Stream<List<String>> watchTodos();
  Future<void> add(String title);
}
