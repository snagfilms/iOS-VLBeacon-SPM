// The Swift Programming Language
// https://docs.swift.org/swift-book

import Foundation


final public class VLBeacon {
    private static let sharedInstance = VLBeacon()
    
    public class func getInstance()-> VLBeacon {
        return sharedInstance
    }
    
    private init() {
        print("VLBeacon init")
    }
    
    private let bundleIdentifier = "com.viewlift.beacon"
    
    public var tokenIdentity: TokenIdentity?
    
    internal var beaconBaseUrl : String?
    
    public var tveProvider: String?
    
    public var environment: String = ""
    
    public var authorizationToken : String? {
        didSet {
            guard let authorizationToken else { return }
            self.tokenIdentity = JWTTokenParser().jwtTokenParser(jwtToken: authorizationToken)
        }
    }
    
    public var debugLogs: Bool? = false {
        didSet{
            guard let debugLogs else { return }
            Log.shared.isLoggingEnabled = debugLogs
            if debugLogs{
                Log.shared.d("VLBeacon debug logs enabled!")
                Log.shared.d("Beacon events pointing to \(String(describing: beaconBaseUrl))")
            }
            
        }
    }
    
    
    public var disabledTracking: Bool = false
    

    public func startSyncBeaconEvents() {
        self.setupConfiguration()
        
        let sharedSyncManager = BeaconSyncManager.sharedInstance
        
        if NetworkStatus.sharedInstance.isNetworkAvailable() && !disabledTracking {
            if let authToken = authorizationToken {
                sharedSyncManager.startSyncingTheEvents(vlBeacon: self, authenticationToken: authToken, withSuccess: {(_ success: Bool) -> Void in
                })
            }
        }
    }
    
    public func triggerBeaconEvent(_ eventStructBody: BeaconEventBodyProtocol) {
        guard let authToken = self.authorizationToken, !disabledTracking else { return }
        
        guard let uID = tokenIdentity?.userId as? String else { return }
        let anonymousId = tokenIdentity?.anonymousId as? String
        let deviceid = eventStructBody.toDictionary()["deviceid"] as? String
        
        if var event = eventStructBody as? PlayerBeaconEventStruct {
            if (anonymousId ?? "").isEmpty == false {
                event.profid = "guest-user"
                event.uid = deviceid
            } else {
                event.profid = uID
            }
            event.environment = environment
            
            event.tveProvider = tveProvider
            event.triggerEvents(authToken: authToken, beaconInstance: self)
        } else if var eventUser = eventStructBody as? UserBeaconEventStruct {
            if (anonymousId ?? "").isEmpty == false {
                eventUser.profid = "guest-user"
                eventUser.uid = deviceid
            } else {
                eventUser.profid = uID
            }
            
            eventUser.environment = environment
            eventUser.triggerEvents(authToken: authToken, beaconInstance: self)
        }
    }
    
}

extension VLBeacon{
    
    func getBeaconBaseUrl() -> String? {
        guard let bundlePath = Bundle.main.path(forResource: "SiteConfig", ofType: "plist"),
              let dict = NSDictionary.init(contentsOfFile: bundlePath),
              let apiEndpoint = dict["BeaconApiUrl"] as? String else { return nil }
        return apiEndpoint
    }
    
    private func getDebugLogger() -> Bool? {
        guard let bundlePath = Bundle.main.path(forResource: "SiteConfig", ofType: "plist"),
              let dict = NSDictionary.init(contentsOfFile: bundlePath),
              let loggerValue = dict["VLBeaconDebugLogger"] as? Bool else {return false}
        return loggerValue
    }
    
    private func setupConfiguration() {
        beaconBaseUrl = getBeaconBaseUrl()
        environment = getEnvironment()
        debugLogs = getDebugLogger()
    }
    
    
    func getEnvironment() -> String {
        guard let bundlePath = Bundle.main.path(forResource: "SiteConfig", ofType: "plist"),
              let dict = NSDictionary.init(contentsOfFile: bundlePath),
              let environment = dict["Env"] as? String else { return "" }
        
        switch environment.lowercased() {
        case "prod":
            return "production"
        case "develop":
            return "develop"
        case "stage":
            return "stage"
        case "uat":
            return "uat"
        case "qa":
            return "qa"
        default:
            return ""
        }
    }
    
}
