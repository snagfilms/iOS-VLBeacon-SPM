//
//  VLPlayerAnalyticsModel.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 03/12/25.
//


import Foundation

public final class VLPlayerAnalyticsModel {
    
    public typealias PropertyChangeCallback = (String, Any?) -> Void
    
    // MARK: - Enum for Dictionary Keys
    public enum AnalyticsKey: String {
        case encodedFrameRate
        case encoding
        case screenResolution
        case duration
        case isDVREnabled
        case streamType
        case daiStream
    }
    
    // MARK: - Properties
    private var propertyChangeCallback: PropertyChangeCallback?
    
    
    public private(set) var encodedFrameRate: Int? {
        didSet { notifyPropertyChange(key: .encodedFrameRate) }
    }
    
    public private(set) var duration: Double? {
        didSet { notifyPropertyChange(key: .duration) }
    }
    
    public private(set) var isDVREnabled: Bool? {
        didSet { notifyPropertyChange(key: .isDVREnabled) }
    }
    
    public private(set) var encoding: String? {
        didSet { notifyPropertyChange(key: .encoding) }
    }
    
    public private(set) var streamType: String? {
        didSet { notifyPropertyChange(key: .streamType) }
    }
    
    public private(set) var daiStream: String? {
        didSet { notifyPropertyChange(key: .daiStream) }
    }
    
    public private(set) var screenResolution: String? {
        didSet { notifyPropertyChange(key: .screenResolution) }
    }
    
    // MARK: - Initializers
    public init(propertyChangeCallback: PropertyChangeCallback? = nil) {
        self.propertyChangeCallback = propertyChangeCallback
    }
    
    public init(
        encodedFrameRate: Int? = nil,
        encoding: String? = nil,
        screenResolution: String? = nil,
        streamType: String? = nil,
        daiStream: String? = "NO",
        duration: Double? = -1,
        isDVREnabled: Bool? = false,
        propertyChangeCallback: PropertyChangeCallback? = nil
    ) {
        self.propertyChangeCallback = propertyChangeCallback
        self.encodedFrameRate = encodedFrameRate
        self.encoding = encoding
        self.streamType = streamType
        self.duration = duration
        self.daiStream = daiStream
        self.isDVREnabled = isDVREnabled
        self.screenResolution = screenResolution
    }
    
    // MARK: - Callback Registration
    public func setPropertyChangeCallback(_ callback: @escaping PropertyChangeCallback) {
        self.propertyChangeCallback = callback
    }
    
    // MARK: - Setters
    public func setEncodedFrameRate(_ value: Int) { self.encodedFrameRate = value }
    public func setEncoding(_ value: String?) { self.encoding = value }
    public func setDuration(_ value: Double?) { self.duration = value }
    public func setStreamType(_ value: String?) { self.streamType = value }
    public func setDAIStream(_ value: String?) { self.daiStream = value }
    public func setIsDVREnabled(_ value: Bool?) { self.isDVREnabled = value }
    public func setScreenResolution(_ value: String?) { self.screenResolution = value }
    
    // MARK: - Dictionary Representation
    public var asDictionary: [String: Any] {
        [
            AnalyticsKey.encodedFrameRate.rawValue: encodedFrameRate ?? "",
            AnalyticsKey.encoding.rawValue: encoding ?? "",
            AnalyticsKey.streamType.rawValue: streamType ?? "",
            AnalyticsKey.daiStream.rawValue: daiStream ?? "",
            AnalyticsKey.duration.rawValue: duration ?? -1,
            AnalyticsKey.isDVREnabled.rawValue: isDVREnabled ?? false,
            AnalyticsKey.screenResolution.rawValue: screenResolution ?? ""
        ]
    }
    
    // MARK: - Callback Helper
    private func notifyPropertyChange(key: AnalyticsKey) {
        propertyChangeCallback?(key.rawValue, asDictionary[key.rawValue])
    }
    
}
