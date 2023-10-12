//
//  LanguageSelectionPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct LanguageSelectionPayload: BeaconEventPayloadProtocol{
    
    var languageCode: String?
    var additionalData: [String: Any]?
    
    public init(languageCode: String? = nil, additionalData: [String : String]? = nil) {
        self.languageCode = languageCode
        self.additionalData = additionalData
    }
}
