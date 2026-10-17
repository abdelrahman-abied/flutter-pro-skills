// K3 A5: I/O in a co-located provider is logic; a transport exception type in the widget is low
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';

final characters = FutureProvider<int>((ref) async {
  final token = CancelToken();
  final r = await Dio().get<int>('https://x', cancelToken: token);
  return r.data ?? 0;
});

class CharactersScreen extends ConsumerWidget {
  const CharactersScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => ref.watch(characters).when(
        data: (n) => Text('$n'),
        loading: () => const SizedBox(),
        error: (e, _) => Text(e is DioException ? 'net' : 'err'),
      );
}
