//
//  ThreadSafe.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//


import Foundation

// MARK: - Thread-Safe Property Wrapper

/// Property wrapper for thread-safe access to any value type
@propertyWrapper
public final class ThreadSafe<Value> {
    private let queue = DispatchQueue(label: "com.vlbeacon.threadsafe.\(UUID().uuidString)")
    private var value: Value
    
    public init(wrappedValue: Value) {
        self.value = wrappedValue
    }
    
    public var wrappedValue: Value {
        get {
            queue.sync { value }
        }
        set {
            queue.sync { value = newValue }
        }
    }
    
    public var projectedValue: ThreadSafe<Value> {
        self
    }
    
    /// Perform atomic mutation on the wrapped value
    public func mutate(_ transform: (inout Value) -> Void) {
        queue.sync {
            transform(&value)
        }
    }
}

// MARK: - Thread-Safe Array Property Wrapper

/// Property wrapper for thread-safe array operations
@propertyWrapper
public final class ThreadSafeArray<Element> {
    private let queue = DispatchQueue(
        label: "com.vlbeacon.threadsafe.array.\(UUID().uuidString)",
        attributes: .concurrent
    )
    private var array: [Element]
    
    public init(wrappedValue: [Element] = []) {
        self.array = wrappedValue
    }
    
    public var wrappedValue: [Element] {
        get {
            queue.sync { array }
        }
        set {
            queue.sync(flags: .barrier) {
                self.array = newValue
            }
        }
    }
    
    public var projectedValue: ThreadSafeArray<Element> {
        self
    }
    
    // MARK: - Thread-Safe Operations
    
    public func append(_ element: Element) {
        queue.async(flags: .barrier) {
            self.array.append(element)
        }
    }
    
    public func removeAll() {
        queue.async(flags: .barrier) {
            self.array.removeAll()
        }
    }
    
    public func remove(at index: Int) {
        queue.async(flags: .barrier) {
            guard index < self.array.count else { return }
            self.array.remove(at: index)
        }
    }
    
    public func forEach(_ body: (Element) -> Void) {
        queue.sync {
            array.forEach(body)
        }
    }
    
    public var count: Int {
        queue.sync { array.count }
    }
    
    public var isEmpty: Bool {
        queue.sync { array.isEmpty }
    }
    
    public func first(where predicate: (Element) -> Bool) -> Element? {
        queue.sync {
            array.first(where: predicate)
        }
    }
}
