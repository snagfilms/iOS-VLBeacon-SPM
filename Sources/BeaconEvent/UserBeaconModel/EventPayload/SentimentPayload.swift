//
//  SentimentPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct SentimentPayload: BeaconEventPayloadProtocol{
    
    var vid: String
    var comment: String?
    var additionalData: [String: Any]?
    
    public init(vid: String, comment: String? = nil, additionalData: [String : String]? = nil) {
        self.vid = vid
        self.comment = comment
        self.additionalData = additionalData
    }
}
