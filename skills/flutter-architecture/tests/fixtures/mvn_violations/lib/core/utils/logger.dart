int logLevel = 0; // ARCH-105: top-level mutable

class Log {
  static bool verbose = false; // ARCH-105: static mutable
  static const tag = 'app';

  static void d(String m) {
    if (verbose && logLevel > 0) print('$tag $m');
  }
}
