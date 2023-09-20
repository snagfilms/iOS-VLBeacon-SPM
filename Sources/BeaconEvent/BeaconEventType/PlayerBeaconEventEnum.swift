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
        
        case .custom(let eventName):
            return eventName
        }
    }
    
}
