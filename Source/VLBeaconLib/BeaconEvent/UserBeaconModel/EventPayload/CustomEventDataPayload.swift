//
//  File.swift
//  
//
//  Created by Rakesh  Sharma on 05/09/24.
//

import Foundation

public struct CustomEventDataPayload: BeaconEventPayloadProtocol{
    
    var eventData: [String: Any]?
    
    public init(eventData: [String : String]? = nil) {
        self.eventData = eventData
    }
}
