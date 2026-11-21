//
//  SharePayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct SharePayload: BeaconEventPayloadProtocol {
    var vid: String?
    var contentUrl: String?
    var shareOption: String?
    var additionalData: [String: Any]?
    
   public init(vid: String? = nil, contentUrl: String? = nil, shareOption: SocialEnum? = nil, additionalData: [String : String]? = nil) {
       self.vid = vid
        self.contentUrl = contentUrl
        self.shareOption = shareOption?.rawValue
        self.additionalData = additionalData
    }
}
