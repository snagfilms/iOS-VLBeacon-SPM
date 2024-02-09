//
//  TokenIdentity.swift
//  VLAuthenticationLib
//
//  Created by Gaurav Vig on 28/11/22.
//

import Foundation

public struct TokenIdentity: Decodable {
    var userId: String?
    var emailId: String?
    var phoneNumber: String?
    var siteName: String?
    var siteId: String?
    var countryCode: String?
    var deviceId: String?
    var anonymousId: String?

    enum CodingKeys: String, CodingKey {
        case userId
        case emailId = "email"
        case phoneNumber
        case siteName = "site"
        case siteId
        case countryCode
        case deviceId
        case anonymousId
    }
}
