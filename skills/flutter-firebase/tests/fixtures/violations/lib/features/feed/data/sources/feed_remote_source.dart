import 'package:cloud_firestore/cloud_firestore.dart';

class FeedRemoteSource {
  FeedRemoteSource(this._db);

  final FirebaseFirestore _db;

  Stream<QuerySnapshot<Map<String, dynamic>>> watchPosts() {
    return _db.collection('posts').orderBy('createdAt', descending: true).snapshots();
  }

  Future<void> createProfile(String uid, String name) {
    return _db.collection('users').doc(uid).set({
      'name': name,
      'role': 'admin',
    });
  }
}
