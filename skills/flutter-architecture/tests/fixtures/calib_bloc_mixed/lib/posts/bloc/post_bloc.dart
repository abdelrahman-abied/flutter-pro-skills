// true positive kept: the bloc does HTTP itself -> ARCH-007
import 'package:bloc/bloc.dart';
import 'package:http/http.dart' as http;

class PostBloc extends Cubit<int> {
  PostBloc({required http.Client httpClient}) : _httpClient = httpClient, super(0);
  final http.Client _httpClient;
  Future<void> load() async {
    final r = await _httpClient.get(Uri.parse('https://x'));
    emit(r.statusCode);
  }
}
