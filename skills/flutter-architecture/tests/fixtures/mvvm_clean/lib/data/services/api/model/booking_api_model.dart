class BookingApiModel {
  const BookingApiModel({required this.id, required this.destinationRef});
  final int id;
  final String destinationRef;

  factory BookingApiModel.fromJson(Map<String, dynamic> json) =>
      BookingApiModel(id: json['id'] as int, destinationRef: json['destinationRef'] as String);
}
