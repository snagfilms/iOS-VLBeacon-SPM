//
//  ApplyCodePayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct ApplyCodePayload: BeaconEventPayloadProtocol{
    
    var status: String?
    var promotionCode: String?
    var discountAmount: String?
    var additionalData: [String: Any]?
    
    public init(status: String? = nil, promotionCode: String? = nil, discountAmount: Int? = nil, additionalData: [String : String]? = nil) {
        self.status = status
        self.promotionCode = promotionCode
        self.discountAmount = String(discountAmount ?? 0)
        self.additionalData = additionalData
    }
}
