//
//  StoreKitPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 18/06/23.
//

import Foundation

public struct StoreKitPayload: BeaconEventPayloadProtocol {
    
    var planId: String?
    var planName: String?
    var planDesc: String?
    var planType: String?
    var paymentMethod: String?
    var promotionCode: String?
    var discountAmount: String?
    var purchaseType: String?
    var orderSubTotalAmount: String?
    var orderTaxAmount: String?
    var orderTotalAmount: String?
    var currencyCode: String?
    var transactionId: String?
    var additionalData: [String: Any]?
    
    public init(planId: String? = nil, planName: String? = nil, planDesc: String? = nil, planType: String? = nil, paymentMethod: String? = nil, promotionCode: String? = nil, discountAmount: Int? = nil, purchaseType: String? = nil, orderSubTotalAmount: Int? = nil, orderTaxAmount: Int? = nil, orderTotalAmount: Int? = nil, currencyCode: String? = nil, transactionId: String? = nil, additionalData: [String : String]? = nil) {
        self.planId = planId
        self.planName = planName
        self.planDesc = planDesc
        self.planType = planType
        self.paymentMethod = paymentMethod
        self.promotionCode = promotionCode
        self.discountAmount = String(discountAmount ?? 0)
        self.purchaseType = purchaseType
        self.orderSubTotalAmount = String(orderSubTotalAmount ?? 0)
        self.orderTaxAmount = String(orderTaxAmount ?? 0)
        self.orderTotalAmount = String(orderTotalAmount ?? 0)
        self.currencyCode = currencyCode
        self.transactionId = transactionId
        self.additionalData = additionalData
    }
}
