class PickException implements Exception {
  const PickException(this.message);
  final String message;
}

extension Pick on Object? {
  int asIntOrThrow() {
    final v = this;
    if (v is int) return v;
    throw const PickException("can't be casted to int");
  }

  // K3-E1: `xOrNull` returning a nullable type: null on failure is the contract (info).
  int? asIntOrNull() {
    if (this == null) return null;
    try {
      return asIntOrThrow();
    } catch (_) {
      return null;
    }
  }

  // Still high: same body, but nothing in the name or type says "null on failure".
  int? asInt() {
    try {
      return asIntOrThrow();
    } catch (_) {
      return null;
    }
  }
}
