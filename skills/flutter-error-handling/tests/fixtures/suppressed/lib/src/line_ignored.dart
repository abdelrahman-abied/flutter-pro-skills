import 'dart:io';

Future<void> removeTemp(File f) async {
  try {
    await f.writeAsString('');
  } catch (_) {} // err-ignore: ERR-001 the file may already be gone
  try {
    await f.writeAsString('x');
  } catch (_) {
    // err-ignore: ERR-001 same reason, comment inside the block
  }
}

void check(int n) {
  if (n < 0) throw 'negative'; // not suppressed: ERR-005 is reported
}
