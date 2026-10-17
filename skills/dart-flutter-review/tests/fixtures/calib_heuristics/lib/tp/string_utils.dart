// True positive: a utils file holding unrelated declarations; `dynamic` in a public API.
String capitalize(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

int wordCount(String s) => s.split(' ').length;

dynamic decode(dynamic raw) => raw;
