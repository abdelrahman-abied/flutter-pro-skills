/// Masks a secret for logs: keeps a short prefix and the length.
String redact(String? value) {
  if (value == null || value.isEmpty) return '<empty>';
  final keep = value.length < 16 ? 1 : 4;
  return '${value.substring(0, keep)}…(${value.length} chars)';
}
