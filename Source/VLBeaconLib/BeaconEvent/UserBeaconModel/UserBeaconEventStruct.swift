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
    
    public init(
        eventName: UserBeaconEventEnum,
        userId: String? = nil,
        profileId: String? = nil,
        siteId: String? = nil,
        pfm: String? = nil,
        etstamp: String? = nil,
        environment: String? = nil,
        appversion: String? = nil,
        source: String?,
        eventData: [String: Any]? = nil,
        additionalData: [String : Any]? = nil,
        tokenIdentity: TokenIdentity?
    ) {
        self.init(
            eventName: eventName.getBeaconEventNameString(),
            userId: userId,
            profileId: profileId,
            siteId: siteId,
            pfm: pfm,
            etstamp: etstamp,
            environment: environment,
            appversion: appversion,
            source: source,
            eventData: eventData,
            additionalData: additionalData,
            tokenIdentity: tokenIdentity
        )
    }

    /// String-based init for cross-module callers — avoids passing `UserBeaconEventEnum`
    /// across a dynamic VLBeaconLib boundary (`EXC_BAD_ACCESS` / null type metadata).
    public init(
        eventName: String,
        userId: String? = nil,
        profileId: String? = nil,
        siteId: String? = nil,
        pfm: String? = nil,
        etstamp: String? = nil,
        environment: String? = nil,
        appversion: String? = nil,
        source: String?,
        eventData: [String: Any]? = nil,
        additionalData: [String : Any]? = nil,
        tokenIdentity: TokenIdentity?
    ) {
        let tokenId = tokenIdentity ?? VLBeacon.getInstance().tokenIdentity
        let beaconInstance = VLBeacon.getInstance()
        
        self.ename = eventName
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
        
        if let source {
            self.source = source
        } else {
            self.source = "VLBeacon"
        }
        
        // Prefer explicit caller overrides when provided (feature branch API).
        self.pfm = pfm ?? Utility.sharedInstance.getPlatform()
        self.appversion = appversion ?? Utility.sharedInstance.getAppVersion()
        self.etstamp = etstamp ?? Utility.sharedInstance.getCurrentTimestampInGMT()
        self.environment = environment ?? beaconInstance.environment
        self.ref = ""
        self.url = ""
        
        // Dictionary form avoids EXC_BAD_ACCESS when crossing dynamic VLBeaconLib boundary.
        self.eventdata = eventData
        self.additionaldata = additionalData
    }
}

// MARK: - Public methods
public extension UserBeaconEventStruct {
    func addBeaconInDBQuery() -> String? {
        var queryToAddBeaconEvent: String?
        
        let additionalDataString: String? = additionaldata?.jsonString()
        
        let eventDataString: String? = eventdata?.jsonString()
        
        queryToAddBeaconEvent = "insert into \(BeaconDBConstants().USERTABLENAME) (ename, uid, profid, siteid, pfm, etstamp, environment, deviceid, ref, url, appversion, source, eventData, additionalData) values('\(self.ename )','\(self.uid ?? "")','\(profid ?? "")','\(self.siteid ?? "")','\(self.pfm ?? "")','\(self.etstamp ?? "")','\(self.environment ?? "")','\(self.deviceid ?? "")','\(self.ref ?? "")','\(self.url ?? "")','\(self.appversion ?? "")','\(self.source ?? "")','\(eventDataString ?? "")','\(additionalDataString ?? "")')"
        
        return queryToAddBeaconEvent
    }
}

// MARK: - BeaconEventBodyProtocol implementation
extension UserBeaconEventStruct: BeaconEventBodyProtocol {
    public func triggerEvents(authToken: String, beaconInstance: VLBeacon) {
        guard let beaconBaseURL = beaconInstance.userBeaconUrl else { return }
        
        DispatchQueue.global(qos: .utility).async {
            DataManger().postBeaconEvents(beaconStructBody: self, authenticationToken: authToken, baseUrl: beaconBaseURL)
        }
    }
}
