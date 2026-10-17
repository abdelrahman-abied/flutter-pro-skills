android {
    namespace = "dev.flutter.demo_gallery"
    defaultConfig {
        applicationId = "dev.flutter.demo_gallery"
        targetSdk = 33
    }
    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}
