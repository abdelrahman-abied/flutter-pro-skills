import 'package:http/http.dart' as http;

import '../../utils/result.dart';

class HabitException implements Exception {
  const HabitException(this.message);
  final String message;
}

class Habit {
  Habit(this.id);
  final int id;
}

abstract class HabitRepository {
  Future<Habit?> findById(int id);
  Future<Habit?> fetchRemote(int id);
  Attempt<int> count();
  Future<Result<List<Habit>>> all();
  Future<List<Habit>> plainAll();
}

class HabitRepositoryImpl implements HabitRepository {
  HabitRepositoryImpl(this._load, this._client);
  final Future<List<Habit>> Function() _load;
  final http.Client _client;

  // K1-E2: a collection lookup, no I/O in the try: not ERR-007 (low ERR-001, use firstWhereOrNull).
  @override
  Future<Habit?> findById(int id) async {
    final all = await _load();
    try {
      return all.firstWhere((h) => h.id == id);
    } catch (e) {
      return null;
    }
  }

  // Still ERR-007: the try does network I/O and turns its failure into null.
  @override
  Future<Habit?> fetchRemote(int id) async {
    try {
      final res = await _client.get(Uri.parse('https://example.com/$id'));
      return Habit(res.statusCode);
    } catch (e) {
      return null;
    }
  }

  // ERR-009 through a typedef: Attempt<int> is Future<Result<int>>, and the method still throws.
  @override
  Attempt<int> count() async {
    final list = await _load();
    if (list.isEmpty) throw HabitException('empty');
    return Ok(list.length);
  }

  @override
  Future<Result<List<Habit>>> all() async {
    try {
      return Ok(await _load());
    } on Exception catch (e) {
      return Error(e);
    }
  }

  @override
  Future<List<Habit>> plainAll() => _load();
}
