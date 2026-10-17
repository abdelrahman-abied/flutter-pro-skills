import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import '../../../../core/widgets/app_icon_button.dart';
import '../view_model/profile_view_model.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, this.viewModel});

  final ProfileViewModel? viewModel;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _passwordController = TextEditingController();
  bool _editing = false;
  bool _searchFocused = false;

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  // The view announces; the view model only exposes the status.
  void _onStatus(SaveStatus status) {
    if (status == SaveStatus.saved) {
      SemanticsService.announce('Profile saved', Directionality.of(context));
    }
  }

  Widget _closeButton() => IconButton(icon: const Icon(Icons.close), onPressed: () {});

  @override
  Widget build(BuildContext context) {
    final back = IconButton(icon: const Icon(Icons.arrow_back), onPressed: () {});
    return Scaffold(
      appBar: AppBar(
        leading: Semantics(label: 'Back', child: back),
        actions: [
          IconButton(tooltip: 'Share', icon: const Icon(Icons.share), onPressed: () {}),
          IconButton(icon: const Icon(Icons.star, semanticLabel: 'Favourite'), onPressed: () {}),
          Tooltip(message: 'Help', child: IconButton(icon: const Icon(Icons.help), onPressed: () {})),
          Semantics(label: 'Close', child: _closeButton()),
          AppIconButton(icon: Icons.edit, onPressed: () {}, tooltip: 'Edit'),
          const BackButton(),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {},
        icon: const Icon(Icons.add),
        label: const Text('Add'),
      ),
      body: Column(
        children: [
          InkWell(onTap: () {}, child: const Text('Open settings')),
          GestureDetector(onTap: () {}, child: const Icon(Icons.favorite, semanticLabel: 'Like')),
          Semantics(
            button: true,
            label: 'Like',
            child: GestureDetector(onTap: () {}, child: const Icon(Icons.favorite_border)),
          ),
          NavigationBar(destinations: const [
            NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
            NavigationDestination(icon: Icon(Icons.person), label: 'Me'),
          ]),
          Image.asset('assets/divider.png', excludeFromSemantics: true),
          Image.network('https://example.com/a.png', semanticLabel: 'Team photo'),
          ExcludeSemantics(child: Image.asset('assets/flourish.png')),
          ScaledText('Scaled on purpose', scale: MediaQuery.textScalerOf(context).scale(1.2)),
          Text('Readable', textScaler: MediaQuery.textScalerOf(context)),
          SizedBox(
            width: 48,
            height: 48,
            child: IconButton(tooltip: 'Info', icon: const Icon(Icons.info), onPressed: () {}),
          ),
          const SizedBox(height: 20, child: Icon(Icons.circle, size: 12)),
          const SizedBox(height: 56, child: Text('Tall enough')),
          ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 20),
            child: const Text('Grows with the text'),
          ),
          TextField(
            controller: _passwordController,
            obscureText: true,
            decoration: InputDecoration(
              labelText: 'Password',
              suffixIcon: IconButton(tooltip: 'Show password', icon: const Icon(Icons.visibility), onPressed: () {}),
            ),
          ),
          Semantics(label: 'Password', obscured: true, child: const SizedBox()),
          Semantics(value: '${_passwordController.text.length} characters', child: const SizedBox()),
          Semantics(label: _editing ? 'Editing profile' : 'Profile', header: true, child: const Text('Profile')),
          ExcludeSemantics(excluding: !_searchFocused, child: const TextField()),
          Semantics(
            button: true,
            label: 'Next page',
            onTap: () {},
            child: GestureDetector(excludeFromSemantics: true, onTap: () {}, child: const Text('Next')),
          ),
          GestureDetector(excludeFromSemantics: true, onDoubleTap: () {}, child: const Text('Zoom')),
          ExcludeSemantics(child: const Icon(Icons.auto_awesome)),
          _editing ? const TextField(autofocus: true) : const TextField(autofocus: true),
        ],
      ),
    );
  }
}

class SearchBox extends StatelessWidget {
  const SearchBox({super.key});

  @override
  Widget build(BuildContext context) => const TextField(autofocus: true);
}
