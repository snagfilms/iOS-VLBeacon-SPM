//
//  VLEventDataValidator.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//


//
//  VLEventDataValidator.swift
//  VLBeacon
//
//  Event data validator with security and performance checks
//

import Foundation

/// Default implementation of event data validator
public final class VLEventDataValidator: EventDataValidator {
    
    // MARK: - Configuration
    
    /// Maximum size of the entire userInfo payload (4KB limit similar to push notifications)
    private let maxPayloadSize: Int
    
    /// Maximum string length to prevent memory issues
    private let maxStringLength: Int
    
    /// Maximum nesting depth for dictionaries
    private let maxNestingDepth: Int
    
    /// Maximum number of keys in a dictionary
    private let maxKeyCount: Int
    
    /// Allowed value types for notification userInfo
    private let allowedTypes: [Any.Type] = [
        String.self,
        Int.self,
        Double.self,
        Float.self,
        Bool.self,
        Date.self,
        Data.self,
        URL.self,
        NSNumber.self,
        NSString.self,
        NSDate.self,
        NSData.self,
        NSURL.self,
        [String: Any].self,
        [Any].self
    ]
    
    // MARK: - Initialization
    
    public init(
        maxPayloadSize: Int = 4096,
        maxStringLength: Int = 1000,
        maxNestingDepth: Int = 3,
        maxKeyCount: Int = 50
    ) {
        self.maxPayloadSize = maxPayloadSize
        self.maxStringLength = maxStringLength
        self.maxNestingDepth = maxNestingDepth
        self.maxKeyCount = maxKeyCount
    }
    
    // MARK: - EventDataValidator Protocol
    
    public func validate(_ data: [String: Any]) -> Bool {
        // Check if data is empty
        if data.isEmpty {
            return true
        }
        
        // Validate key count
        guard data.count <= maxKeyCount else {
            debugPrint("❌ Validation failed: Too many keys (\(data.count) > \(maxKeyCount))")
            return false
        }
        
        // Validate payload size
        guard estimatedSize(of: data) <= maxPayloadSize else {
            debugPrint("❌ Validation failed: Payload too large (> \(maxPayloadSize) bytes)")
            return false
        }
        
        // Validate nesting depth
        guard checkNestingDepth(data, currentDepth: 0) else {
            debugPrint("❌ Validation failed: Nesting too deep (> \(maxNestingDepth))")
            return false
        }
        
        // Validate keys
        for key in data.keys {
            guard isValidKey(key) else {
                debugPrint("❌ Validation failed: Invalid key '\(key)'")
                return false
            }
        }
        
        // Validate values
        for (key, value) in data {
            guard isValidValue(value) else {
                debugPrint("❌ Validation failed: Invalid value type for key '\(key)'")
                return false
            }
        }
        
        return true
    }
    
    public func sanitize(_ data: [String: Any]) -> [String: Any] {
        var sanitized: [String: Any] = [:]
        
        for (key, value) in data {
            // Sanitize key
            let sanitizedKey = sanitizeKey(key)
            
            // Skip if key becomes invalid after sanitization
            guard !sanitizedKey.isEmpty else {
                continue
            }
            
            // Sanitize value
            if let sanitizedValue = sanitizeValue(value) {
                sanitized[sanitizedKey] = sanitizedValue
            }
        }
        
        return sanitized
    }
    
    // MARK: - Private Validation Methods
    
    /// Check if key is valid
    private func isValidKey(_ key: String) -> Bool {
        // Key must not be empty
        guard !key.isEmpty else { return false }
        
        // Key must not be too long
        guard key.count <= 100 else { return false }
        
        // Key should only contain alphanumeric characters, underscores, and dots
        let allowedCharacters = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_."))
        guard key.unicodeScalars.allSatisfy({ allowedCharacters.contains($0) }) else {
            return false
        }
        
        return true
    }
    
    /// Check if value type is allowed
    private func isValidValue(_ value: Any) -> Bool {
        // Check if type is in allowed list
        for allowedType in allowedTypes {
            if type(of: value) == allowedType {
                return true
            }
        }
        
        // Special handling for nested dictionaries
        if let dict = value as? [String: Any] {
            return dict.allSatisfy { isValidKey($0.key) && isValidValue($0.value) }
        }
        
        // Special handling for arrays
        if let array = value as? [Any] {
            return array.allSatisfy { isValidValue($0) }
        }
        
        return false
    }
    
    /// Check nesting depth of dictionaries
    private func checkNestingDepth(_ data: [String: Any], currentDepth: Int) -> Bool {
        guard currentDepth < maxNestingDepth else {
            return false
        }
        
        for value in data.values {
            if let nestedDict = value as? [String: Any] {
                guard checkNestingDepth(nestedDict, currentDepth: currentDepth + 1) else {
                    return false
                }
            } else if let array = value as? [Any] {
                for item in array {
                    if let nestedDict = item as? [String: Any] {
                        guard checkNestingDepth(nestedDict, currentDepth: currentDepth + 1) else {
                            return false
                        }
                    }
                }
            }
        }
        
        return true
    }
    
