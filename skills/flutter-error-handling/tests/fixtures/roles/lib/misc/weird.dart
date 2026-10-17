// An unknown role must not crash the checker; content rules still run.
class Weird {
  void go() => throw 'weird';
}
