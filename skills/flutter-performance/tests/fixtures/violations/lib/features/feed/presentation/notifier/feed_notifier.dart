import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/feed_state.dart';

part 'feed_notifier.g.dart';

@riverpod
class FeedNotifier extends _$FeedNotifier {
  @override
  FeedState build() => const FeedState();
}

@riverpod
class GalleryNotifier extends _$GalleryNotifier {
  @override
  FeedState build() => const FeedState();
}

@riverpod
class BannerNotifier extends _$BannerNotifier {
  @override
  FeedState build() => const FeedState();
}
