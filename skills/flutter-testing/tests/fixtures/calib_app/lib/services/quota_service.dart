enum QuotaError { empty, tooLong }

abstract class Checker<E> {
  E? check(String value);
}

class QuotaService extends Checker<QuotaError> {
  @override
  QuotaError? check(String value) {
    if (value.isEmpty) return QuotaError.empty;
    return value.length > 8 ? QuotaError.tooLong : null;
  }
}
