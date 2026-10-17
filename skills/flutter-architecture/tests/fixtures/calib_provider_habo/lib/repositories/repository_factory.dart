// K1 A3: a factory that only constructs repositories is DI wiring (role di), not ARCH-011
import 'habit_repository.dart';
import 'sqlite_habit_repository.dart';

class RepositoryFactory {
  final HabitRepository habitRepository = SQLiteHabitRepository();
}
