import 'package:flutter/material.dart';

import '../../data/models/location.dart';
import '../../data/open_meteo_api_client.dart';

class SearchPage extends StatefulWidget {
  const SearchPage._();

  static Route<String> route() {
    return MaterialPageRoute(builder: (_) => const SearchPage._());
  }

  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final TextEditingController _textController = TextEditingController();
  final OpenMeteoApiClient _apiClient = OpenMeteoApiClient();
  List<Location> _suggestions = const [];

  String get _text => _textController.text;

  Future<void> _onChanged(String query) async {
    if (query.length < 3) return;
    try {
      final results = await _apiClient.locationSearch(query, count: 5);
      if (mounted) setState(() => _suggestions = results);
    } on Exception {
      if (mounted) setState(() => _suggestions = const []);
    }
  }

  @override
  void dispose() {
    _textController.dispose();
    _apiClient.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('City Search')),
      body: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(8),
                  child: TextField(
                    controller: _textController,
                    onChanged: _onChanged,
                    decoration: const InputDecoration(
                      labelText: 'City',
                      hintText: 'Chicago',
                    ),
                  ),
                ),
              ),
              IconButton(
                key: const Key('searchPage_search_iconButton'),
                icon: const Icon(Icons.search, semanticLabel: 'Submit'),
                onPressed: () => Navigator.of(context).pop(_text),
              ),
            ],
          ),
          Expanded(
            child: ListView.builder(
              itemCount: _suggestions.length,
              itemBuilder: (context, i) => ListTile(
                title: Text(_suggestions[i].name),
                onTap: () => Navigator.of(context).pop(_suggestions[i].name),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
