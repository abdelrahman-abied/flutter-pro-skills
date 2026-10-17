/// App route locations with a query (FP cause: NET-010 on non-HTTP strings and id-like values).
class ScreenPaths {
  static String gallery(String itemId) => '/gallery${itemId.isEmpty ? '' : '?item=$itemId'}';
  static String search(String tab) => '/search?tab=$tab';
}
