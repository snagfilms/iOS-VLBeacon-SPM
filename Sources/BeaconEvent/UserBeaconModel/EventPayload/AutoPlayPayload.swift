//
//  AutoPlayPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct AutoPlayPayload: BeaconEventPayloadProtocol{
    
    var isAutoPlayOn: String?
    var additionalData: [String: Any]?
    
    public init(isAutoPlayOn: Bool? = false, additionalData: [String : String]? = nil) {
        
        self.isAutoPlayOn = Utility.sharedInstance.getBoolType(isAutoPlayOn ?? false)
        self.additionalData = additionalData
    }
}
