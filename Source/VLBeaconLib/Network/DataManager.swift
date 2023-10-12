//
//  DataManager.swift
//  VLBeacon
//
//  Created by NEXGEN on 28/03/23.
//

import Foundation

class DataManger: NSObject {
        
    //MARK: Api to post beacon data
    func postBeaconEvents(beaconStructBody: BeaconEventBodyProtocol, authenticationToken: String, baseUrl: String) {

        if NetworkStatus.sharedInstance.isNetworkAvailable() {
            Log.shared.i("Internet Detected. Posting the event.")
            self.net_postBeaconEvents(beaconDict: beaconStructBody.toDictionary(), authenticationToken: authenticationToken, baseUrl: baseUrl)
            
        }
        else {
            #if os(iOS)
            let sharedManager = BeaconQueryManager.sharedInstance
            Log.shared.i("No Internet Detected. Adding the event to the DB.")
            sharedManager.addBeaconEventInDB(beaconStructBody)
            #endif
        }
    }
    
    func net_postBeaconEvents(beaconDict: Dictionary<String, Any>, authenticationToken: String, baseUrl: String) {

        var parameterArray = Array<Dictionary<String,Any>>()
        parameterArray.append(beaconDict)
        
        NetworkHandler.sharedInstance.callNetworkToPostBeaconData(apiURL: baseUrl, requestType: .post, authenticationToken: authenticationToken, requestHeaders: nil, parameters: parameterArray ) { (_ responseConfigData: Bool?) in
            Log.shared.i("Beacon event posted: \(String(describing: responseConfigData))")
        }
    }
    
    func net_postOfflineBeaconEvents(beaconEventArray : Array<Dictionary<String,Any>>, authenticationToken: String, baseUrl: String, completionHandler: @escaping ((_ response: Bool) -> Void)) {

        NetworkHandler.sharedInstance.callNetworkToPostBeaconData(apiURL: baseUrl, requestType: .post, authenticationToken: authenticationToken, requestHeaders:nil , parameters: beaconEventArray ) { (_ responseConfigData: Bool?) in
            Log.shared.i("Offline Beacon events posted: \(String(describing: responseConfigData))")
            completionHandler(responseConfigData!)
        }
    }
}


