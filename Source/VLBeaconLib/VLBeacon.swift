// The Swift Programming Language
// https://docs.swift.org/swift-book

import Foundation

final public class VLBeacon {
    private static let sharedInstance = VLBeacon()
    
    public class func getInstance()-> VLBeacon {
        return sharedInstance
    }
    
    private init() {
        debugPrint("VLBeacon init")
    }
    
    private let bundleIdentifier = "com.viewlift.beacon"
    
    private var _tokenIdentity: TokenIdentity?
    public var tokenIdentity: TokenIdentity? {
        get { tokenQueue.sync { _tokenIdentity } }
        set { tokenQueue.sync { _tokenIdentity = newValue } }
    }
    
    internal var userBeaconUrl : String?
    internal var playerBeaconUrl : String?
    
    public var tveProvider: String?
    public var mvpdProvider: String?
    
    public var environment: String = ""
    private var isOfflineEventsSynced = false
    
    private let tokenQueue = DispatchQueue(label: "com.viewlift.beacon.tokenQueue")
    
    private var _authorizationToken: String?
    
    public var authorizationToken: String? {
        get {
            var result: String?
            tokenQueue.sync {
                result = _authorizationToken
            }
            return result
        }
        set {
            // Synchronous so tokenIdentity is ready before immediate submitUserBeaconEvent calls.
            // Write _tokenIdentity directly (already on tokenQueue) to avoid nested sync deadlocks.
            tokenQueue.sync {
                self._authorizationToken = newValue
                guard let authorizationToken = newValue else {
                    self._tokenIdentity = nil
                    return
                }
                self._tokenIdentity = JWTTokenParser().jwtTokenParser(jwtToken: authorizationToken)
            }
        }
    }
    
    public var debugLogs: Bool? = false {
        didSet {
            guard let debugLogs else { return }
            
            Log.shared.isLoggingEnabled = debugLogs
            
            if debugLogs {
                Log.shared.d("VLBeacon debug logs enabled!")
                Log.shared.d("User Beacon events pointing to \(String(describing: userBeaconUrl))")
                Log.shared.d("Player Beacon events pointing to \(String(describing: playerBeaconUrl))")
            }
        }
    }
}

// MARK: - Public methods
public extension VLBeacon {
    func startSyncBeaconEvents(userBeaconUrl: String?, playerBeaconUrl: String?) {
        self.setupConfiguration(userBeaconUrl: userBeaconUrl, playerBeaconUrl: playerBeaconUrl)
        
        let sharedSyncManager = BeaconSyncManager.sharedInstance
        
        guard NetworkStatus.sharedInstance.isNetworkAvailable() else { return }
        guard let authToken = authorizationToken else { return }
        
        sharedSyncManager.startSyncingTheEvents(vlBeacon: self,
                                                authenticationToken: authToken,
                                                withSuccess: {(_ success: Bool) -> Void in })
    }
    
    func updatePlayerBeaconEndpoint(_ playerEndpoint: String) {
        guard playerBeaconUrl == nil, (playerBeaconUrl?.isEmpty ?? true), !playerEndpoint.isEmpty else { return }
        
        playerBeaconUrl = playerEndpoint
        environment = getEnvironment()
    }
    
    func updateUserBeaconEndpoint(_ userEndpoint: String) {
        guard userBeaconUrl == nil, (userBeaconUrl?.isEmpty ?? true), !userEndpoint.isEmpty else { return }
        
        userBeaconUrl = userEndpoint
        environment = getEnvironment()
    }
    
    // Concrete overloads (no `BeaconEventBodyProtocol` existential involved) — calling
    // `.toDictionary()` / `.triggerEvents(...)` on a value whose static type is known
    // avoids boxing the (large) struct into a protocol existential. Boxing these structs
    // — even entirely *within* VLBeaconLib itself, not just across the AppCMS boundary —
    // has been observed to cause `EXC_BAD_ACCESS` (null witness/metadata) while VLBeaconLib
    // is linked as a dynamic framework. Prefer these overloads; the protocol-typed
    // overload below only exists for source compatibility with not-yet-updated callers.
    func triggerBeaconEvent(_ event: PlayerBeaconEventStruct, userMergedForAnonymousId: String? = nil) {
        var event = event
        let deviceid = event.toDictionary()["deviceid"] as? String

        prepareForOfflineSyncIfNeeded()
        let isNetworkAvailable = NetworkStatus.sharedInstance.isNetworkAvailable()
        let uID = tokenIdentity?.userId as? String ?? ""
        let anonymousId = tokenIdentity?.anonymousId as? String ?? ""

        if (anonymousId ?? "").isEmpty == false {
            event.profid = "guest-user"
            event.uid = deviceid
            event.anonymousuid = anonymousId
        } else {
            event.profid = uID
        }
        if let userMergedForAnonymousId {
            event.anonymousuid = userMergedForAnonymousId
        }
        event.environment = environment
        if let _ = mvpdProvider {
            event.tveProvider = tveProvider
        }
        event.mvpdprovider = mvpdProvider
        event.eventType = "Player Beacon"

        debugPrint("Event Player: ", event.toDictionary())

        if !isNetworkAvailable {
            BeaconOfflineHandle.saveDataToLocal(newDict: event.toDictionary())
        }

        if let authToken = self.authorizationToken {
            event.triggerEvents(authToken: authToken, beaconInstance: self)
        } else {
            // Token not ready yet — save locally, will sync when token arrives
            BeaconOfflineHandle.saveDataToLocal(newDict: event.toDictionary())
        }
    }

