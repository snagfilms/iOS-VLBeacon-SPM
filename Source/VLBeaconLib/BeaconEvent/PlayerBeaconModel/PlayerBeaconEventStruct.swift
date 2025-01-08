//
//  PlayerBeaconEventStruct.swift
//  VLBeacon
//
//  Created by NEXGEN on 01/04/23.
//

import Foundation
import UIKit

public struct PlayerBeaconEventStruct {

    var aid: String!
    var cid: String!
    var pfm: String!
    var vid: String!
    var uid: String!
    var profid: String!
    var pa: String!
    var player: String?
    var environment: String!
    var media_type: String?
    var tstampoverride: String?
    var stream_id: String?
    var dp1: String?
    var dp2: String?
    var dp3: String?
    var dp4: String?
    var dp5: String?
    var ref: String!
    var apos: String?
    var apod: String?
    var vpos: String!
    var url: String!
    var embedUrl: String?
    var ttFirstFrame: String?
    var bitrate: String?
    var connectionSpeed: String?
    var resolutionheight: String?
    var resolutionwidth: String?
    var bufferHealth: String?
    var plid: String?
    var fcid: String?
    var seriesid: String?
    var seasonid: String?
    var seasonnumber: String?
    var tstamp: String!
    var subscription_type: String?
    var mvpdprovider: String?
    var guid: String?
    var appversion: String?
    var duration: String?
    var deviceid: String?
    var siteid: String?
    var source: String?
    var tveProvider: String?
    var anonymousuid: String?
    
    var additionaldata: [String: Any]?
    
    public init(eventName: PlayerBeaconEventEnum, vid: String? = nil, profid: String? = nil, userId: String? = nil, player: String? = nil,  media_type: String? = nil, tstampoverride: String? = nil, stream_id: String? = nil, dp1: String? = nil, dp2: String? = nil, dp3: String? = nil, dp4: String? = nil, dp5: String? = nil, ref: String? = nil, apos: Int? = nil, apod: Int? = nil, vpos: Int? = nil, url: String? = nil, embedUrl: String? = nil, ttFirstFrame: Int? = nil, bitrate: Int? = nil, connectionSpeed: Int? = nil, resolution: CGRect? = nil, bufferHealth: Int? = nil, plid: String? = nil, fcid: String? = nil, seriesid: String? = nil, seasonid: String? = nil, seasonnumber: String? = nil, subscription_type: String? = nil, mvpdprovider: String? = nil, guid: String? = nil, appversion: String? = nil, duration: String? = nil, siteId: String? = nil, environment: String? = nil, source: String?, tveProvider: String? = nil, additionalData: [String: Any]? = nil, tokenIdentity: TokenIdentity?) {
        
        guard let tokenId = tokenIdentity ?? VLBeacon.getInstance().tokenIdentity else { return }
        
        if (tokenId.userId ?? "").isEmpty {
            return
        }
        
        self.pa = eventName.getBeaconEventNameString()
        self.vid = vid ?? ""
        self.profid = profid ?? ""
        self.player = player
        self.media_type = media_type
        self.tstampoverride = tstampoverride
        self.stream_id = stream_id
        self.dp1 = dp1
        self.dp2 = dp2
        self.dp3 = dp3
        self.dp4 = dp4
        self.dp5 = dp5
        self.ref = ref ?? ""
        self.url = url ?? ""
        self.embedUrl = embedUrl
        self.plid = plid
        self.fcid = fcid
        self.seriesid = seriesid
        self.seasonid = seasonid
        self.seasonnumber = seasonnumber
        self.subscription_type = subscription_type
        self.mvpdprovider = mvpdprovider
        self.guid = guid
        self.appversion = appversion
        self.duration = duration
        
        self.aid = tokenId.siteName ?? ""
		self.cid = tokenId.siteId ?? ""
        
        if let apos {
            self.apos = String(describing: apos)
        }
        
        if let apod {
            self.apod = String(describing: apod)
        }
        
		self.vpos = String(describing: vpos ?? 0)
        
        if let ttFirstFrame {
            self.ttFirstFrame = String(describing: ttFirstFrame)
        }
        
        if let bitrate {
            self.bitrate = String(describing: bitrate)
        }
        
        if let connectionSpeed {
            self.connectionSpeed = String(describing: connectionSpeed)
        }
        
        if let bitrate, let res = self.getResolutionFromBitrate(bitrate) {
            self.resolutionheight = String(describing: Int(res.height))
            self.resolutionwidth = String(describing: Int(res.width))
        } else {
            self.resolutionheight = "0"
            self.resolutionwidth = "0"
        }
        
        
        if let bufferHealth {
            self.bufferHealth = String(describing: bufferHealth)
        }
        
        if let userID = tokenId.userId {
            self.uid = userID
        } else {
            self.uid = userId
        }
        
        if let deviceID = tokenId.deviceId {
            self.deviceid = deviceID
        } else {
            self.deviceid = Utility.sharedInstance.getUUID()
        }
        
        if let siteID = tokenId.siteId {
            self.siteid = siteID
        } else {
            self.siteid = siteId
        }
        
        if let source{
            self.source = source
        } else {
            self.source = "VLBeacon"
        }
        
        if let appversion{
            self.appversion = appversion
        } else {
            self.appversion = Utility.sharedInstance.getAppVersion()
        }
        
        
        self.pfm = Utility.sharedInstance.getPlatform()
        
        self.tstamp = Utility.sharedInstance.getCurrentTimestampInGMT()
        
        self.tveProvider = tveProvider
        self.additionaldata = additionalData
    }
    
    
    /**Resolution mapping: These values assume H.264 video encoding and a typical 30fps frame rate, which are common for streaming:

    < 1 Mbps (1000 kbps): 360p (or lower)
    1-2 Mbps (1000-2000 kbps): 480p
    2-5 Mbps (2000-5000 kbps): 720p
    5-10 Mbps (5000-10000 kbps): 1080p
    10-15 Mbps (10000-15000 kbps): 1440p (2K)
    > 15 Mbps (15000+ kbps): 4K
     */
    
