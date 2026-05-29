// swift-tools-version: 5.8.0
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "VLBeaconLib",
    platforms: [
        .iOS(.v14),
        .tvOS(.v13)
    ],
    products: [
        // Default static library. Do not use type: .dynamic — when ios-analytics-sdk
        // archives provider xcframeworks against dynamic VLBeacon, the linker records
        // @rpath/VLBeaconLib_<hash>_PackageProduct.framework, which does not match the
        // VLBeaconLib.framework the app embeds from SPM and causes dyld crashes.
        .library(
            name: "VLBeaconLib",
            targets: ["VLBeaconLib"]),
    ],
    targets: [
        .target(
            name: "VLBeaconLib"),
        .testTarget(
            name: "VLBeaconLibTests",
            dependencies: ["VLBeaconLib"]),
    ],
    swiftLanguageVersions: [.v5]
)
