//
//  TokenIdentity.swift
//  VLAuthenticationLib
//
//  Created by Gaurav Vig on 28/11/22.
//

import Foundation

public struct TokenIdentity: Decodable {
    public var userId: String?
    public var emailId: String?
    public var phoneNumber: String?
    public var siteName: String?
    public var siteId: String?
    public var countryCode: String?
    public var deviceId: String?
    public var anonymousId: String?

    public enum CodingKeys: String, CodingKey {
        case userId
        case emailId = "email"
        case phoneNumber
        case siteName = "site"
        case siteId
        case countryCode
        case deviceId
        case anonymousId
    }

    public init(
    userId: String?,
    emailId: String?,
    phoneNumber: String?,
    siteName: String?,
    siteId: String?,
    countryCode: String?,
    deviceId: String?,
    anonymousId: String?
) {
    self.userId = userId
    self.emailId = emailId
    self.phoneNumber = phoneNumber
    self.siteName = siteName
    self.siteId = siteId
    self.countryCode = countryCode
    self.deviceId = deviceId
    self.anonymousId = anonymousId
}
}
