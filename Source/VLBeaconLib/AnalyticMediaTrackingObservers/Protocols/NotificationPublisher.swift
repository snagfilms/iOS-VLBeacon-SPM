//
//  NotificationPublisher.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//

import Foundation

// MARK: - Notification Publisher Protocol

/// Protocol for objects that publish notifications
public protocol NotificationPublisher: AnyObject {
    /// Post notification synchronously
    func post(name: Notification.Name, userInfo: [String: Any]?, object: Any?)
    
    /// Post notification asynchronously
    func postAsync(name: Notification.Name, userInfo: [String: Any]?, object: Any?)
}

// MARK: - Notification Subscriber Protocol

/// Protocol for objects that subscribe to notifications
public protocol NotificationSubscriber: AnyObject {
    /// Add observer for a specific notification
    @discardableResult
    func addObserver(
        for name: Notification.Name,
        object: Any?,
        queue: OperationQueue?,
        using block: @escaping (Notification) -> Void
    ) -> NSObjectProtocol
    
    /// Remove a specific observer
    func removeObserver(_ observer: NSObjectProtocol)
    
    /// Remove multiple observers
    func removeObservers(_ observers: [NSObjectProtocol])
}

// MARK: - Event Data Validator Protocol

/// Protocol for validating and sanitizing event data
public protocol EventDataValidator {
    /// Validate notification user info data
    func validate(_ data: [String: Any]) -> Bool
    
    /// Sanitize notification user info data
    func sanitize(_ data: [String: Any]) -> [String: Any]
}
