abstract class HaboSyncException implements Exception {
  const HaboSyncException(this.code, this.message);
  final String code;
  final String message;

  @override
  String toString() => '$runtimeType($code): $message';
}

class SyncException extends HaboSyncException {
  const SyncException(super.code, super.message);
  factory SyncException.pushFailed() => const SyncException('SYNC_PUSH_FAILED', 'Push failed');
}
