//
//  VerifiedProfilePayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct VerifiedProfilePayload: BeaconEventPayloadProtocol {
    
    var mobileNumber: String?
    var email: String?
    var additionalData: [String: Any]?
    
    public init(mobileNumber: String? = nil, email: String? = nil, additionalData: [String : String]? = nil) {
        self.mobileNumber = mobileNumber
        self.email = email
        self.additionalData = additionalData
    }
}
