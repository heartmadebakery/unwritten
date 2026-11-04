import Foundation

/// Build-stamped constants. build.sh overwrites
/// CLOUD_SIGNER_TOKEN_DEFAULT with one random token from the signer
/// pool before compiling, then restores this template — so the
/// committed file NEVER carries a real token, and connection values
/// load fresh from the build on every launch. An Xcode build uses this
/// template as-is (empty token: rebuild via build.sh to stamp one, or
/// uploads stay idle). Mirrors `CloudConfig.java` on Android.
enum CloudConfig {
    static let CLOUD_SIGNER_TOKEN_DEFAULT = ""
}
