//
//  BeaconSyncManager.swift
//  VLBeacon
//
//  Created by NEXGEN on 29/03/23.
//

import Foundation

internal class BeaconSyncManager {
    
    static let sharedInstance : BeaconSyncManager = {
        let instance = BeaconSyncManager()
        return instance
    }()
    
    private init() {
        queryManager = BeaconQueryManager.sharedInstance
    }
    
    var queryManager: BeaconQueryManager
    
    //MARK:-  Sync Events With Server
    func startSyncingTheEvents(vlBeacon: VLBeacon, authenticationToken: String, withSuccess success: @escaping (_: Bool) -> Void) {
        
        for beaconType in BeaconType.allCases {
            if let arrayOfBeaconEvents = queryManager.fetchTheUnsyncronisedBeaconEvents(beaconType), !arrayOfBeaconEvents.isEmpty {
                Log.shared.d("DB: Syncing DB \(beaconType) Events")
                self.postDataToServer(vlBeacon: vlBeacon, arrayOfBeaconEvents: arrayOfBeaconEvents, authenticationToken: authenticationToken, beaconType: beaconType)
            } else {
                Log.shared.d("DB: No DB \(beaconType) Events")
            }
        }
    }
    
    //MARK:-POST data to server
    /// Method to post data to server in form on Array with nested dictionaries
    ///
    /// - Parameter arrayOfBeaconEvents: return Array
    func postDataToServer(vlBeacon: VLBeacon, arrayOfBeaconEvents : Array<Dictionary<String,Any>>, authenticationToken: String, beaconType: BeaconType)
    {
        Log.shared.d("DB: Posting DB \(beaconType) Events")
        
        var beaconEndpoint: String = ""
        
        switch beaconType {
        case .user:
            beaconEndpoint = APIUrl.getUserBeaconBaseUrl() ?? ""
        case .player:
            beaconEndpoint = APIUrl.getPlayerBeaconBaseUrl() ?? ""
        }
        
        if beaconEndpoint.isEmpty {
            return
        }
        
        DataManger().net_postOfflineBeaconEvents(beaconEventArray: arrayOfBeaconEvents, authenticationToken: authenticationToken, baseUrl: beaconEndpoint) { (response) in
            if(response) {
                self.queryManager.removeBeaconEventFromTheBeaconDB(beaconType)
            }
        }
    }
}
