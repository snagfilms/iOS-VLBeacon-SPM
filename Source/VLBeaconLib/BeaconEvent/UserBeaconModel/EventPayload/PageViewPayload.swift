//
//  PageViewPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct PageViewPayload: BeaconEventPayloadProtocol{
    
    var pgId: String?
    var pgName: String?
    var pgUrl: String?
    var sourceUrl: String?
    var additionalData: [String: Any]?
    
    public init(pgId: String? = nil, pgName: String? = nil, pgUrl: String? = nil, sourceUrl: String? = nil, additionalData: [String : String]? = nil) {
        self.pgId = pgId
        self.pgName = pgName
        self.pgUrl = pgUrl
        self.sourceUrl = sourceUrl
        self.additionalData = additionalData
    }
}
