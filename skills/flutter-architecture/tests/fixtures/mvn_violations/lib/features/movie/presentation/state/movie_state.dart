class MovieState {
  MovieState({this.page = 0});

  int page; // ARCH-106
  bool showErrorDialog = false; // ARCH-106 + ARCH-111
  final List<String> titles = const [];
  // Persistent UI toggles are legitimate state, not one-time events (no ARCH-111):
  final bool showPassword = false;
  final bool showArchived = false;
  final bool showDetails = true;
  final bool isExpanded = false;
  final bool openNow = false;
}
