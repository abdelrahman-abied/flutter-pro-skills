android {
    namespace = "com.flutter.news.demo"
    defaultConfig {
        applicationId = "com.flutter.news.demo"
        targetSdk = flutter.targetSdkVersion
    }
    signingConfigs {
        create("release") {
            val path = System.getenv("ANDROID_KEYSTORE_PATH")
            if (!path.isNullOrBlank()) {
                storeFile = file(path)
            }
        }
    }
    flavorDimensions.add("default")
    productFlavors {
        create("development") {
            applicationIdSuffix = "dev"
        }
        create("production") {
            applicationIdSuffix = ""
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}
