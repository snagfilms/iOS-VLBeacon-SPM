// The Swift Programming Language
// https://docs.swift.org/swift-book

import Foundation


final public class VLBeaconPlayer {
    private static let sharedInstance = VLBeaconPlayer()
    
    public class func getInstance()-> VLBeaconPlayer {
        return sharedInstance
    }
    
    private init() {
        debugPrint("VLBeaconPlayer init")
    }
    
    
}
