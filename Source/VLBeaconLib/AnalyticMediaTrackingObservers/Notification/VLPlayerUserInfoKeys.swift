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
    public static let playheadInfo = "playheadInfo"
    public static let endTime = "endTime"
    public static let startTime = "startTime"
    public static let newTime = "newTime"
    public static let shouldResume = "shouldResume"
    public static let closeCaptionlanguage = "closeCaptionlanguage"
    public static let audioChange = "audioChange"
    public static let frameRateChange = "frameRateChange"
    public static let analyticsSeekStartTime = "analyticsSeekStartTime"
    public static let analyticsSeekEndTime = "analyticsSeekEndTime"
    public static let currentAdElapsedDuration = "currentAdElapsedDuration"
    
    // MARK: - Error Keys
    public static let errorMessage = "errorMessage"
    public static let isFatal = "isFatal"
    public static let errorCode = "errorCode"
    public static let vl_errorCode = "vl_errorCode"
    
    // MARK: - UI State Keys
    public static let isFullScreen = "isFullScreen"
    public static let trackOptions = "trackOptions"
    public static let chapterTimeline = "chapterTimeline"
    
    // MARK: - Chaptering Click-Stream Keys
    public static let playerControlAction = "playerControlAction"
    public static let playerAction = "playeraction"
    public static let playerState = "playerstate"
    public static let recapTitle = "recaptitle"
    public static let recapNumber = "recapnumber"
    public static let recapLocation = "location"
    public static let recapTags = "tags"
    public static let carouselName = "carouselname"
    public static let carouselAction = "carouselaction"
    public static let isChapteringCuePointEnable = "isChapteringCuePointEnable"
    
    // MARK: - Analytics Keys
    public static let analyticsContentInfo = "analyticsContentInfo"
    public static let analyticsPlayerInfo = "analyticsPlayerInfo"
    public static let analyticsAvPlayer = "analyticsAvPlayer"
    public static let analyticsTVProviderInfo = "analyticsTVProviderInfo"
    public static let analyticsOtherInfo = "analyticsOtherInfo"
    public static let analyticsUserInfo = "analyticsUserInfo"
    public static let analyticsAdsLoaderInfo = "analyticsAdsLoaderInfo"
    public static let customParameters = "customParameters"
    
    private init() {}
}
