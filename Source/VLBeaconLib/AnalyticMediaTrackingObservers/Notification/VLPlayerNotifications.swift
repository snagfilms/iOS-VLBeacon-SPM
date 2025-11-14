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
    
    // MARK: - Bundle Identifier
    
    /// The bundle identifier prefix for all notifications
    /// This ensures uniqueness across multiple apps using the same library
    private static var bundlePrefix: String {
        if let bundleId = Bundle.main.bundleIdentifier {
            return bundleId
        }
        
        return "com.viewlift.mediaTracking"
    }
    
    /// Helper method to create notification names with bundle identifier prefix
    private static func notificationName(_ suffix: String) -> Notification.Name {
        return Notification.Name("\(bundlePrefix).\(suffix)")
    }
    
    // MARK: - Analytics Info
    
    public static var analyticsInfoUpdated: Notification.Name {
        notificationName("vlplayer.analytics.info.updated")
    }
    
    // MARK: - Session Events
    
    public static var sessionStart: Notification.Name {
        notificationName("vlplayer.session.start")
    }
    
    public static var sessionEnd: Notification.Name {
        notificationName("vlplayer.session.end")
    }
    
    // MARK: - Playback Events
    
    public static var playStarted: Notification.Name {
        notificationName("vlplayer.play.started")
    }
    
    public static var videoPaused: Notification.Name {
        notificationName("vlplayer.video.paused")
    }
    
    public static var videoComplete: Notification.Name {
        notificationName("vlplayer.video.complete")
    }
    
    // MARK: - Ads Events
    
    public static var adsStart: Notification.Name {
        notificationName("vlplayer.ads.start")
    }
    
    public static var adsComplete: Notification.Name {
        notificationName("vlplayer.ads.complete")
    }
    
    public static var adsBreakStart: Notification.Name {
        notificationName("vlplayer.ads.break.start")
    }
    
    public static var adsBreakComplete: Notification.Name {
        notificationName("vlplayer.ads.break.complete")
    }
    
    // MARK: - Buffering Events
    
    public static var bufferStart: Notification.Name {
        notificationName("vlplayer.buffer.start")
    }
    
    public static var bufferComplete: Notification.Name {
        notificationName("vlplayer.buffer.complete")
    }
    
    public static var bitrateChange: Notification.Name {
        notificationName("vlplayer.bitrate.change")
    }
    
    public static var closeCaptionChange: Notification.Name {
        notificationName("vlplayer.closed.caption")
    }
    
    public static var audioChange: Notification.Name {
        notificationName("vlplayer.audio")
    }
    
    // MARK: - Seeking Events
    
    public static var seekStart: Notification.Name {
        notificationName("vlplayer.seek.start")
    }
    
    public static var seekComplete: Notification.Name {
        notificationName("vlplayer.seek.complete")
    }
    
    // MARK: - Chapter Events
    
    public static var chapterStart: Notification.Name {
        notificationName("vlplayer.chapter.start")
    }
    
    public static var chapterComplete: Notification.Name {
        notificationName("vlplayer.chapter.complete")
    }
    
    // MARK: - Playhead Events
    
    public static var playheadUpdate: Notification.Name {
        notificationName("vlplayer.playhead.update")
    }
    
    // MARK: - Error Events
    
    public static var error: Notification.Name {
        notificationName("vlplayer.error")
    }
    
    // MARK: - Assets Events
    
    public static var videoAssetsUpdated: Notification.Name {
        notificationName("vlplayer.assets.video.updated")
    }
    
    public static var adAssetsUpdated: Notification.Name {
        notificationName("vlplayer.assets.ad.updated")
    }
    
    public static var userIdentityUpdated: Notification.Name {
        notificationName("vlplayer.useridentity.updated")
    }
    
    public static var screenModeUpdated: Notification.Name {
        notificationName("vlplayer.screenmode.updated")
    }
    
    public static var reportDroppedFramesUpdate: Notification.Name {
        notificationName("vlplayer.dropperFrames.updated")
    }
    
    private init() {}
}

// MARK: - Debug Helper

#if DEBUG
public extension VLPlayerNotifications {
    /// Print all notification names for debugging
    static func printAllNotifications() {
        print("📢 VLPlayer Notification Names (Bundle: \(bundlePrefix)):")
        print("  - sessionStart: \(sessionStart.rawValue)")
        print("  - playStarted: \(playStarted.rawValue)")
        print("  - adsStart: \(adsStart.rawValue)")
        // Add more as needed
    }
}
#endif

