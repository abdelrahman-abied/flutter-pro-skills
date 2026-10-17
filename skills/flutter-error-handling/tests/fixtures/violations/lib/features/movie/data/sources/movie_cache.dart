import 'dart:async';
import 'dart:io';

class MovieCache {
  MovieCache(this._file);

  final File _file;
  StreamSubscription<void>? _sub;

  Future<void> close() async {
    try {
      await _file.delete();
    } on FileSystemException {
      // Best effort: the OS clears temp files.
    }
    try {
      await _sub?.cancel();
    } catch (_) {}
  }
}
