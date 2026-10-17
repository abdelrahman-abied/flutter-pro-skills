// err-ignore-file: ERR-005 legacy API contract: callers match on these strings

void a(int n) {
  if (n < 0) throw 'negative';
}

void b(int n) {
  if (n > 9) throw 'too big';
}
