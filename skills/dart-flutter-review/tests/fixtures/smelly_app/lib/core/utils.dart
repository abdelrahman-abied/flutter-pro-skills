// SMELLS: grab-bag-file (file name), k-or-hungarian-prefix, dynamic-in-api,
// get-prefixed-method (zero-argument sync getVersion()).
const kDefaultTimeout = Duration(seconds: 5);

dynamic parse(dynamic raw) => raw;

String getVersion() => '1.0.0';
