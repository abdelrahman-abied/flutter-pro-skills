import 'package:web_socket_channel/web_socket_channel.dart';

class ChatSocketSource {
  WebSocketChannel? _channel;

  Stream<dynamic> messages(Uri uri) {
    _channel = WebSocketChannel.connect(uri);
    return _channel!.stream;
  }

  void send(String text) => _channel?.sink.add(text);
}
