//
//  LifecycleManageable.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//

import Foundation

/// Protocol for objects that require cleanup
public protocol LifecycleManageable: AnyObject {
    /// Cleanup resources and observers
    func cleanup()
}
