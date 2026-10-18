class ChatSocket {
  final List<Map<String, Object>> sent = [];

  void send(String text) {
    final message = {'role': 'user', 'content': text};
    sent.add(message);
    final copy = Map<String, Object>.from(message);
    copy.update('role', (_) => 'assistant');
  }
}
