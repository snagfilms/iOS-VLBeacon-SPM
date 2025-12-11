//
//  RNPlayerViewManager.swift
//  ReactNativeVidApp2
//
//  Created by vikassachan@viewlift.com on 30/10/25.
//

import Foundation
import React

@objc(RNPlayerViewManager)
final public class RNPlayerViewManager: RCTViewManager {
    
    override public static func requiresMainQueueSetup() -> Bool {
        return true
    }
    
    override public func view() -> UIView! {
        return RNPlayerView()
    }
    
    // MARK: - Commands
    @objc override public func constantsToExport() -> [AnyHashable : Any]! {
        return [
            "Commands": [
                "play": 0,
                "pause": 1,
                "seekTo": 2,
                "goFullScreen": 3
            ]
        ]
    }
    
  @objc func performCommand(_ reactTag: NSNumber, commandId: NSNumber, args: NSArray, action: String) {

      
      DispatchQueue.main.async {
              // Try to find the view using the standard bridge (if available)
              // OR traverse the window if the registry fails
              
              let bridge = self.bridge
              
              // valid check
              guard let uiManager = bridge?.uiManager else { return }
              
              // Try resolving the view
              let view = uiManager.view(forReactTag: reactTag)
              
              if let targetView = view as? RNPlayerView {
                if action == "playVlplayer" {
                  targetView.play()

                } else if action == "pauseVlplayer" {
                  targetView.pause()

                } else if action == "releaseVlplayer" {
                  print("releaseVlplayer called")
                  targetView.destroyPlayer()

                }
                else if action == "goFullScreen" {
                  let isFullScreen = args[0] as? Bool ?? false
                   targetView.goFullScreen(isFullScreen)
                 }
              } else {
                  print("Still could not find view with tag: \(reactTag)")
              }
          }
    }
}
