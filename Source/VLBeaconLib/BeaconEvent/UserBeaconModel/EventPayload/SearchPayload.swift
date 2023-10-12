//
//  SearchPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct SearchPayload: BeaconEventPayloadProtocol{
    
    var searchText : String?
    var items: [String]?
    var additionalData: [String: Any]?
    
    public init(searchText: String? = nil, items: [String]? = nil, additionalData: [String : String]? = nil) {
        self.searchText = searchText
        self.items = items
        self.additionalData = additionalData
    }
}
