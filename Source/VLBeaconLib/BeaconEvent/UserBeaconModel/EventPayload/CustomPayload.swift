//
//  CustomPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct CustomPayload: BeaconEventPayloadProtocol{
    
    var additionalData: [String: Any]?
    
    public init(additionalData: [String : String]? = nil) {
        self.additionalData = additionalData
    }
}
