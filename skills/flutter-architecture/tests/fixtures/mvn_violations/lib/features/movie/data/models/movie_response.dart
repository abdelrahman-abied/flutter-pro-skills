class MovieResponse {
  const MovieResponse({required this.id, required this.title});
  final String id;
  final String title;

  factory MovieResponse.fromJson(Map<String, dynamic> json) =>
      MovieResponse(id: json['id'] as String, title: json['title'] as String);
}
