/// Pure domain rule: top-level function with named parameters.
int discountFor(int total, {bool member = false}) {
  if (total <= 0) return 0;
  return member ? total ~/ 10 : 0;
}
