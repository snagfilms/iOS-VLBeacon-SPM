//
//  APIUrlEndPoint.swift
//  VLBeacon
//
//  Created by NEXGEN on 07/06/23.
//

import Foundation

enum APIUrl {
    static func getUserBeaconBaseUrl() -> String? {
        return VLBeacon.getInstance().userBeaconUrl
    }
    
    static func getPlayerBeaconBaseUrl() -> String? {
        return VLBeacon.getInstance().playerBeaconUrl
    }
}
