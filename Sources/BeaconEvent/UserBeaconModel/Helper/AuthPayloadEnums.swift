//
//  AuthPayloadEnums.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 22/06/23.
//

import Foundation

public enum AuthType {
    case social
    case viewlift
    case tve
    case custom(eventName: String)

    var typeName: String {
        switch self {
        case .social:
            return "social"
        case .viewlift:
            return "viewlift"
        case .tve:
            return "tve"
        case .custom(let eventName):
            return eventName
        }
    }
}


public enum AuthSubType {
    case google
    case apple
    case facebook
    case loginWithMobile
    case activateDevice
    case email
    case phoneNo
    case adobe
    case verimatrix
    case custom(eventName: String)

    var subTypeName: String {
        switch self {
        case .google:
            return "google"
        case .apple:
            return "apple"
        case .facebook:
            return "facebook"
        case .loginWithMobile:
            return "loginWithMobile"
        case .activateDevice:
            return "activateDevice"
        case .email:
            return "email"
        case .phoneNo:
            return "phoneNo"
        case .adobe:
            return "adobe"
        case .verimatrix:
            return "verimatrix"
        case .custom(let eventName):
            return eventName
        }
    }
}
