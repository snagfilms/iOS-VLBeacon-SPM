import Foundation

extension VLBeacon {

  public var isUserBeaconConfigured: Bool {
    guard let userBeaconUrl, !userBeaconUrl.isEmpty else { return false }
    return true
  }

  /// Builds and submits a user beacon event inside VLBeaconLib so callers never construct `UserBeaconEventStruct` across module boundaries.
  public func submitUserBeaconEvent(
    eventName: UserBeaconEventEnum,
    userId: String? = nil,
    profileId: String? = nil,
    siteId: String? = nil,
    pfm: String? = nil,
    etstamp: String? = nil,
    environment: String? = nil,
    appversion: String? = nil,
    source: String? = nil,
    eventData: BeaconEventPayloadProtocol? = nil,
    additionalData: [String: Any]? = nil,
    userMergedForAnonymousId: String? = nil
  ) {
    guard isUserBeaconConfigured else { return }

    let event = UserBeaconEventStruct(
      eventName: eventName,
      userId: userId,
      profileId: profileId,
      siteId: siteId,
      pfm: pfm,
      etstamp: etstamp,
      environment: environment,
      appversion: appversion,
      source: source,
      eventData: eventData,
      additionalData: additionalData,
      tokenIdentity: tokenIdentity
    )
    triggerBeaconEvent(event, userMergedForAnonymousId: userMergedForAnonymousId)
  }
}
