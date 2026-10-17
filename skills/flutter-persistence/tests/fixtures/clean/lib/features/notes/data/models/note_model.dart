import 'package:hive/hive.dart';

part 'note_model.g.dart';

const kNoteTypeId = 1;

@HiveType(typeId: kNoteTypeId)
class NoteModel {
  NoteModel(this.id, this.title, this.body);

  @HiveField(0)
  final int id;

  @HiveField(1)
  final String title;

  @HiveField(3)
  final String body;
}

@HiveType(typeId: 2)
class TagModel {
  TagModel(this.name);

  @HiveField(0)
  final String name;
}

class LegacyAdapter extends TypeAdapter<String> {
  @override
  final int typeId = 3;

  @override
  String read(BinaryReader reader) => reader.readString();

  @override
  void write(BinaryWriter writer, String obj) => writer.writeString(obj);
}
