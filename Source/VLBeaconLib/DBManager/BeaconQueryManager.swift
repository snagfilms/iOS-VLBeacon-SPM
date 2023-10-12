//
//  BeaconQueryManager.swift
//  VLBeacon
//
//  Created by NEXGEN on 29/03/23.
//

import Foundation

internal class BeaconQueryManager {
    
    static let sharedInstance : BeaconQueryManager = {
        let instance = BeaconQueryManager()
        return instance
    }()
    
    private init() {
        dbManagerObj = BeaconDBManager()
        beaconDBConstants = BeaconDBConstants()
        createDBForBeaconEvents()
    }
    
    private var dbManagerObj: BeaconDBManager
    private var beaconDBConstants: BeaconDBConstants
    
    private func createDBForBeaconEvents() {
        
        dbManagerObj.intializeData(dbFilename: beaconDBConstants.DBNAME, tableName: beaconDBConstants.USERTABLENAME, tableColumnsQuery: beaconDBConstants.USER_TABLE_COLUMNS_QUERY )
        
        dbManagerObj.intializeData(dbFilename: beaconDBConstants.DBNAME, tableName: beaconDBConstants.PLAYERTABLENAME, tableColumnsQuery: beaconDBConstants.PLAYER_TABLE_COLUMNS_QUERY )
    }
    
    private func removeEmptyAndNilValues(from dictionary: inout [String: Any]) {
        dictionary = dictionary.filter { key, value in
            if let value = value as? String {
                return !value.isEmpty
            }
            return true
        }
    }
    
    func fetchTheUnsyncronisedBeaconEvents(_ beaconType: BeaconType) -> Array<Dictionary<String,Any>>? {
        
        let queryToLoadAllData: String?
        
        switch beaconType{
        case .user:
            queryToLoadAllData = "select * from \(beaconDBConstants.USERTABLENAME)"
            
        case .player:
            queryToLoadAllData = "select * from \(beaconDBConstants.PLAYERTABLENAME)"
        }
        
        guard let queryToLoadAllData else{ return nil }
        
        let customBeaconData = dbManagerObj.loadData(fromDB: queryToLoadAllData)
        
        let transformedData = customBeaconData.map { dictionaryData -> [String: Any] in
            var dataMap = dictionaryData as [String: Any]

            if let customData = dictionaryData[additionalData]?.data(using: .utf8),
               let decodedDict = try? JSONDecoder().decode(AnyDecodable.self, from: customData).value as? [String: Any] {
                dataMap[additionalData] = decodedDict
            }
            dataMap.removeValue(forKey: additionalData)
            
            if let data = dictionaryData[eventData]?.data(using: .utf8),
               let decodedData = try? JSONDecoder().decode(AnyDecodable.self, from: data).value as? [String: Any] {
                dataMap[eventData] = decodedData
            }
            
            removeEmptyAndNilValues(from: &dataMap)
            
            return dataMap
        }
        
//        print("in fetchTheUnsyncronisedBeaconEvents: \(transformedData)")
        return transformedData
    }
    
    func addBeaconEventInDB(_ beaconEvent: BeaconEventBodyProtocol) {
        
        guard let queryToAddBeaconEvent = beaconEvent.addBeaconInDBQuery() else { return }
//        print("in addBeaconEventInDB: \(queryToAddBeaconEvent)")
        dbManagerObj.execute(queryToAddBeaconEvent)
    }
    
    //MARK:- Generate Query to remove data from sqlite
    func removeBeaconEventFromTheBeaconDB(_ beaconType: BeaconType) {
        
        Log.shared.d("DB: Deleting \(beaconType) Table")
        let queryToRemoveBeaconEvent: String?
        
        switch beaconType{
        case .user:
            queryToRemoveBeaconEvent = "delete from \(beaconDBConstants.USERTABLENAME)"
        case .player:
            queryToRemoveBeaconEvent = "delete from \(beaconDBConstants.PLAYERTABLENAME)"
        }
        
        guard let queryToRemoveBeaconEvent else{ return }
        
        dbManagerObj.execute(queryToRemoveBeaconEvent)
    }

}
