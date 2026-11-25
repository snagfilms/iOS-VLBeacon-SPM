//
//  BeaconDBConstants.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 18/06/23.
//

import Foundation

internal class BeaconDBConstants {
    
    internal let DBNAME = "beaconEvents.sql"
    internal let USERTABLENAME = "userBeaconEventTable"
    internal let PLAYERTABLENAME = "playerBeaconEventTable"
    
    internal let USER_TABLE_COLUMNS_QUERY = "userBeaconEventId INTEGER PRIMARY KEY AUTOINCREMENT, ename TEXT, uid TEXT, profid TEXT, siteid TEXT, pfm TEXT, etstamp TEXT, environment TEXT, deviceid TEXT, ref TEXT, url TEXT, appversion TEXT, source TEXT, eventData TEXT, additionalData TEXT, pageid TEXT"
    
    internal let PLAYER_TABLE_COLUMNS_QUERY = "playerBeaconEventId INTEGER PRIMARY KEY AUTOINCREMENT, aid TEXT, cid TEXT ,pfm TEXT ,vid TEXT, uid TEXT , profid TEXT ,pa TEXT ,player TEXT ,environment TEXT ,media_type TEXT, tstampoverride TEXT ,stream_id TEXT ,dp1 TEXT, dp2 TEXT, dp3 TEXT, dp4 TEXT, dp5 TEXT, ref TEXT, apos TEXT, apod TEXT, vpos TEXT, url TEXT, embedurl TEXT, ttfirstframe TEXT, bitrate TEXT, connectionspeed TEXT, resolutionheight TEXT, resolutionwidth TEXT, bufferhealth TEXT, plid TEXT, fcid TEXT, seriesid TEXT, seasonid TEXT, seasonnumber TEXT, tstamp TEXT, subscription_type TEXT, mvpdprovider TEXT, guid TEXT, appversion TEXT, duration TEXT, deviceid TEXT, siteid TEXT, source TEXT, tveprovider TEXT, error_message TEXT, error_code TEXT, additionalData TEXT"
    
    /// Columns added after the original player table. Existing databases are migrated with ALTER TABLE.
    internal let PLAYER_TABLE_MIGRATION_COLUMNS = ["tveprovider", "error_message", "error_code"]
    
}