    func triggerBeaconEvent(_ event: UserBeaconEventStruct, userMergedForAnonymousId: String? = nil) {
        var eventUser = event
        let deviceid = eventUser.toDictionary()["deviceid"] as? String

        prepareForOfflineSyncIfNeeded()
        let isNetworkAvailable = NetworkStatus.sharedInstance.isNetworkAvailable()
        let uID = tokenIdentity?.userId as? String ?? ""
        let anonymousId = tokenIdentity?.anonymousId as? String ?? ""

        if (anonymousId ?? "").isEmpty == false {
            eventUser.profid = "guest-user"
            eventUser.uid = deviceid
            eventUser.anonymousuid = anonymousId
        } else {
            eventUser.profid = uID
        }
        if let userMergedForAnonymousId {
            eventUser.anonymousuid = userMergedForAnonymousId
        }
        eventUser.environment = environment
        eventUser.eventType = "User Beacon"

        debugPrint("Event User: ", eventUser.toDictionary())

        if !isNetworkAvailable {
            BeaconOfflineHandle.saveDataToLocal(newDict: eventUser.toDictionary())
        }

        if let authToken = self.authorizationToken {
            eventUser.triggerEvents(authToken: authToken, beaconInstance: self)
        } else {
            // Token not ready yet — save locally, will sync when token arrives
            BeaconOfflineHandle.saveDataToLocal(newDict: eventUser.toDictionary())
        }
    }

    // Compatibility shim for external callers (e.g. VLStoreKit) built against an older
    // VLBeaconLib API. Once such callers are rebuilt against this version, Swift's overload
    // resolution automatically prefers the concrete overloads above at their call sites
    // (since they already hold a concretely-typed `PlayerBeaconEventStruct` /
    // `UserBeaconEventStruct`), so this path should no longer be hit in practice.
    @available(*, deprecated, message: "Pass a concrete PlayerBeaconEventStruct or UserBeaconEventStruct to avoid boxing it into a BeaconEventBodyProtocol existential.")
    func triggerBeaconEvent(_ eventStructBody: BeaconEventBodyProtocol, userMergedForAnonymousId: String? = nil) {
        if let event = eventStructBody as? PlayerBeaconEventStruct {
            triggerBeaconEvent(event, userMergedForAnonymousId: userMergedForAnonymousId)
        } else if let eventUser = eventStructBody as? UserBeaconEventStruct {
            triggerBeaconEvent(eventUser, userMergedForAnonymousId: userMergedForAnonymousId)
        }
    }
}

// MARK: - Private methods
private extension VLBeacon {
    func prepareForOfflineSyncIfNeeded() {
        guard !isOfflineEventsSynced else { return }
        isOfflineEventsSynced = true
        NetworkStatus.sharedInstance.syncOfflineDat()
    }

    func getDebugLogger() -> Bool? {
        guard let bundlePath = Bundle.main.path(forResource: "SiteConfig", ofType: "plist"),
              let dict = NSDictionary.init(contentsOfFile: bundlePath),
              let loggerValue = dict["VLBeaconDebugLogger"] as? Bool else {return false}
        return loggerValue
    }
    
    func setupConfiguration(userBeaconUrl: String?, playerBeaconUrl: String?) {
        self.userBeaconUrl = userBeaconUrl
        self.playerBeaconUrl = playerBeaconUrl
        
        environment = getEnvironment()
        debugLogs = getDebugLogger()
    }
    
    func getEnvironment() -> String {
        guard let bundlePath = Bundle.main.path(forResource: "SiteConfig", ofType: "plist"),
              let dict = NSDictionary.init(contentsOfFile: bundlePath),
              let environment = dict["Env"] as? String else { return "production" }
        
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
            return "production"
        }
    }
}
