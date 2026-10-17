const _delay = Duration(milliseconds: 300);
Future<void> wait() => Future.delayed(_delay);

// bloclibrary flutter_dynamic_form: a fake repository that cannot fail.
class NewCarRepository {
  Future<List<String>> fetchBrands() async {
    await wait();
    return ['Chevy', 'Toyota', 'Honda'];
  }
}
