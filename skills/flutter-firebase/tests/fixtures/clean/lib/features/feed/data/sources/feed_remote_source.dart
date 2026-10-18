import 'package:cloud_firestore/cloud_firestore.dart';

class FeedRemoteSource {
  FeedRemoteSource(this._db);

  final FirebaseFirestore _db;

  CollectionReference<Map<String, dynamic>> get _posts => _db.collection('posts');

  Stream<QuerySnapshot<Map<String, dynamic>>> watchPage(DocumentSnapshot? after) {
    var query = _posts.orderBy('createdAt', descending: true).limit(20);
    if (after != null) query = query.startAfterDocument(after);
    return query.snapshots();
  }

  Future<DocumentSnapshot<Map<String, dynamic>>> post(String id) => _db.collection('posts').doc(id).get();

  Future<int?> countPosts() async => (await _db.collection('posts').count().get()).count;

  Future<DocumentSnapshot<Map<String, dynamic>>> createAndRead(String text) async {
    final ref = await _db.collection('posts').add({'text': text});
    return ref.get();
  }

  Query<Map<String, dynamic>> pagedQuery() => _db.collection('posts').orderBy('createdAt');

  Future<void> saveProfile(String uid, String name) {
    return _db.collection('users').doc(uid).set({'name': name, 'displayRole': 'reader'}, SetOptions(merge: true));
  }

  Future<void> bumpLikes(String id) {
    return _db.runTransaction((transaction) async {
      final ref = _db.collection('posts').doc(id);
      final snap = await transaction.get(ref);
      transaction.update(ref, {'likes': (snap.data()?['likes'] as int? ?? 0) + 1});
    });
  }
}
