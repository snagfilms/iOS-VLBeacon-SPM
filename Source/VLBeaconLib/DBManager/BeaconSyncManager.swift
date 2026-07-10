//
//  BeaconSyncManager.swift
//  VLBeacon
//
//  Created by NEXGEN on 29/03/23.
//

import Foundation

internal final class BeaconSyncManager {
    static let sharedInstance: BeaconSyncManager = {
        let instance = BeaconSyncManager()
        return instance
    }()
    
    private init() {
        queryManager = BeaconQueryManager.sharedInstance
    }
    
    var queryManager: BeaconQueryManager
}

// MARK: - Internal methods
extension BeaconSyncManager {
    func startSyncingTheEvents(vlBeacon: VLBeacon, authenticationToken: String, withSuccess success: @escaping (_: Bool) -> Void) {
        for beaconType in BeaconType.allCases {
            if let arrayOfBeaconEvents = queryManager.fetchTheUnsyncronisedBeaconEvents(beaconType), !arrayOfBeaconEvents.isEmpty {
                Log.shared.d("DB: Syncing DB \(beaconType) Events")
                
                self.postDataToServer(
                    vlBeacon: vlBeacon,
                    arrayOfBeaconEvents: arrayOfBeaconEvents,
                    authenticationToken: authenticationToken,
                    beaconType: beaconType
                )
            } else {
                Log.shared.d("DB: No DB \(beaconType) Events")
            }
        }
    }
    
    func postDataToServer(vlBeacon: VLBeacon, arrayOfBeaconEvents : Array<Dictionary<String,Any>>, authenticationToken: String, beaconType: BeaconType) {
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
        
        DataManger().net_postOfflineBeaconEvents(beaconEventArray: arrayOfBeaconEvents,
                                                 authenticationToken: authenticationToken,
                                                 baseUrl: beaconEndpoint) { [weak self] (response) in
            guard let self else { return }
            guard response else { return }
            
            self.queryManager.removeBeaconEventFromTheBeaconDB(beaconType)
        }
    }
}
