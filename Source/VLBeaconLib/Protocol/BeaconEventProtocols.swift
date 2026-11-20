//
//  BeaconEventProtocols.swift
//  VLBeacon
//
//  Created by NEXGEN on 01/04/23.
//

import Foundation

public protocol BeaconEventNameProtocol {
    func getBeaconEventNameString() -> String
}

public protocol StructToDictionaryProtocol {
    func toDictionary() -> Dictionary<String, Any>
}

extension StructToDictionaryProtocol {

    //returns a Dictionary of Struct
    public func toDictionary() -> Dictionary<String, Any> {
        let mirror = Mirror(reflecting: self)
        var dict = [String: Any]()
        for case let (label?, value) in mirror.children {
            guard let unwrapped = unwrapMirrorValue(value) else { continue }

            if let stringValue = unwrapped as? String {
                if stringValue != "nil" {
                    dict[label] = stringValue
                }
            } else if let boolValue = unwrapped as? Bool {
                dict[label] = boolValue
            } else if let intValue = unwrapped as? Int {
                dict[label] = intValue
            } else if let dictValue = unwrapped as? [String: Any] {
                dict[label] = dictValue
            } else if let arrayDict = unwrapped as? [[String: String]] {
                dict[label] = arrayDict
            } else if let arrayString = unwrapped as? [String] {
                dict[label] = arrayString
            } else if let arrayStruct = unwrapped as? [StructToDictionaryProtocol] {
                dict[label] = arrayStruct.map { $0.toDictionary() }
            }
        }
        return dict
    }

    /// Unwraps Optional values so fields like `error_message` / `error_code` serialize reliably.
    private func unwrapMirrorValue(_ value: Any) -> Any? {
        let mirror = Mirror(reflecting: value)
        guard mirror.displayStyle == .optional else { return value }
        guard let child = mirror.children.first else { return nil }
        return unwrapMirrorValue(child.value)
    }
}

public protocol BeaconDBQueryProtocol {
    func addBeaconInDBQuery() -> String?
}

public protocol BeaconEventPayloadProtocol: StructToDictionaryProtocol {}


public protocol BeaconEventBodyProtocol: StructToDictionaryProtocol, BeaconDBQueryProtocol {
    func triggerEvents(authToken: String, beaconInstance: VLBeacon)
}
