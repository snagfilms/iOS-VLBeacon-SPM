//
//  NetworkStatus.swift
//  VLBeacon
//
//  Created by NEXGEN on 29/03/23.
//

class NetworkStatus {
    
    static let sharedInstance = NetworkStatus()
    
    private init() {
//        print(">>>>> NetworkStatus <<<<<")
        reachability = NetworkReachabilityManager()
        
//        reachability?.listener = { status in
//            print("status changed: \(status)")
////            self.syncOfflineDat()
//        }
        
//        reachability?.startListening()
    }
    
    var reachability: NetworkReachabilityManager?
    
    func isNetworkAvailable() -> Bool {
        
//        let reachability = try? Reachability(hostname: "www.apple.com")
//        self.reachability = reachability
        
        guard let reachability = reachability else {
            return false
        }
        return reachability.isReachable
    }
    
    func syncOfflineDat() {
        if isNetworkAvailable() {
            BeaconOfflineHandle.triggerSavedEvents()
        }
    }

}
