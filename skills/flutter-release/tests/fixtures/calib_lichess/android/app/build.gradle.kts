android {
    defaultConfig {
        applicationId = "org.sample.board"
    }
    signingConfigs {
        create("release") {
            storeFile = file("upload-keystore.jks")
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            applicationIdSuffix = ".debug"
        }
    }
}
