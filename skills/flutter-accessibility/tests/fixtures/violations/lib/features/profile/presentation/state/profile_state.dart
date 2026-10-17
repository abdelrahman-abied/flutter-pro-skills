sealed class ProfileState {
  const ProfileState();
}

final class ProfileIdle extends ProfileState {
  const ProfileIdle();
}

final class ProfileCodeSent extends ProfileState {
  const ProfileCodeSent();
}