    /// Estimate size of dictionary in bytes
    private func estimatedSize(of data: [String: Any]) -> Int {
        var size = 0
        
        for (key, value) in data {
            // Add key size
            size += key.utf8.count
            
            // Add value size
            size += estimatedValueSize(value)
        }
        
        return size
    }
    
    /// Estimate size of a value
    private func estimatedValueSize(_ value: Any) -> Int {
        switch value {
        case let string as String:
            return string.utf8.count
        case let nsString as NSString:
            return nsString.length
        case let data as Data:
            return data.count
        case let nsData as NSData:
            return nsData.length
        case let dict as [String: Any]:
            return estimatedSize(of: dict)
        case let array as [Any]:
            return array.reduce(0) { $0 + estimatedValueSize($1) }
        case is Int, is Double, is Float, is Bool:
            return 8  // Approximate size for numeric types
        case let date as Date:
            return 8  // Timestamp
        case let url as URL:
            return url.absoluteString.utf8.count
        default:
            return 0
        }
    }
    
    // MARK: - Private Sanitization Methods
    
    /// Sanitize a key string
    private func sanitizeKey(_ key: String) -> String {
        // Trim whitespace
        var sanitized = key.trimmingCharacters(in: .whitespacesAndNewlines)
        
        // Remove invalid characters
        let allowedCharacters = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_."))
        sanitized = sanitized.unicodeScalars
            .filter { allowedCharacters.contains($0) }
            .map { String($0) }
            .joined()
        
        // Limit length
        if sanitized.count > 100 {
            sanitized = String(sanitized.prefix(100))
        }
        
        return sanitized
    }
    
    /// Sanitize a value
    private func sanitizeValue(_ value: Any) -> Any? {
        switch value {
        case let string as String:
            return sanitizeString(string)
            
        case let nsString as NSString:
            return sanitizeString(nsString as String)
            
        case let dict as [String: Any]:
            return sanitize(dict)
            
        case let array as [Any]:
            return array.compactMap { sanitizeValue($0) }
            
        case let data as Data:
            // Limit data size
            if data.count > maxPayloadSize / 4 {
                return data.prefix(maxPayloadSize / 4)
            }
            return data
            
        case let url as URL:
            return url
            
        case let date as Date:
            return date
            
        case let number as NSNumber:
            return number
            
        case let int as Int:
            return int
            
        case let double as Double:
            return double.isFinite ? double : nil
            
        case let float as Float:
            return float.isFinite ? float : nil
            
        case let bool as Bool:
            return bool
            
        default:
            // Remove unsupported types
            debugPrint("⚠️ Unsupported type removed during sanitization: \(type(of: value))")
            return nil
        }
    }
    
    /// Sanitize string values
    private func sanitizeString(_ string: String) -> String {
        var sanitized = string
        
        // Trim whitespace from ends
        sanitized = sanitized.trimmingCharacters(in: .whitespacesAndNewlines)
        
        // Remove null characters and control characters
        sanitized = sanitized.filter { character in
            let scalar = character.unicodeScalars.first!
            return !CharacterSet.controlCharacters.contains(scalar) || character == "\n" || character == "\t"
        }
        
        // Limit string length
        if sanitized.count > maxStringLength {
            sanitized = String(sanitized.prefix(maxStringLength))
        }
        
        // Remove any potential SQL injection or script injection patterns (basic protection)
        let dangerousPatterns = ["<script", "javascript:", "onerror=", "onclick=", "--", ";", "DROP ", "DELETE ", "INSERT "]
        for pattern in dangerousPatterns {
            sanitized = sanitized.replacingOccurrences(of: pattern, with: "", options: .caseInsensitive)
        }
        
        return sanitized
    }
}

// MARK: - Validation Extensions

extension VLEventDataValidator {
    
    /// Validate specific notification requirements for VLPlayer
    public func validatePlayerNotification(_ data: [String: Any], for notificationName: Notification.Name) -> Bool {
        // Perform basic validation first
        guard validate(data) else {
            return false
        }
        
        // Validate specific required keys based on notification type
        switch notificationName {
        case VLPlayerNotifications.sessionStart:
            return data.keys.contains(VLPlayerUserInfoKeys.analyticsContentInfo) &&
                   data.keys.contains(VLPlayerUserInfoKeys.analyticsPlayerInfo)
            
        case VLPlayerNotifications.chapterStart:
            return data.keys.contains(VLPlayerUserInfoKeys.currentTime) &&
                   data.keys.contains(VLPlayerUserInfoKeys.endTime)
            
        case VLPlayerNotifications.seekComplete:
            return data.keys.contains(VLPlayerUserInfoKeys.newTime) &&
                   data.keys.contains(VLPlayerUserInfoKeys.shouldResume)
            
        case VLPlayerNotifications.error:
            return data.keys.contains(VLPlayerUserInfoKeys.errorMessage)
            
        default:
            return true
        }
    }
}
