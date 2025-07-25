//
//  UserBeaconStruct.swift
//  VLBeacon
//
//  Created by NEXGEN on 30/03/23.
//

import Foundation

public struct UserBeaconEventStruct {
    
    var ename: String
    var uid: String!
    var profid: String!
    var siteid: String!
    var pfm: String!
    var etstamp: String!
    var environment: String!
    var deviceid: String?
    var ref: String!
    var url: String!
    var appversion: String!
    var source: String?
    var eventdata: [String: Any]?
    var additionaldata: [String: Any]?
    var anonymousuid: String?
    var eventType: String?
    
    public init(eventName: UserBeaconEventEnum, userId: String? = nil, profileId: String? = nil, siteId: String? = nil, pfm: String? = nil, etstamp: String? = nil, environment: String? = nil, appversion: String? = nil, source: String?, eventData: BeaconEventPayloadProtocol? = nil, additionalData: [String : Any]? = nil, tokenIdentity: TokenIdentity?) {
        
        let tokenId = tokenIdentity ?? VLBeacon.getInstance().tokenIdentity
        
        self.ename = eventName.getBeaconEventNameString()
        self.profid = profileId ?? ""
        
        if let userID = tokenId?.userId {
            self.uid = userID
        } else {
            self.uid = userId
        }
        
        if let deviceID = tokenId?.deviceId {
            self.deviceid = deviceID
        } else {
            self.deviceid = Utility.sharedInstance.getUUID()
        }
        
        if let siteID = tokenId?.siteId {
            self.siteid = siteID
        } else {
            self.siteid = siteId
        }
        
        if let source{
            self.source = source
        } else {
            self.source = "VLBeacon"
        }
        
        self.pfm = Utility.sharedInstance.getPlatform()
        
        self.appversion = Utility.sharedInstance.getAppVersion()
        
        self.etstamp = Utility.sharedInstance.getCurrentTimestampInGMT()
        
        self.eventdata = eventData?.toDictionary()
        
        self.additionaldata = additionalData
        
    }
}

extension UserBeaconEventStruct: BeaconEventBodyProtocol {
    
    public func triggerEvents(authToken: String, beaconInstance: VLBeacon) {
        guard let beaconBaseURL = beaconInstance.userBeaconUrl else { return }
        
        DispatchQueue.global(qos: .utility).async {
            DataManger().postBeaconEvents(beaconStructBody: self, authenticationToken: authToken, baseUrl: beaconBaseURL)
        }
    }
    
    public func addBeaconInDBQuery() -> String? {
        var queryToAddBeaconEvent: String?
        
        let additionalDataString: String? = additionaldata?.jsonString()
        
        let eventDataString: String? = eventdata?.jsonString()
        
        queryToAddBeaconEvent = "insert into \(BeaconDBConstants().USERTABLENAME) (ename, uid, profid, siteid, pfm, etstamp, environment, deviceid, ref, url, appversion, source, eventData, additionalData) values('\(self.ename )','\(self.uid ?? "")','\(profid ?? "")','\(self.siteid ?? "")','\(self.pfm ?? "")','\(self.etstamp ?? "")','\(self.environment ?? "")','\(self.deviceid ?? "")','\(self.ref ?? "")','\(self.url ?? "")','\(self.appversion ?? "")','\(self.source ?? "")','\(eventDataString ?? "")','\(additionalDataString ?? "")')"
        
        return queryToAddBeaconEvent
    }
}
