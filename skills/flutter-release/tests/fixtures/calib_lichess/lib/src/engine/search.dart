import 'package:flutter/foundation.dart';

const double _depthThreshold = kDebugMode ? 12 : 18;
const kUsableDepth = kDebugMode ? 13 : 15;

double threshold() => _depthThreshold;

String get socketHost => kReleaseMode ? 'wss://socket.board.example' : 'ws://localhost:9664';
