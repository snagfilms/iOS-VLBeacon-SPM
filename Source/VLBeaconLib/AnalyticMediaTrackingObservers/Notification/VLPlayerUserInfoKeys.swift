//
//  VLPlayerUserInfoKeys.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//

import Foundation

/// Standard keys for accessing data in notification userInfo dictionaries
public struct VLPlayerUserInfoKeys {
    
    // MARK: - Asset Info Keys
    public static let adInfo = "adInfo"
    public static let chapterInfo = "chapterInfo"
    public static let userIdentity = "userIdentity"
    public static let sessionVideoId = "sessionVideoId"
    
    // MARK: - Time Keys
    public static let currentTime = "currentTime"
    public static let endTime = "endTime"
    public static let startTime = "startTime"
    public static let newTime = "newTime"
    public static let shouldResume = "shouldResume"
    public static let closeCaptionlanguage = "closeCaptionlanguage"
    public static let audioChange = "audioChange"
    public static let frameRateChange = "frameRateChange"
    public static let analyticsSeekStartTime = "analyticsSeekStartTime"
    public static let analyticsSeekEndTime = "analyticsSeekEndTime"
    
    // MARK: - Error Keys
    public static let errorMessage = "errorMessage"
    public static let isFatal = "isFatal"
    
    // MARK: - UI State Keys
    public static let isFullScreen = "isFullScreen"
    public static let trackOptions = "trackOptions"
    public static let chapterTimeline = "chapterTimeline"
    
    // MARK: - Analytics Keys
    public static let analyticsContentInfo = "analyticsContentInfo"
    public static let analyticsPlayerInfo = "analyticsPlayerInfo"
    public static let analyticsAvPlayer = "analyticsAvPlayer"
    public static let analyticsTVProviderInfo = "analyticsTVProviderInfo"
    public static let analyticsUserInfo = "analyticsUserInfo"
    public static let analyticsAdsLoaderInfo = "analyticsAdsLoaderInfo"
    
    private init() {}
}
