// swift-tools-version: 5.8.0
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "VLBeaconPlayer",
    platforms: [
        .iOS(.v14),
        .tvOS(.v13)
    ],
    products: [
        .library(
            name: "VLBeaconPlayer",
            targets: ["VLBeaconPlayer"]),
    ],
    targets: [
        .target(
            name: "VLBeaconPlayer")
    ],
    swiftLanguageVersions: [.v5]
)
