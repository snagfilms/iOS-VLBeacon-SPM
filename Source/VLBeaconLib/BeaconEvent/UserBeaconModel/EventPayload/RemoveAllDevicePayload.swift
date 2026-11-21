//
//  RemoveAllDevicePayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 29/06/23.
//

import Foundation

public struct RemoveAllDevicePayload: BeaconEventPayloadProtocol{
    
    var devices: [RemoveDevicePayload]?
    var additionalData: [String: Any]?
    
    public init(deviceList: [RemoveDevicePayload]? = nil , additionalData: [String : String]? = nil) {
        self.devices = deviceList
        self.additionalData = additionalData
    }
}
