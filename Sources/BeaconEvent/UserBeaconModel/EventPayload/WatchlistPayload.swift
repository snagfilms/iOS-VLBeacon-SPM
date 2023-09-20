//
//  WatchlistPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct WatchlistPayload: BeaconEventPayloadProtocol{
    
    var vid: String?
    var items: [String]?
    var additionalData: [String: Any]?
    
    public init(vid: String? = nil, items: [String]? = nil, additionalData: [String : String]? = nil) {
        self.vid = vid
        self.items = items
        self.additionalData = additionalData
    }
}
