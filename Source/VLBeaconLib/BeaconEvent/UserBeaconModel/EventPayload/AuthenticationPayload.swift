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
        self.init(
            type: type?.typeName,
            subType: subType?.subTypeName,
            email: email,
            phoneNumber: phoneNumber,
            mvpd: mvpd,
            existingUser: existingUser,
            additionalData: additionalData,
            tokenIdentity: tokenIdentity
        )
    }

    /// String-based init for cross-module callers — avoids passing AuthType/AuthSubType
    /// across a dynamic VLBeaconLib boundary.
    public init(type: String? = nil, subType: String? = nil, email: String? = nil, phoneNumber: String? = nil, mvpd: String? = nil, existingUser: Bool? = nil, additionalData: [String : String]? = nil, tokenIdentity: TokenIdentity?) {
        
        let tokenId = tokenIdentity ?? VLBeacon.getInstance().tokenIdentity
        
        self.type = type
        self.subType = subType
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
