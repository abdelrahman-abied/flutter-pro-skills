import 'package:flutter/widgets.dart';

class Cart {}

class Gift {}

class HomeView extends StatelessWidget {
  const HomeView({super.key});
  @override
  Widget build(BuildContext context) => const SizedBox();
}

class ProductsView extends StatelessWidget {
  const ProductsView({super.key});
  @override
  Widget build(BuildContext context) => const SizedBox();
}

class ProductView extends StatelessWidget {
  const ProductView({super.key, required this.id});
  final int id;
  @override
  Widget build(BuildContext context) => const SizedBox();
}

class SearchView extends StatelessWidget {
  const SearchView({super.key, required this.query});
  final String query;
  @override
  Widget build(BuildContext context) => const SizedBox();
}

class GiftView extends StatelessWidget {
  const GiftView({super.key, this.gift});
  final Gift? gift;
  @override
  Widget build(BuildContext context) => const SizedBox();
}

class CheckoutView extends StatelessWidget {
  const CheckoutView({super.key, required this.cart});
  final Cart cart;
  @override
  Widget build(BuildContext context) => const SizedBox();
}

class LoginPlaceholder extends StatelessWidget {
  const LoginPlaceholder({super.key});
  @override
  Widget build(BuildContext context) => const SizedBox();
}
