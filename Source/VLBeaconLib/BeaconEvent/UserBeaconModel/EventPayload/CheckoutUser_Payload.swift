//
//  CheckoutUserPayload.swift
//
//
//  Created by NexG on 24/09/24.
//

import Foundation
public struct CheckoutUserPayload: BeaconEventPayloadProtocol {
    var uid: String?
    var anonymousuid: String?
    var mergeType: String?
    var email: String?
    var phoneNumber: String?
    var registeredVia: String?
    var consentStatus: String?
    var error: String?
    var message: String?
    var pageUrl: String?
    
    public init(uid: String? = nil,
                anonymousuid: String? = nil,
                mergeType: String? = nil,
                email: String? = nil,
                phoneNumber: String? = nil,
                registeredVia: String? = nil,
                consentStatus: String? = nil,
                error: String? = nil,
                message: String? = nil,
                pageUrl: String? = nil) {
        self.uid = uid
        self.anonymousuid = anonymousuid
        self.mergeType = mergeType
        self.email = email
        self.phoneNumber = phoneNumber
        self.registeredVia = registeredVia
        self.consentStatus = consentStatus
        self.error = error
        self.message = message
        self.pageUrl = pageUrl
    }
}
