import 'db/database.dart';

class DataController {
  DataController._(this._db, this._logDb);

  final Drift _db;
  final DriftLogger _logDb;

  static Future<DataController> init() async {
    final drift = Drift.sqlite(Object(), Object());
    Future<DriftLogger> open() async => DriftLogger.sqlite(Object());
    final logDb = await open();
    return DataController._(drift, logDb);
  }

  Future<int> countLogs() async {
    final fresh = DriftLogger.sqlite(Object());
    final rows = await fresh.customSelect('SELECT COUNT(*) FROM logger_messages').get();
    return rows.length;
  }
}
