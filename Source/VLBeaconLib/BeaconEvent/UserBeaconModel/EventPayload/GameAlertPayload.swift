//
//  GameAlertPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct GameAlertPayload: BeaconEventPayloadProtocol{
    
    var isAlertOn: String?
    var additionalData: [String: Any]?
    
    public init(isAlertOn: Bool? = false, additionalData: [String : String]? = nil) {
        
        self.isAlertOn = Utility.sharedInstance.getBoolType(isAlertOn ?? false)
        self.additionalData = additionalData
    }
}
