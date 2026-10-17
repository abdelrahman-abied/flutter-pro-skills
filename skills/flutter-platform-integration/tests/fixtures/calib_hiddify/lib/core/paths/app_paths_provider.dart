import 'package:flutter/services.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'app_paths_provider.g.dart';

@Riverpod(keepAlive: true)
class AppPaths extends _$AppPaths {
  final _channel = const MethodChannel('app.example/host');

  @override
  Future<String> build() async {
    final base = await _channel.invokeMethod<String>('basePath');
    return base ?? '.';
  }
}
