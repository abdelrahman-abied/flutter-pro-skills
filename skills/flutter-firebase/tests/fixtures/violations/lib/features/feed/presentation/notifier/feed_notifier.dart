import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'feed_notifier.g.dart';

@riverpod
class FeedNotifier extends _$FeedNotifier {
  @override
  int build() {
    FirebaseFirestore.instance.collection('posts').limit(20).snapshots().listen((snapshot) {
      state = snapshot.size;
    });
    return 0;
  }
}
