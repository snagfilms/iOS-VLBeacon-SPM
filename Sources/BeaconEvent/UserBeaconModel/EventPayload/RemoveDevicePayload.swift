//
//  RemoveDevicePayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct RemoveDevicePayload: BeaconEventPayloadProtocol{
    
    var deviceName: String?
    var dateAdded: String?
    var lastWatched: String?
    var additionalData: [String: Any]?
    
    public init(deviceName: String? = nil, dateAdded: String? = nil, lastWatched: String? = nil, additionalData: [String : String]? = nil) {
        self.deviceName = deviceName
        self.dateAdded = dateAdded
        self.lastWatched = lastWatched
        self.additionalData = additionalData
    }
}
