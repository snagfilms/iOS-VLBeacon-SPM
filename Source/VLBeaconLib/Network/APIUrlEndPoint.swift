//
//  APIUrlEndPoint.swift
//  VLBeacon
//
//  Created by NEXGEN on 07/06/23.
//

import Foundation

enum APIUrl {
    static func getAPIBaseUrl() -> String? {
        if let baseUrl = VLBeacon.getInstance().beaconBaseUrl {
            return baseUrl
        }
        
        guard let url = VLBeacon.getInstance().getBeaconBaseUrl() else { return nil }
        
        VLBeacon.getInstance().beaconBaseUrl = url
        
        return url
    }
}

enum APIUrlEndPoint: String {
    case playerBeacon = "/player-beacon"
    case userBeacon = "/user-beacon"
}
