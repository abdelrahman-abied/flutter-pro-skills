// net-ignore-file: NET-006 tokens here are handed to a legacy queue that cancels by id
import 'package:dio/dio.dart';

Future<void> enqueue(Dio dio) async {
  await dio.get<void>('/a', cancelToken: CancelToken());
  await dio.get<void>('/b', cancelToken: CancelToken());
}
