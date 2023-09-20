//
//  CustomerFeedbackPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct CustomerFeedbackPayload: BeaconEventPayloadProtocol{
    
    var customerComment: String?
    var additionalData: [String: Any]?
    
    public init(customerComment: String? = nil, additionalData: [String : String]? = nil) {
        self.customerComment = customerComment
        self.additionalData = additionalData
    }
}
