//
//  AuthenticationPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 18/06/23.
//

import Foundation

public struct AuthenticationPayload: BeaconEventPayloadProtocol {
    
    var type: String?
    var subType: String?
    var email : String?
    var phoneNo : String?
    var mvpd : String?
    var existingUser: String?
    var additionalData: [String: Any]?
    
    public init(type: AuthType? = nil, subType: AuthSubType? = nil, email: String? = nil, phoneNumber: String? = nil, mvpd: String? = nil, existingUser: Bool? = nil, additionalData: [String : String]? = nil, tokenIdentity: TokenIdentity?) {
        
        let tokenId = tokenIdentity ?? VLBeacon.getInstance().tokenIdentity
        
        self.type = type?.typeName
        self.subType = subType?.subTypeName
        self.mvpd = mvpd
        
        if let existingUser {
            self.existingUser = String(existingUser)
        }
        
        if let emailID = tokenId?.emailId {
            self.email = emailID
        } else {
            self.email = email
        }
        
        if let phoneNumber = tokenId?.phoneNumber {
            self.phoneNo = phoneNumber
        } else {
            self.phoneNo = phoneNumber
        }
        
        self.additionalData = additionalData
    }
}
