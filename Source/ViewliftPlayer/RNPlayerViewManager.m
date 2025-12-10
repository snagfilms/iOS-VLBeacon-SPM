//
//  RNPlayerViewManager.m
//  ReactNativeVidApp2
//
//  Created by vikassachan@viewlift.com on 30/10/25.
//

#import <React/RCTViewManager.h>
#import <React/RCTBridge.h>

@interface RCT_EXTERN_MODULE(RNPlayerViewManager, RCTViewManager)

// This exports your Swift @objc property to JS
RCT_EXPORT_VIEW_PROPERTY(videoSourceData, NSDictionary)
RCT_EXTERN_METHOD(performCommand:(nonnull NSNumber *)reactTag
                  commandId:(nonnull NSNumber *)commandId
                  args:(nonnull NSArray *)args
                  action:(nonnull NSString *) action)
RCT_EXPORT_VIEW_PROPERTY(onVideoStateChange, RCTDirectEventBlock)
@end
