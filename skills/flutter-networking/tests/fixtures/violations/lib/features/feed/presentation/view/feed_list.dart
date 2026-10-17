import 'package:flutter/material.dart';

import '../bloc/feed_bloc.dart';

class FeedList extends StatefulWidget {
  const FeedList({required this.bloc, super.key});

  final FeedBloc bloc;

  @override
  State<FeedList> createState() => _FeedListState();
}

class _FeedListState extends State<FeedList> {
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    if (_scroll.offset >= _scroll.position.maxScrollExtent * 0.9) {
      widget.bloc.add(FeedNextPageRequested());
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(controller: _scroll);
}
