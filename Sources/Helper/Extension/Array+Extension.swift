//
//  Array+Extension.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 22/06/23.
//

import Foundation

extension Array{
    
    func jsonString() -> String? {
        let object = self
        
        guard JSONSerialization.isValidJSONObject(object) else {
            return nil
        }
        
        do {
            let encodedData = try JSONSerialization.data(withJSONObject: object)
            return String(data: encodedData, encoding: .utf8)
        } catch {
//            print("Error in converting object to JSON string: \(error)")
            return nil
        }
    }
}

