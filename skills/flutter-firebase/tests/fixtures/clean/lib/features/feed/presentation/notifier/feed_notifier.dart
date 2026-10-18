import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'feed_notifier.g.dart';

@riverpod
class FeedNotifier extends _$FeedNotifier {
  @override
  int build() {
    final sub = FirebaseFirestore.instance.collection('posts').limit(20).snapshots().listen((snapshot) {
      state = snapshot.size;
    });
    ref.onDispose(sub.cancel);
    return 0;
  }
}

@Riverpod(keepAlive: true)
class SessionNotifier extends _$SessionNotifier {
  @override
  bool build() {
    FirebaseFirestore.instance.collection('sessions').limit(1).snapshots().listen((s) => state = s.size > 0);
    return false;
  }
}
