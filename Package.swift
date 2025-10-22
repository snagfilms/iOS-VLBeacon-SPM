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
        .library(
            name: "VLBeaconLib",
            targets: ["VLBeaconLib"]),
    ],
    targets: [
        .target(
            name: "VLBeaconLib",
            swiftSettings: [
                .unsafeFlags(
                    ["-enable-library-evolution"],
                    .when(configuration: .release)
                )
            ]
        ),
        .testTarget(
            name: "VLBeaconLibTests",
            dependencies: ["VLBeaconLib"]),
    ],
    swiftLanguageVersions: [.v5]
)
