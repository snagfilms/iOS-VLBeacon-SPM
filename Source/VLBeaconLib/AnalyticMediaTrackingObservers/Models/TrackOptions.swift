//
//  TrackOptions.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//

import Foundation

/// Options for specifying what data to include in tracking events
public struct TrackOptions: OptionSet {
    public let rawValue: Int
    
    public init(rawValue: Int) {
        self.rawValue = rawValue
    }
    
    /// Include content information
    public static let content = TrackOptions(rawValue: 1 << 0)
    
    /// Include ads information
    public static let ads = TrackOptions(rawValue: 1 << 1)
    
    /// Include TV provider information
    public static let tvProvider = TrackOptions(rawValue: 1 << 2)
    
    /// Include player information
    public static let player = TrackOptions(rawValue: 1 << 3)
    
    /// Include all available information
    public static let all: TrackOptions = [.content, .ads, .tvProvider, .player]
    
    /// No tracking options
    public static let none: TrackOptions = []
}
