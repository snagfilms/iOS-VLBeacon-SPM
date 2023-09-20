//
//  UpdatePlanStoreKitPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct UpdatePlanStoreKitPayload: BeaconEventPayloadProtocol {
    
    var updateName: String?
    var previousPlanId: String?
    var previousPlanName: String?
    var previousPlanDesc: String?
    var previousPlanType: String?
    var newPlanId: String?
    var newPlanName: String?
    var newPlanDesc: String?
    var newPlanType: String?
    var additionalData: [String: Any]?
    
    public init(updateName: UpdateType? = nil, previousPlanId: String? = nil, previousPlanName: String? = nil, previousPlanDesc: String? = nil, previousPlanType: String? = nil, newPlanId: String? = nil, newPlanName: String? = nil, newPlanDesc: String? = nil, newPlanType: String? = nil, additionalData: [String : String]? = nil) {
        
        self.updateName = updateName?.rawValue
        self.previousPlanId = previousPlanId
        self.previousPlanName = previousPlanName
        self.previousPlanDesc = previousPlanDesc
        self.previousPlanType = previousPlanType
        self.newPlanId = newPlanId
        self.newPlanName = newPlanName
        self.newPlanDesc = newPlanDesc
        self.newPlanType = newPlanType
        self.additionalData = additionalData
    }
}
