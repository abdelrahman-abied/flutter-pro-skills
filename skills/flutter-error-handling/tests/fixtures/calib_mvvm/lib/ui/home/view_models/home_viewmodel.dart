import 'package:flutter/foundation.dart';

import '../../../data/repositories/habit_repository.dart';
import '../../../utils/command.dart';
import '../../../utils/result.dart';

typedef Loader = Future<Result<List<Habit>>> Function();

class HomeViewModel extends ChangeNotifier {
  HomeViewModel({required HabitRepository habitRepository, required Loader loader})
      : _habitRepository = habitRepository,
        _loader = loader {
    load = Command0(_habitRepository.all);
  }

  final HabitRepository _habitRepository;
  final Loader _loader;
  late final Command0<List<Habit>> load;
  bool _loading = false;
  bool get loading => _loading;
  Result<List<Habit>>? _last;
  Result<List<Habit>>? get last => _last;

  // Result-typed callee through the repository contract: not ERR-010.
  Future<void> refresh() async {
    _loading = true;
    notifyListeners();
    final r = await _habitRepository.all();
    _loading = false;
    _last = r;
    notifyListeners();
  }

  // Result-typed callee through a typedef'd field: not ERR-010.
  Future<void> reload() async {
    _loading = true;
    notifyListeners();
    final r = await _loader();
    _loading = false;
    _last = r;
    notifyListeners();
  }

  // True positive: the callee throws, nothing resets _loading.
  Future<void> reloadPlain() async {
    _loading = true;
    notifyListeners();
    await _habitRepository.plainAll();
    _loading = false;
    notifyListeners();
  }
}
