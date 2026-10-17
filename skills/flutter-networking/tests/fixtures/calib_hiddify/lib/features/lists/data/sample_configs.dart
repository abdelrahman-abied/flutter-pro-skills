import '../../../core/http/proxy_aware_client.dart';

class SampleConfigs {
  SampleConfigs(this._client);

  final ProxyAwareClient _client;

  Future<String?> load() async =>
      (await _client.get('https://raw.githubusercontent.com/demo-org/samples/main/configs.txt')).data;
}
