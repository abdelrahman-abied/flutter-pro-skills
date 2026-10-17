import 'src/stub.dart'
    if (dart.library.io) '../data/sources/net_source.dart'
    if (dart.library.html) 'src/stub.dart' as impl show NetSource hide Placeholder2;
import "package:parsing_edge_cases/data/sources/net_source.dart" deferred as lazy;
import 'package:flutter/widgets.dart';
/* import 'package:dio/dio.dart';
   /* nested */ import 'package:dio/dio.dart'; */
// import 'package:dio/dio.dart';

const s = "import 'package:dio/dio.dart'; jsonDecode(x) // not a comment";
final r = r'C:\path\' 'jsonDecode(';
final t = '''
import 'package:dio/dio.dart';
jsonDecode(
''';

class HomeView extends StatelessWidget {
  const HomeView({super.key, this.source});
  final impl.NetSource? source;

  @override
  Widget build(BuildContext context) {
    final a = true;
    final url = 'http://x.com/${a ? 'b' : "c/${"d"}"}'; // jsonDecode( in a comment
    final lazySource = lazy.NetSource;
    return Text('$url $s $r $t $lazySource');
  }
}
