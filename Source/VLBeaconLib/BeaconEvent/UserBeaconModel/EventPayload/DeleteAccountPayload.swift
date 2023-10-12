//
//  DeleteAccountPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct DeleteAccountPayload: BeaconEventPayloadProtocol{
    
    var customerName: String?
    var mobileNumber: String?
    var email: String?
    var additionalData: [String: Any]?
    
    public init(customerName: String? = nil, mobileNumber: String? = nil, email: String? = nil, additionalData: [String : String]? = nil) {
        self.customerName = customerName
        self.mobileNumber = mobileNumber
        self.email = email
        self.additionalData = additionalData
    }
}
