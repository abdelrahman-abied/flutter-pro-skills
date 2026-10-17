class Destination {
  const Destination({required this.name, required this.imageUrl});

  final String name;
  final String imageUrl;
}

/// Bundled sample data with image links (FP cause: NET-008 on image URLs).
class LocalDataService {
  List<Destination> destinations() => const [
        Destination(name: 'Coast', imageUrl: 'https://img-cdn-demo.io/travel/coast.jpg'),
      ];
}
