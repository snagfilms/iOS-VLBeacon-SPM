//
//  UserBeaconEventEnum.swift
//  VLBeacon
//
//  Created by NEXGEN on 28/03/23.
//

import Foundation

public enum UserBeaconEventEnum : BeaconEventNameProtocol, Equatable{
    
    case loginInit
    case loginSuccess
    case loginFailure
    case logout
    
    //ask to add
    case signupInit
    case signupSuccess
    case signupFailure
    case resendVerificationCode
    
    case getVerificationCode
    case submitVerificationCode
    
    case search
    
    case addToWatchlist
    case removeFromWatchlist
    case removeAllFromWatchlist
    case removeAllFromWatchHistory
    
    case pageView
    case like
    case dislike
    case clickOnItem
    case share
    case languageSelection
    
    case subscribeNow
    case planSelection
    case applyCodeStatus
    case cardAdded
    case paymentInitiate
    case paymentPending
    case paymentSuccess
    case paymentFailed

    case cancelSubscription
    case updateSubscription
    
    case updateName
    case updateMobileNumber
    case updateEmail
    
    case verifyMobileNumber
    case verifyEmail
    
    case setGameAlerts
    
    case customerFeedback
    
    case deleteAccount
    
    case setAutoPlay
    
    case removeAllDevices
    case removeDevice
    
    case custom(eventName: String)
    
    public func getBeaconEventNameString() -> String {
        switch self {
        case .loginInit:
            return "login-init"
        case .loginSuccess:
            return "login-success"
        case .loginFailure:
            return "login-failure"
        case .logout:
            return "logout"
        case .signupInit:
            return "signup-init"
        case .signupSuccess:
            return "signup-success"
        case .signupFailure:
            return "signup-failure"
        case .resendVerificationCode:
            return "resend-verification-code"
        case .getVerificationCode:
            return "get-verification-code"
        case .submitVerificationCode:
            return "submit-verification-code"
        case .search:
            return "search"
        case .addToWatchlist:
            return "add-to-watchlist"
        case .removeFromWatchlist:
            return "remove-from-watchlist"
        case .removeAllFromWatchlist:
            return "remove-all-from-watchlist"
        case .removeAllFromWatchHistory:
            return "remove-all-from-watch-history"
        case .pageView:
            return "page-view"
        case .like:
            return "like"
        case .dislike:
            return "dislike"
        case .clickOnItem:
            return "click-on-item"
        case .share:
            return "share"
        case .languageSelection:
            return "language-selection"
        case .subscribeNow:
            return "subscribe-now"
        case .planSelection:
            return "plan-selection"
        case .applyCodeStatus:
            return "apply-code-status"
        case .cardAdded:
            return "card-added"
        case .paymentInitiate:
            return "payment-initiate"
        case .paymentPending:
            return "payment-pending"
        case .paymentSuccess:
            return "payment-success"
        case .paymentFailed:
            return "payment-failed"
        case .cancelSubscription:
            return "cancel-subscription"
        case .updateSubscription:
            return "update-subscription"
        case .updateName:
            return "update-name"
        case .updateMobileNumber:
            return "update-mobile-number"
        case .updateEmail:
            return "update-email"
        case .verifyMobileNumber:
            return "verify-mobile-number"
        case .verifyEmail:
            return "verify-email"
        case .setGameAlerts:
            return "set-game-alerts"
        case .customerFeedback:
            return "customer-feedback"
        case .deleteAccount:
            return "delete-account"
        case .setAutoPlay:
            return "set-auto-play"
        case .removeAllDevices:
            return "remove-all-devices"
        case .removeDevice:
            return "remove-device"
        case .custom(let eventName):
            return eventName
        }
    }
    
}

/*
 switch self {
     
     ///Authentication events
 case .loginInit:
     return "login-init"
 case .loginSuccess:
     return "login-success"
 case .loginFailure:
     return "login-failure"
 case .logout:
     return "logout"
     
 case .getVerificationCode:
     return "get-verification-code"
 case .submitVerificationCode:
     return "submit-verification-code"
     
     ///---- ask to add
 case .resendVerificationCode:
     return "resend-verification-code"
 case .signupInit:
     return "signup-init"
 case .signupSuccess:
     return "signup-success"
 case .signupFailure:
     return "signup-failure"
     
     
     ///StoreKit events
 case .subscribeNow:
     return "subscribe_now"
 
 case .paymentPending:
     return "payment-pending"
 
 case .paymentFailed:
     return "payment-failed"

     ///Behaviour events
 case .search:
     return "search"
 case .addToWatchlist:
     return "add-to-watchlist"
 case .removeFromWatchlist:
     return "remove-from-watchlist"
 case .removeAllFromWatchlist:
     return "remove-all-from-watchlist"
 case .removeAllFromWatchHistory:
     return "remove-all-from-watch-history"
     
     
 case .languageSelection:
     return "language-selection"
     
 case .share:
     return "share"
 case .pageView:
     return "page-view"
 case .like
     return "like"
 case .dislike
     return "dislike"
     
     ///User defined event name
 case .custom(let event):
     return event
 }
 */
