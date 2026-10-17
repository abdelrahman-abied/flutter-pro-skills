import 'dart:async';

import 'package:bloc/bloc.dart';

import '../../../repositories/todos_repository.dart';
import 'stats_state.dart';

class StatsCubit extends Cubit<StatsState> {
  StatsCubit(TodosRepository repository) : super(const StatsState()) {
    _sub = repository.watchTodos().listen((t) => emit(StatsState(total: t.length)));
  }

  late final StreamSubscription<List<String>> _sub;

  @override
  Future<void> close() {
    _sub.cancel();
    return super.close();
  }
}
