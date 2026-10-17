class GameService {
  bool isOver(List<String> moves) => moves.isNotEmpty && moves.last == '#';
}
