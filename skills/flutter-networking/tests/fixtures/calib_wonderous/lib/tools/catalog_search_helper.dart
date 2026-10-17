/// Dev tooling that repeats the API base (TP: `_base…` names count; this was a false negative).
const String _baseObjectsEndpoint = 'https://api.museum-demo.org/public/v1/objects';

String objectUri(int id) => '$_baseObjectsEndpoint/$id';
