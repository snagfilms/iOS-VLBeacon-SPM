//
//  File.swift
//  
//
//  Created by Ratnakar Gautam on 15/01/25.
//

import Foundation
import UIKit

class BeaconOfflineHandle {
    private static let fileAccessQueue = DispatchQueue(label: "com.beaconOfflineHandle.fileAccessQueue")
    
    private static var beaconFilePath: URL? {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first?.appendingPathComponent("beacon_events.plist")
    }

    static func saveDataToLocal(newDict: [String: Any]) {
        fileAccessQueue.sync {
            do {
                var existingData = try readPlistData()
                existingData.append(newDict)
                try writePlistData(existingData)
                print("Data saved successfully")
            } catch {
                print("Error saving data: \(error)")
            }
        }
    }

    static func fetchLocalData() -> [[String: Any]]? {
        return fileAccessQueue.sync {
            do {
                return try readPlistData()
            } catch {
                print("Error fetching data: \(error)")
                return nil
            }
        }
    }

    static func deleteDictionaryAt(index: Int) {
        fileAccessQueue.sync {
            do {
                var existingData = try readPlistData()
                guard index < existingData.count else { return }
                existingData.remove(at: index)
                try writePlistData(existingData)
                print("Dictionary deleted successfully")
            } catch {
                print("Error deleting data: \(error)")
            }
        }
    }

    static func triggerSavedEvents() {
        fileAccessQueue.sync {
            guard let authToken = VLBeacon.getInstance().authorizationToken else { return }
            let beaconInstance = VLBeacon.getInstance()

            do {
                var savedEvents = try readPlistData()
                var successfullyTriggeredIndices: [Int] = []

                // Aggregate events by type
                var userEvents: [[String: Any]] = []
                var playerEvents: [[String: Any]] = []

                for (index, tempDict) in savedEvents.enumerated() {
                    var eventDict = tempDict
                    guard let eventTypeString = eventDict["eventType"] as? String,
                          let eventType = BeaconType(rawValue: eventTypeString.capitalized) else {
                        continue
                    }

                    eventDict.removeValue(forKey: "eventType")

                    // Process event dictionary
                    processEventDict(&eventDict, beaconInstance: beaconInstance)

                    // Append to appropriate event type array
                    switch eventType {
                    case .user:
                        userEvents.append(eventDict)
                    case .player:
                        playerEvents.append(eventDict)
                    }

                    // Mark the index for successful processing
                    successfullyTriggeredIndices.append(index)
                }

                // Trigger events for each type
                triggerEvents(userEvents, beaconInstance: beaconInstance, authToken: authToken, beaconType: .user)
                triggerEvents(playerEvents, beaconInstance: beaconInstance, authToken: authToken, beaconType: .player)

                // Remove successfully triggered events from saved data
                removeProcessedEvents(&savedEvents, successfullyTriggeredIndices)
                try writePlistData(savedEvents)
            } catch {
                print("Error triggering saved events: $error)")
            }
        }
    }

    // Helper function to process event dictionary
    private static func processEventDict(_ eventDict: inout [String: Any], beaconInstance: VLBeacon) {
        guard let uID = beaconInstance.tokenIdentity?.userId as? String else { return }
        let anonymousId = beaconInstance.tokenIdentity?.anonymousId as? String
        
        eventDict["aid"] = beaconInstance.tokenIdentity?.siteName ?? ""
        eventDict["cid"] = beaconInstance.tokenIdentity?.siteId ?? ""

        if let anonymousId = anonymousId, !anonymousId.isEmpty {
            if eventDict["profid"] == nil || (eventDict["profid"] as? String ?? "").isEmpty {
                eventDict["profid"] = "guest-user"
            }
            if eventDict["uid"] == nil || (eventDict["uid"] as? String ?? "").isEmpty {
                eventDict["uid"] = UIDevice.current.identifierForVendor?.uuidString ?? ""
            }
            if eventDict["anonymousuid"] == nil || (eventDict["anonymousuid"] as? String ?? "").isEmpty {
                eventDict["anonymousuid"] = anonymousId
            }
        } else {
            if eventDict["uid"] == nil || (eventDict["uid"] as? String ?? "").isEmpty {
                eventDict["uid"] = uID
            }
        }
    }

    // Helper function to trigger events
    private static func triggerEvents(_ events: [[String: Any]], beaconInstance: VLBeacon, authToken: String, beaconType: BeaconType) {
        if !events.isEmpty {
            BeaconSyncManager.sharedInstance.postDataToServer(
                vlBeacon: beaconInstance,
                arrayOfBeaconEvents: events,
                authenticationToken: authToken,
                beaconType: beaconType
            )
        }
    }

    // Helper function to remove processed events
    private static func removeProcessedEvents(_ savedEvents: inout [[String: Any]], _ successfullyTriggeredIndices: [Int]) {
        if !successfullyTriggeredIndices.isEmpty {
            for index in successfullyTriggeredIndices.sorted(by: >) {
                savedEvents.remove(at: index)
            }
        }
    }

    private static func readPlistData() throws -> [[String: Any]] {
        guard let filePath = beaconFilePath else { return [] }
        
        // Check if the file exists
        if !FileManager.default.fileExists(atPath: filePath.path) {
            // Create an empty file if it doesn't exist
            try writePlistData([])
        }
        
        let data = try Data(contentsOf: filePath)
        return try PropertyListSerialization.propertyList(from: data, options: [], format: nil) as? [[String: Any]] ?? []
    }

    private static func writePlistData(_ data: [[String: Any]]) throws {
        guard let filePath = beaconFilePath else { return }
        
        // Serialize the data and write to the file
        let plistData = try PropertyListSerialization.data(fromPropertyList: data, format: .xml, options: 0)
        try plistData.write(to: filePath)
    }
}