    private func getResolutionFromBitrate(_ bitrate: Int) -> (width: Int, height: Int)? {
        switch bitrate {
        case 0..<1000000:
            // Bitrate < 1 Mbps: Approximate resolution 360p
            return (width: 640, height: 360)
            
        case 1000000..<2000000:
            // Bitrate 1-2 Mbps: Approximate resolution 480p
            return (width: 854, height: 480)
            
        case 2000000..<5000000:
            // Bitrate 2-5 Mbps: Approximate resolution 720p
            return (width: 1280, height: 720)
            
        case 5000000..<10000000:
            // Bitrate 5-10 Mbps: Approximate resolution 1080p
            return (width: 1920, height: 1080)
            
        case 10000000..<15000000:
            // Bitrate 10-15 Mbps: Approximate resolution 1440p (2K)
            return (width: 2560, height: 1440)
            
        case 15000000...:
            // Bitrate > 15 Mbps: Approximate resolution 4K
            return (width: 3840, height: 2160)
            
        default:
            // If bitrate is unknown or not in expected ranges
            return nil
        }
    }
}


extension PlayerBeaconEventStruct: BeaconEventBodyProtocol {
    
    public func triggerEvents(authToken: String, beaconInstance: VLBeacon) {
        guard let beaconBaseURL = beaconInstance.playerBeaconUrl else { return }
        
        DispatchQueue.global(qos: .utility).async {
            DataManger().postBeaconEvents(beaconStructBody: self, authenticationToken: authToken, baseUrl: beaconBaseURL)
        }
    }
    
    public func addBeaconInDBQuery() -> String? {
        var queryToAddBeaconEvent: String?
        
        let customDataString: String? = self.additionaldata?.jsonString()
        
        queryToAddBeaconEvent = "insert into \(BeaconDBConstants().PLAYERTABLENAME)  (aid, cid, pfm, vid, uid, profid, pa, player, environment, media_type, tstampoverride , stream_id, dp1, dp2, dp3, dp4, dp5, ref, apos, apod, vpos, url, embedUrl, ttfirstframe, bitrate, connectionspeed, resolutionheight , resolutionwidth, bufferhealth, plid, fcid, seriesid, seasonid, seasonnumber, tstamp, subscription_type, mvpdprovider, guid, appversion, duration, deviceid, siteid, source, tveprovider, additionalData ) values('\(self.aid ?? "")','\(self.cid ?? "")','\(self.pfm ?? "")','\(self.vid ?? "")','\(self.uid ?? "")','\(self.profid ?? "")','\(self.pa ?? "")','\(self.player ?? "")','\(self.environment ?? "")','\(self.media_type ?? "")','\(self.tstampoverride ?? "")','\(self.stream_id ?? "")','\(self.dp1 ?? "")','\(self.dp2 ?? "")','\(self.dp3 ?? "")','\(self.dp4 ?? "")','\(self.dp5 ?? "")','\(self.ref ?? "")','\(self.apos ?? "")','\(self.apod ?? "")','\(self.vpos ?? "")','\(self.url ?? "")','\(self.embedUrl ?? "")','\(self.ttFirstFrame ?? "")','\(self.bitrate ?? "")','\(self.connectionSpeed ?? "")','\(self.resolutionheight ?? "")','\(self.resolutionwidth ?? "")','\(self.bufferHealth ?? "")','\(self.plid ?? "")','\(self.fcid ?? "")','\(self.seriesid ?? "")','\(self.seasonid ?? "")','\(self.seasonnumber ?? "")','\(self.tstamp ?? "")','\(self.subscription_type ?? "")','\(self.mvpdprovider ?? "")','\(self.guid ?? "")','\(self.appversion ?? "")','\(self.duration ?? "")','\(self.deviceid ?? "")','\(self.siteid ?? "")','\(self.source ?? "")','\(self.tveProvider ?? "")','\(customDataString ?? "")')"
        
        return queryToAddBeaconEvent
        
    }
}
