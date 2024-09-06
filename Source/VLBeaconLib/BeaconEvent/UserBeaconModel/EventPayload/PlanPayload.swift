//
//  PlanPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct PlanPayload: BeaconEventPayloadProtocol {
    
    var planId: String?
    var planName: String?
    var planDesc: String?
    var planType: String?
    var location: String?
    var additionalData: [String: Any]?
    var type: [String]?
    var stepsCompleted: [String]?
    var status: [Any]?
    var paymentMethod: String?
    var currencyCode: String?
    var orderTotalAmount: String?
    var transactionId: String?
    
    public init(planId: String? = nil, planName: String? = nil, planDesc: String? = nil, planType: String? = nil, additionalData: [String : String]? = nil, type: [String]? = nil, stepsCompleted: [String]? = nil, location: String? = nil, status: [Any]? = nil, paymentMethod: String? = nil, currencyCode: String? = nil, orderTotalAmount: String? = nil, transactionId: String? = nil) {
        self.planId = planId
        self.planName = planName
        self.planDesc = planDesc
        self.planType = planType
        self.additionalData = additionalData
        self.type = type
        self.stepsCompleted = stepsCompleted
        self.location = location
        self.status = status
        self.paymentMethod = paymentMethod
        self.currencyCode = currencyCode
        self.orderTotalAmount = orderTotalAmount
        self.transactionId = transactionId
    }
}
