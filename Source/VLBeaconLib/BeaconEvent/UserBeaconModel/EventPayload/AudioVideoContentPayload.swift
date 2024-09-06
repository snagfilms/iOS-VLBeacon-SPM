//
//  AudioVideoContentPayload.swift
//
//
//  Created by Rakesh  Sharma on 06/09/24.
//

import Foundation

public struct AudioVideoContentPayload: BeaconEventPayloadProtocol {
    
    var contentDetails: [String: Any]?
    var gameDetails: [String: Any]?
    
    public init(contentDetails: [String : String]? = nil, gameDetails: [String : String]? = nil) {
        self.gameDetails = gameDetails
        self.contentDetails = contentDetails
    }
}
