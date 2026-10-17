class HistoryService {
  final List<String> _events = [];

  void track(String name) {
    if (name.isEmpty) return;
    _events.add(name);
  }

  List<String> get events => List.unmodifiable(_events);
}
