//
//  VLPlayerNotifications.swift
//  VLBeaconLib
//
//  Created by rakeshkrsharma@viewlift.com on 22/10/25.
//


import Foundation

/// Central repository for all player-related notification names
/// ⚠️ CRITICAL: These names MUST remain stable across all SPM modules
public struct VLPlayerNotifications {
    
    // MARK: - Analytics Info
    public static let analyticsInfoUpdated = Notification.Name("com.vlplayer.analytics.info.updated")
    
    // MARK: - Session Events
    public static let sessionStart = Notification.Name("com.vlplayer.session.start")
    public static let sessionEnd = Notification.Name("com.vlplayer.session.end")
    
    // MARK: - Playback Events
    public static let playStarted = Notification.Name("com.vlplayer.play.started")
    public static let videoPaused = Notification.Name("com.vlplayer.video.paused")
    public static let videoComplete = Notification.Name("com.vlplayer.video.complete")
    
    // MARK: - Ads Events
    public static let adsStart = Notification.Name("com.vlplayer.ads.start")
    public static let adsComplete = Notification.Name("com.vlplayer.ads.complete")
    public static let adsBreakStart = Notification.Name("com.vlplayer.ads.break.start")
    public static let adsBreakComplete = Notification.Name("com.vlplayer.ads.break.complete")
    
    // MARK: - Buffering Events
    public static let bufferStart = Notification.Name("com.vlplayer.buffer.start")
    public static let bufferComplete = Notification.Name("com.vlplayer.buffer.complete")
    public static let bitrateChange = Notification.Name("com.vlplayer.bitrate.change")
    
    // MARK: - Seeking Events
    public static let seekStart = Notification.Name("com.vlplayer.seek.start")
    public static let seekComplete = Notification.Name("com.vlplayer.seek.complete")
    
    // MARK: - Chapter Events
    public static let chapterStart = Notification.Name("com.vlplayer.chapter.start")
    public static let chapterComplete = Notification.Name("com.vlplayer.chapter.complete")
    
    // MARK: - Playhead Events
    public static let playheadUpdate = Notification.Name("com.vlplayer.playhead.update")
    
    // MARK: - Error Events
    public static let error = Notification.Name("com.vlplayer.error")
    
    // MARK: - Assets Events
    public static let videoAssetsUpdated = Notification.Name("com.vlplayer.assets.video.updated")
    public static let adAssetsUpdated = Notification.Name("com.vlplayer.assets.ad.updated")
    public static let userIdentityUpdated = Notification.Name("com.vlplayer.useridentity.updated")
    public static let screenModeUpdated = Notification.Name("com.vlplayer.screenmode.updated")
    
    private init() {}
}
