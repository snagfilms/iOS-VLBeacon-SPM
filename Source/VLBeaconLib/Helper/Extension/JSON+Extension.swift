//
//  JSON+Extension.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 21/06/23.
//
//import Foundation
//
//struct JSONCodingKeys: CodingKey {
//    var stringValue: String
//
//    init?(stringValue: String) {
//        self.stringValue = stringValue
//    }
//
//    var intValue: Int?
//
//    init?(intValue: Int) {
//        self.init(stringValue: "\(intValue)")
//        self.intValue = intValue
//    }
//}
//
//
//extension KeyedDecodingContainer {
//
//    func decode(_ type: Dictionary<String, Any>.Type, forKey key: K) throws -> Dictionary<String, Any> {
//        let container = try self.nestedContainer(keyedBy: JSONCodingKeys.self, forKey: key)
//        return try container.decode(type)
//    }
//
//    func decodeIfPresent(_ type: Dictionary<String, Any>.Type, forKey key: K) throws -> Dictionary<String, Any>? {
//        guard contains(key) else {
//            return nil
//        }
//        guard try decodeNil(forKey: key) == false else {
//            return nil
//        }
//        return try decode(type, forKey: key)
//    }
//
//    func decode(_ type: Array<Any>.Type, forKey key: K) throws -> Array<Any> {
//        var container = try self.nestedUnkeyedContainer(forKey: key)
//        return try container.decode(type)
//    }
//
//    func decodeIfPresent(_ type: Array<Any>.Type, forKey key: K) throws -> Array<Any>? {
//        guard contains(key) else {
//            return nil
//        }
//        guard try decodeNil(forKey: key) == false else {
//            return nil
//        }
//        return try decode(type, forKey: key)
//    }
//
//    func decode(_ type: Dictionary<String, Any>.Type) throws -> Dictionary<String, Any> {
//        var dictionary = Dictionary<String, Any>()
//
//        for key in allKeys {
//            if let boolValue = try? decode(Bool.self, forKey: key) {
//                dictionary[key.stringValue] = boolValue
//            } else if let stringValue = try? decode(String.self, forKey: key) {
//                dictionary[key.stringValue] = stringValue
//            } else if let intValue = try? decode(Int.self, forKey: key) {
//                dictionary[key.stringValue] = intValue
//            } else if let doubleValue = try? decode(Double.self, forKey: key) {
//                dictionary[key.stringValue] = doubleValue
//            } else if let nestedDictionary = try? decode(Dictionary<String, Any>.self, forKey: key) {
//                dictionary[key.stringValue] = nestedDictionary
//            } else if let nestedArray = try? decode(Array<Any>.self, forKey: key) {
//                dictionary[key.stringValue] = nestedArray
//            }
//        }
//        return dictionary
//    }
//}
//
//extension UnkeyedDecodingContainer {
//
//    mutating func decode(_ type: Array<Any>.Type) throws -> Array<Any> {
//        var array: [Any] = []
//        while isAtEnd == false {
//            // See if the current value in the JSON array is `null` first and prevent infite recursion with nested arrays.
//            if try decodeNil() {
//                continue
//            } else if let value = try? decode(Bool.self) {
//                array.append(value)
//            } else if let value = try? decode(Double.self) {
//                array.append(value)
//            } else if let value = try? decode(String.self) {
//                array.append(value)
//            } else if let nestedDictionary = try? decode(Dictionary<String, Any>.self) {
//                array.append(nestedDictionary)
//            } else if let nestedArray = try? decode(Array<Any>.self) {
//                array.append(nestedArray)
//            }
//        }
//        return array
//    }
//
//    mutating func decode(_ type: Dictionary<String, Any>.Type) throws -> Dictionary<String, Any> {
//
//        let nestedContainer = try self.nestedContainer(keyedBy: JSONCodingKeys.self)
//        return try nestedContainer.decode(type)
//    }
//}


