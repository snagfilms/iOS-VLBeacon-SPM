//
//  VLPlayerNotificationHelper.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//

import Foundation
#if canImport(UIKit)
import UIKit
#endif

// MARK: - Core Notification Helper

public final class VLPlayerNotificationHelper: NotificationPublisher, NotificationSubscriber, LifecycleManageable {
    
    // MARK: - Properties
    
    public static let shared = VLPlayerNotificationHelper()
    
    private let notificationCenter: NotificationCenter
    private let validator: EventDataValidator
    private let notificationQueue: OperationQueue
    @ThreadSafeArray private var activeObservers: [NSObjectProtocol]
    
    // MARK: - Initialization
    
    public init(
        notificationCenter: NotificationCenter = .default,
        validator: EventDataValidator = VLEventDataValidator()
    ) {
        self.notificationCenter = notificationCenter
        self.validator = validator
        
        // Create dedicated queue for notifications
        self.notificationQueue = OperationQueue()
        self.notificationQueue.name = "com.vlbeacon.notification.queue"
        self.notificationQueue.maxConcurrentOperationCount = 1
        self.notificationQueue.qualityOfService = .userInitiated
        
        self._activeObservers = ThreadSafeArray(wrappedValue: [])
        
        #if os(iOS) || os(tvOS)
        setupMemoryWarningObserver()
        #endif
    }
    
    deinit {
        cleanup()
    }
    
    // MARK: - NotificationPublisher Protocol
    
    /// Post notification synchronously on main thread
    public func post(name: Notification.Name, userInfo: [String: Any]? = nil, object: Any? = nil) {
        let sanitizedUserInfo = sanitizeAndValidate(userInfo)
        
        if Thread.isMainThread {
            notificationCenter.post(name: name, object: object, userInfo: sanitizedUserInfo)
        } else {
            DispatchQueue.main.sync {
                self.notificationCenter.post(name: name, object: object, userInfo: sanitizedUserInfo)
            }
        }
    }
    
    /// Post notification asynchronously on main thread
    public func postAsync(name: Notification.Name, userInfo: [String: Any]? = nil, object: Any? = nil) {
        let sanitizedUserInfo = sanitizeAndValidate(userInfo)
        
        DispatchQueue.main.async { [weak self] in
            self?.notificationCenter.post(name: name, object: object, userInfo: sanitizedUserInfo)
        }
    }
    
    // MARK: - NotificationSubscriber Protocol
    
    @discardableResult
    public func addObserver(
        for name: Notification.Name,
        object: Any? = nil,
        queue: OperationQueue? = nil,
        using block: @escaping (Notification) -> Void
    ) -> NSObjectProtocol {
        let targetQueue = queue ?? .main
        
        let observer = notificationCenter.addObserver(
            forName: name,
            object: object,
            queue: targetQueue
        ) { [weak self] notification in
            // Wrap in autoreleasepool for memory efficiency
            autoreleasepool {
                self?.handleNotification(notification, with: block)
            }
        }
        
        _activeObservers.append(observer)
        return observer
    }
    
    public func removeObserver(_ observer: NSObjectProtocol) {
        notificationCenter.removeObserver(observer)
        // Note: Removal from activeObservers array could be optimized if needed
    }
    
    public func removeObservers(_ observers: [NSObjectProtocol]) {
        observers.forEach { removeObserver($0) }
    }
    
    // MARK: - LifecycleManageable Protocol
    
    public func cleanup() {
        let currentObservers = _activeObservers.wrappedValue
        currentObservers.forEach { notificationCenter.removeObserver($0) }
        _activeObservers.removeAll()
    }
    
    // MARK: - Private Methods
    
    private func sanitizeAndValidate(_ userInfo: [String: Any]?) -> [String: Any]? {
        guard let userInfo = userInfo else { return nil }
        
        guard validator.validate(userInfo) else {
            debugPrint("Invalid notification user info")
            return nil
        }
        
        return validator.sanitize(userInfo)
    }
    
    private func handleNotification(_ notification: Notification, with block: @escaping (Notification) -> Void) {
        block(notification)
    }
    
    #if os(iOS) || os(tvOS)
    private func setupMemoryWarningObserver() {
        NotificationCenter.default.addObserver(
            forName: UIApplication.didReceiveMemoryWarningNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            // Optional: Clean up caches or perform memory optimization
            self?.handleMemoryWarning()
        }
    }
    
    private func handleMemoryWarning() {
        // Implement memory warning handling if needed
    }
    #endif
}
