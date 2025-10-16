//
//  PlayerBeaconEventEnum.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 26/06/23.
//

import Foundation

public enum PlayerBeaconEventEnum : BeaconEventNameProtocol, Equatable{
    
    case play
    case firstFrame
    case ping
    case adRequest
    case adImpression
    case failedToStart
    case buffering
    case droppedStream
    case resume
    case pause
    case watchLive // When the user clicks on a live stream to start watching LIVE
    case startFromBeginning // When the user clicks to start from the beginning
    case resumePlayback // When the user clicks to resume playback from where they left off
    case seekForward // When the user clicks to seek forward
    case seekBackward //When the user clicks to seek backward
    
    case custom(eventName: String)
    
    public func getBeaconEventNameString() -> String {
        switch self {
        case .play:
            return "PLAY"
        case .resume:
            return "RESUME"
        case .pause:
            return "PAUSE"
        case .firstFrame:
            return "FIRST_FRAME"
        case .ping:
            return "PING"
        case .adRequest:
            return "AD_REQUEST"
        case .adImpression:
            return "AD_IMPRESSION"
        case .failedToStart:
            return "FAILED_TO_START"
        case .buffering:
            return "BUFFERING"
        case .droppedStream:
            return "DROPPED_STREAM"
        case .watchLive:
            return "WATCH_LIVE"
        case .startFromBeginning:
            return "START_FROM_BEGINNING"
        case .resumePlayback:
            return "RESUME_PLAYBACK"
        case .seekForward:
            return "SEEK_FORWARD"
        case .seekBackward:
            return "SEEK_BACKWARD"
        case .custom(let eventName):
            return eventName
        }
    }
    
}
