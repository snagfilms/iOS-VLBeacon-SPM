//
//  PlanPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct Status: BeaconEventPayloadProtocol{
    var errorCode: String?
    var message: String?
    
    public init(errorCode: String? = nil, message: String? = nil) {
        self.errorCode = errorCode
        self.message = message
    }
}

public struct PlanPayload: BeaconEventPayloadProtocol {
    
    var planId: String?
    var planName: String?
    var planDesc: String?
    var planType: String?
    var location: String?
    var additionalData: [String: Any]?
    var type: [String]?
    var stepsCompleted: [String]?
    var status: Status?
    var paymentMethod: String?
    var currencyCode: String?
    var orderTotalAmount: String?
    var transactionId: String?
    var monetizationType: String?
    var pgId: String?
    var pgName: String?
    var modType: String?
    var tveProvider: String?
    var mvpdProvider: String?
    
    public init(planId: String? = nil, planName: String? = nil, planDesc: String? = nil, planType: String? = nil, additionalData: [String : String]? = nil, type: [String]? = nil, stepsCompleted: [String]? = nil, location: String? = nil, status: Status? = nil, paymentMethod: String? = nil, currencyCode: String? = nil, orderTotalAmount: String? = nil, transactionId: String? = nil, monetizationType: String? = nil, pgId: String? = nil, pgName: String? = nil, modType: String? = nil, tveProvider: String? = nil, mvpdProvider: String? = nil) {
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
        self.monetizationType = monetizationType
        self.pgId = pgId
        self.pgName = pgName
        self.modType = modType
        self.tveProvider = tveProvider
        self.mvpdProvider = mvpdProvider
    }
}
