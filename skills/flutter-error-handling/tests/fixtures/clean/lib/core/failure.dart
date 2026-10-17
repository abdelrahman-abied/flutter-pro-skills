/// Domain failures: what the app can do something about, in words a user can read.
sealed class Failure implements Exception {
  const Failure(this.userMessage);
  final String userMessage;
}

final class NetworkFailure extends Failure {
  const NetworkFailure() : super('You appear to be offline.');
}

final class ServerFailure extends Failure {
  const ServerFailure(this.statusCode) : super('The server had a problem. Try again later.');
  final int? statusCode;
}

final class ParseFailure extends Failure {
  const ParseFailure() : super('We received data we could not read.');
}
