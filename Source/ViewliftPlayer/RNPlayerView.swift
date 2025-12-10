//
//  RNPlayerModule.swift
//  ReactNativeVidApp2
//
//  Created by vikassachan@viewlift.com on 30/10/25.
//

import Foundation
import UIKit
import React
import VLPlayerLib
import VLBeaconLib

@objc(RNPlayerView)
final public class RNPlayerView: UIView {
    private var vlPlayer: VLPlayer!
    private var playerView: UIView?
    private var loader: UIActivityIndicatorView?
    
    @objc var videoSourceData: NSDictionary? {
        didSet {
            Task { await setupPlayer() }
        }
    }
  let vm = FeedVCVM()
  var verticalPlayer: UIViewController?
  @objc var onVideoStateChange: RCTDirectEventBlock?
    
    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .black
    }
    
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    private func showLoader() {
        loader?.removeFromSuperview()
        let loaderView = UIActivityIndicatorView(style: .large)
        loaderView.center = center
        loaderView.startAnimating()
        addSubview(loaderView)
        loader = loaderView
    }
    
    private func hideLoader() {
        loader?.stopAnimating()
        loader?.removeFromSuperview()
        loader = nil
    }
    
    private func createVLPlayer() -> VLPlayer {
      
            return VLPlayer(playerType: .default)
    }
    
    private func getPlaybackSourceType(from data: NSDictionary) -> VLPlayer.PlaybackSourceType? {
      if let streamUrl = data["videoUrl"] as? String, streamUrl.isEmpty == false {
            let isLive = data["isLive"] as? Bool ?? false
            let isDVR = data["isDVR"] as? Bool ?? false
            
            let streamType = VLPlayer.DirectStreamType(
                url: streamUrl,
                streamConfig: VLPlayer.StreamConfig(isLive: isLive, isDVR: isDVR, isSSAIEnabled: true),
                drmconfig: nil
            )
            
            let playbackConfig = VLPlayer.DirectStreamPlaybackConfig(stream: streamType)
            return .directStream(playbackConfig)
        }
        
        if let token = data["token"] as? String,
           token.isEmpty == false,
           let apiBaseURL = data["baseUrl"] as? String,
           let videoId = data["assetId"] as? String {
            let config = VLPlayer.ContentPlaybackConfig(
                videoId: videoId,
                token: token,
                apiBaseURL: apiBaseURL,
                adobeTempPassPayload: nil
            )
            return .contentPlayback(config)
        }
            
      let streamType = VLPlayer.DirectStreamType(
          url: "https://prodamdnewsencoding.akamaized.net/NBC_News_Digital/n_cabrera_rubin_khardori_capitol_rioter_charged_with_threatening_hakeem_jeffries_251021/1/abs/index.m3u8",
          streamConfig: VLPlayer.StreamConfig(isLive: false, isDVR: false, isSSAIEnabled: true),
          drmconfig: nil
      )
      
      let playbackConfig = VLPlayer.DirectStreamPlaybackConfig(stream: streamType)
      return .directStream(playbackConfig)
        
    }
    
    private func getPlayerFeaturesSupported() -> VLPlayerLib.VLPlayer.VLPlayerFeatureSupported {
      return VLPlayerLib.VLPlayer.VLPlayerFeatureSupported(appMacrosList: nil, customPlayerControlsColor: nil, chromecastCustomReceiver: nil, controlsVisibility: .auto)
    }
    
    @MainActor
    private func setupPlayer() async {
      
      guard let data = videoSourceData else { return }
        
        showLoader()
        
        let vlBaseUrl = data["apiBaseURL"] as? String ?? ""
        let featureSupported = getPlayerFeaturesSupported()
        
      let type = data["playerType"] as? String
      if type == "VERTICAL_VL_PLAYER" {
        let verticalVC = VLFeedPlayer().setSource(delegate: vm,
                                                            config: vm.config,
                                                            baseUrl: "https://livgolfplus.staging.api.viewlift.com",
                                                            authToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhbm9ueW1vdXNJZCI6ImI2NTAzMjgzZDNjOTJiMDE0ZmExNzNmZGU1MGQ0ODJkN2FlYWI3MDc4Y2U2OGMxODQwZTFlY2U0MzYwMzhkN2MiLCJjb3VudHJ5Q29kZSI6IklOIiwiZGV2aWNlSWQiOiJicm93c2VyLTQxMmE5MjJjLTk3NWMtNmUyYi1kZWUwLTYzNGJmNzdmNzA5MSIsImV4cCI6MTc5Njc0NzAyOSwiaWF0IjoxNzY1MjExMDI5LCJpZCI6IjMxYWIzMjYwLTg0YWEtNDc2NC1hZWYwLTI1NzYxZjFmZGIzNSIsImlwYWRkcmVzcyI6IjEyMi4xNjEuNDguMTg2IiwiaXBhZGRyZXNzZXMiOiIxMjIuMTYxLjQ4LjE4NiwxMC4xNjAuMS4yNDciLCJwb3N0YWxjb2RlIjoiMTEwMDkxIiwicHJvdmlkZXIiOiJ2aWV3bGlmdCIsInNpdGUiOiJsaXYtZ29sZiIsInNpdGVJZCI6IjllZDdkZWUwLWM3MTktMTFlYy1iYzI1LWExOTVjMmEzNDM1NyIsInVzZXJJZCI6IjMxYWIzMjYwLTg0YWEtNDc2NC1hZWYwLTI1NzYxZjFmZGIzNSIsInVzZXJuYW1lIjoiYW5vbnltb3VzIn0.BvjDyUU06pEVo4EYPLUE6N9TcMlq2QokmR-uW_m9Z3w")!
        self.verticalPlayer = verticalVC
        if let verticalView = verticalVC.view {
          
          verticalView.frame = self.bounds
          verticalView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
          verticalView.isUserInteractionEnabled = true
          self.addSubview(verticalView)
        }
        
      } else {
        let player = createVLPlayer()
        vlPlayer = player
        player.videoPlayerDelegate = self
        guard let sourceType = getPlaybackSourceType(from: data) else {
          print("❌ Invalid playback source type")
          return
        }
        
        
        player.setSource(
          type: sourceType,
          vlPlayerTag: "1",
          customControlsView: nil,
          adUrl: nil,
          playerFeaturesSupported: featureSupported,
          nextPlaybackList: nil
        ) { [weak self] isSuccess, playerView, contentResponse in
          guard let self = self else { return }
          DispatchQueue.main.async {
            self.hideLoader()
            
            if let pv = playerView {
              // remove previous
              self.playerView?.removeFromSuperview()
              
              // add SDK player view
              pv.frame = self.bounds
              pv.autoresizingMask = [.flexibleWidth, .flexibleHeight]
              pv.isUserInteractionEnabled = true
              self.addSubview(pv)
              self.playerView = pv
              
              
              print("✅ [RNPlayerView] Player view added successfully")
            } else {
              print("❌ [RNPlayerView] Failed to load player view")
            }
          }
        }
      }
    }
    
    // MARK: - Commands
  func play() { vlPlayer?.play() }
  func pause() { vlPlayer?.pause() }
  func seekTo(_ ms: Int) { }
  func destroyPlayer() {
    vlPlayer?.videoPlayerDelegate = nil
    vlPlayer?.destroy()
    vlPlayer?.getVideoPlayerView()?.removeFromSuperview()
    playerView?.removeFromSuperview()
    playerView = nil
  }
  
  func sendVideoStateEvent(isPlaying: Bool) {
          // Check if React Native has assigned a listener to this prop
          if let callback = onVideoStateChange {
              // Send the data. Keys must match your JS expectations.
              callback(["isPlaying": isPlaying])
          }
      }
  
}
extension RNPlayerView: VideoPlaybackDelegate {
  func videoPause(timestamp: Double, playerTag: String) {
    sendVideoStateEvent(isPlaying: false)
  }
  
  func videoResume(timestamp: Double, playerTag: String) {
    sendVideoStateEvent(isPlaying: true)
  }
  
  func videoStarted(timestamp: Double, playerTag: String) {
    sendVideoStateEvent(isPlaying: true)
  }
}
