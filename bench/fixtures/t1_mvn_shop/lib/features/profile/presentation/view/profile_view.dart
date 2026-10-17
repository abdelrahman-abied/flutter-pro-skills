import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../../../l10n/gen/app_localizations.dart';
import '../notifier/profile_notifier.dart';
import '../state/profile_state.dart';
import '../widget/edit_name_field.dart';

class ProfileView extends ConsumerWidget {
  const ProfileView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final state = ref.watch(profileProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.profileTitle)),
      body: switch (state) {
        ProfileLoading() => const Center(child: CircularProgressIndicator()),
        ProfileError() => Center(
            child: TextButton(
              onPressed: ref.read(profileProvider.notifier).load,
              child: Text(l10n.retry),
            ),
          ),
        ProfileSuccess(:final profile) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(profile.email),
              const SizedBox(height: 16),
              const Text('Edit profile'),
              EditNameField(
                initialName: profile.name,
                onSave: ref.read(profileProvider.notifier).updateName,
              ),
              const SizedBox(height: 32),
              FutureBuilder<PackageInfo>(
                future: PackageInfo.fromPlatform(),
                builder: (context, snapshot) => Text(
                  l10n.versionLabel(snapshot.data?.version ?? ''),
                ),
              ),
            ],
          ),
      },
    );
  }
}