//import Foundation
//
//// Inspired by https://gist.github.com/mbuchetics/c9bc6c22033014aa0c550d3b4324411a
//
//struct JSONCodingKeys: CodingKey {
//    var stringValue: String
//
//    init?(stringValue: String) {
//        self.stringValue = stringValue
//    }
//
//    var intValue: Int?
//
//    init?(intValue: Int) {
//        self.init(stringValue: "\(intValue)")
//        self.intValue = intValue
//    }
//}
//
//
//extension KeyedDecodingContainer {
//
//    func decode(_ type: Dictionary<String, Any>.Type, forKey key: K) throws -> Dictionary<String, Any> {
//        let container = try self.nestedContainer(keyedBy: JSONCodingKeys.self, forKey: key)
//        return try container.decode(type)
//    }
//
//    func decodeIfPresent(_ type: Dictionary<String, Any>.Type, forKey key: K) throws -> Dictionary<String, Any>? {
//        guard contains(key) else {
//            return nil
//        }
//        return try decode(type, forKey: key)
//    }
//
//    func decode(_ type: Array<Any>.Type, forKey key: K) throws -> Array<Any> {
//        var container = try self.nestedUnkeyedContainer(forKey: key)
//        return try container.decode(type)
//    }
//
//    func decodeIfPresent(_ type: Array<Any>.Type, forKey key: K) throws -> Array<Any>? {
//        guard contains(key) else {
//            return nil
//        }
//        return try decode(type, forKey: key)
//    }
//
//    func decode(_ type: Dictionary<String, Any>.Type) throws -> Dictionary<String, Any> {
//        var dictionary = Dictionary<String, Any>()
//
//        for key in allKeys {
//            if let boolValue = try? decode(Bool.self, forKey: key) {
//                dictionary[key.stringValue] = boolValue
//            } else if let stringValue = try? decode(String.self, forKey: key) {
//                dictionary[key.stringValue] = stringValue
//            } else if let intValue = try? decode(Int.self, forKey: key) {
//                dictionary[key.stringValue] = intValue
//            } else if let doubleValue = try? decode(Double.self, forKey: key) {
//                dictionary[key.stringValue] = doubleValue
//            } else if let nestedDictionary = try? decode(Dictionary<String, Any>.self, forKey: key) {
//                dictionary[key.stringValue] = nestedDictionary
//            } else if let nestedArray = try? decode(Array<Any>.self, forKey: key) {
//                dictionary[key.stringValue] = nestedArray
//            }
////            else if let fileMetaData = try? decode(Asset.FileMetadata.self, forKey: key) {
////               dictionary[key.stringValue] = fileMetaData // Custom contentful type.
////           }
//        }
//        return dictionary
//    }
//}
//
//extension UnkeyedDecodingContainer {
//
//    mutating func decode(_ type: Array<Any>.Type) throws -> Array<Any> {
//        var array: [Any] = []
//        while isAtEnd == false {
//            if let value = try? decode(Bool.self) {
//                array.append(value)
//            } else if let value = try? decode(Double.self) {
//                array.append(value)
//            } else if let value = try? decode(String.self) {
//                array.append(value)
//            } else if let nestedDictionary = try? decode(Dictionary<String, Any>.self) {
//                array.append(nestedDictionary)
//            } else if let nestedArray = try? decode(Array<Any>.self) {
//                array.append(nestedArray)
//            }
//        }
//        return array
//    }
//
//    mutating func decode(_ type: Dictionary<String, Any>.Type) throws -> Dictionary<String, Any> {
//
//        let nestedContainer = try self.nestedContainer(keyedBy: JSONCodingKeys.self)
//        return try nestedContainer.decode(type)
//    }
//}


public struct AnyDecodable: Decodable {
  public var value: Any

  private struct CodingKeys: CodingKey {
    var stringValue: String
    var intValue: Int?
    init?(intValue: Int) {
      self.stringValue = "\(intValue)"
      self.intValue = intValue
    }
    init?(stringValue: String) { self.stringValue = stringValue }
  }

  public init(from decoder: Decoder) throws {
    if let container = try? decoder.container(keyedBy: CodingKeys.self) {
      var result = [String: Any]()
      try container.allKeys.forEach { (key) throws in
        result[key.stringValue] = try container.decode(AnyDecodable.self, forKey: key).value
      }
      value = result
    } else if var container = try? decoder.unkeyedContainer() {
      var result = [Any]()
      while !container.isAtEnd {
        result.append(try container.decode(AnyDecodable.self).value)
      }
      value = result
    } else if let container = try? decoder.singleValueContainer() {
      if let intVal = try? container.decode(Int.self) {
        value = intVal
      } else if let doubleVal = try? container.decode(Double.self) {
        value = doubleVal
      } else if let boolVal = try? container.decode(Bool.self) {
        value = boolVal
      } else if let stringVal = try? container.decode(String.self) {
        value = stringVal
      } else {
        throw DecodingError.dataCorruptedError(in: container, debugDescription: "the container contains nothing serialisable")
      }
    } else {
      throw DecodingError.dataCorrupted(DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Could not serialise"))
    }
  }
}

