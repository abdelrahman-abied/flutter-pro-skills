import 'package:hive/hive.dart';

part 'note_model.g.dart';

@HiveType(typeId: 1)
class NoteModel {
  NoteModel(this.id, this.title, this.body);

  @HiveField(0)
  final int id;

  @HiveField(1)
  final String title;

  @HiveField(1)
  final String body;

  Map<String, Object?> toMap() => {'id': id, 'title': title, 'body': body};
}

@HiveType(typeId: 1)
class TagModel {
  TagModel(this.name);

  @HiveField(0)
  final String name;
}
