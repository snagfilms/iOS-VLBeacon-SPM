//
//  SubscriptionEventDataPayload.swift
//  VLBeaconLib
//
//  Created by vishalthakur@viewlift.com on 19/02/26.
//

import Foundation


public struct SubscriptionEventDataPayload: BeaconEventPayloadProtocol {
    
    var trayId: String?
    var trayNumber: String?
    var itemNo: String?
    var vid: String?
    var isVertical: String?
    
    var pgName: String?
    var pgId: String?
    
    var modType: String?
    var modID: String?
    
    var buttonName: String?
    
    var additionalData: [String: Any]?
    
    public init(
        trayId: String? = nil,
        trayNumber: Int? = nil,
        itemNo: Int? = nil,
        vid: String? = nil,
        isVertical: Bool? = nil,
        pgName: String? = nil,
        pgId: String? = nil,
        modType: String? = nil,
        modID: String? = nil,
        buttonName: String? = nil,
        additionalData: [String: Any]? = nil
    ) {
        
        self.trayId = trayId
        self.trayNumber = trayNumber != nil ? String(trayNumber!) : nil
        self.itemNo = itemNo != nil ? String(itemNo!) : nil
        self.vid = vid
        
        self.isVertical = Utility.sharedInstance.getBoolType(isVertical ?? false)
        
        self.pgName = pgName
        self.pgId = pgId
        
        self.modType = modType
        self.modID = modID
        
        self.buttonName = buttonName
        self.additionalData = additionalData
    }
}

public struct PlanEventDataPayload: BeaconEventPayloadProtocol {
    
    var planId: String?
    var planName: String?
    var planDesc: String?
    var planType: String?
    
    var pgName: String?
    var pgId: String?
    
    var modType: String?
    var modID: String?
    
    var paymentMethod: String?
    
    var additionalData: [String: Any]?
    
    public init(
        planId: String? = nil,
        planName: String? = nil,
        planDesc: String? = nil,
        planType: String? = nil,
        pgName: String? = nil,
        pgId: String? = nil,
        modType: String? = nil,
        modID: String? = nil,
        paymentMethod: String? = nil,
        additionalData: [String: Any]? = nil
    ) {
        
        self.planId = planId
        self.planName = planName
        self.planDesc = planDesc
        self.planType = planType
        
        self.pgName = pgName
        self.pgId = pgId
        
        self.modType = modType
        self.modID = modID
        
        self.paymentMethod = paymentMethod
        
        self.additionalData = additionalData
    }
}
