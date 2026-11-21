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
    var isVertical: String?
    var pgName: String?
    var pgId: String?
    var modType: String?
    var modID: String?
    var buttonName: String?
    var additionalData: [String: Any]?
    
    public init(vid: String? = nil,
                trayId: String? = nil,
                trayNumber: Int? = nil,
                itemNo: Int? = nil,
                isVertical: Bool? = nil,
                pgName: String? = nil,
                pgId: String? = nil,
                modType: String? = nil,
                modID: String? = nil,
                buttonName: String? = nil,
                additionalData: [String : String]? = nil) {
        
        self.trayId = trayId
        self.trayNumber = trayNumber != nil ? String(trayNumber!) : nil
        self.itemNo = itemNo != nil ? String(itemNo!) : nil
        self.vid = vid
        self.isVertical = Utility.sharedInstance.getBoolType(isVertical ?? false)
        self.pgName = pgName
        self.pgId = pgId
        self.modType = modType
        self.modID = modID
        self.buttonName = buttonName
        self.additionalData = additionalData
    }
}
