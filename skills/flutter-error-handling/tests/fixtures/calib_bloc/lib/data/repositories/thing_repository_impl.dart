import '../sources/api.dart';

class ServerException implements Exception {}

class Failure {}

typedef _Chooser = Future<String> Function();

// K2 (ResoCoder): the awaits are inside `on ServerException`, so they aren't "unguarded",
// but ClientException/SocketException/FormatException from the source still leak (ERR-004).
class ThingRepositoryImpl {
  ThingRepositoryImpl(this._api, this._online);
  final Api _api;
  final Future<bool> Function() _online;

  Future<Object> fetch() async {
    return await _guard(() => _api.get());
  }

  Future<Object> _guard(_Chooser run) async {
    if (await _online()) {
      try {
        return await run();
      } on ServerException {
        return Failure();
      }
    }
    return Failure();
  }
}
