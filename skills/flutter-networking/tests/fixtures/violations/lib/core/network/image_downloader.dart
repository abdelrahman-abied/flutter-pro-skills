import 'dart:io';

class ImageDownloader {
  Future<List<int>> download(Uri uri) async {
    final client = HttpClient();
    final request = await client.getUrl(uri);
    final response = await request.close();
    final bytes = <int>[];
    await for (final chunk in response) {
      bytes.addAll(chunk);
    }
    return bytes;
  }
}
