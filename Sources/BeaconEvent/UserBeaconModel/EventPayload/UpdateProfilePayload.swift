//
//  UpdateProfilePayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct UpdateProfilePayload: BeaconEventPayloadProtocol {
    
    var previousName: String?
    var newName: String?
    
    var previousNumber: String?
    var newNumber: String?
    
    var previousEmail: String?
    var newEmail: String?
    
    var verified: String?
    
    var additionalData: [String: Any]?
    
    public init(previousName: String? = nil, newName: String? = nil, previousNumber: String? = nil, newNumber: String? = nil, previousEmail: String? = nil, newEmail: String? = nil, verified: Bool? = false, additionalData: [String : String]? = nil) {
        
        self.previousName = previousName
        self.newName = newName
        
        self.previousNumber = previousNumber
        self.newNumber = newNumber
        
        self.previousEmail = previousEmail
        self.newEmail = newEmail
        
        self.verified = Utility.sharedInstance.getBoolType(verified ?? false)
        
        self.additionalData = additionalData
    }
}
