//
//  TrayPayload.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 25/06/23.
//

import Foundation

public struct TrayPayload: BeaconEventPayloadProtocol{
    
    var vid: String?
    var trayId: String?
    var trayNumber: String?
    var itemNo: String?
    var additionalData: [String: Any]?
    
    public init(vid: String? = nil, trayId: String? = nil, trayNumber: Int? = nil, itemNo: Int? = nil, additionalData: [String : String]? = nil) {
        self.vid = vid
        self.trayId = trayId
        self.trayNumber = String(trayNumber ?? 0)
        self.itemNo = String(itemNo ?? 0)
        self.additionalData = additionalData
    }
}
