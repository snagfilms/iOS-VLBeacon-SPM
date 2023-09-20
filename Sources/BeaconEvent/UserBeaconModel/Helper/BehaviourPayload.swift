//
//  BehaviourPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public enum SocialEnum {
    case facebook
    case instagram
    case twitter
    case whatsApp
    case email
    case custom(eventName: String)

    var rawValue: String {
        switch self {
        case .facebook:
            return "Facebook"
        case .instagram:
            return "Instagram"
        case .twitter:
            return "Twitter"
        case .whatsApp:
            return "WhatsApp"
        case .email:
            return "Email"
        case .custom(let eventName):
            return eventName
        }
    }
}

public enum UpdateType: String{
    
    case upgrade
    case downgrade
}

//public enum BoolType: String{
//
//    case yes
//    case no
//}
