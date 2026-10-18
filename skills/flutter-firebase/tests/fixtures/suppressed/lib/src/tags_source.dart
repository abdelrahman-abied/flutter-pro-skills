// fire-ignore-file: FIRE-007 the tags collection is a fixed list of 12 documents
import 'package:cloud_firestore/cloud_firestore.dart';

class TagsSource {
  TagsSource(this._db);

  final FirebaseFirestore _db;

  Future<QuerySnapshot<Map<String, dynamic>>> all() => _db.collection('tags').get();

  Stream<QuerySnapshot<Map<String, dynamic>>> watch() => _db.collection('tags').snapshots();
}
