import Foundation

extension VLBeacon {

  public var isUserBeaconConfigured: Bool {
    guard let userBeaconUrl, !userBeaconUrl.isEmpty else { return false }
    return true
  }

  /// Convenience for authentication beacon events — constructs `AuthenticationPayload`
  /// inside VLBeaconLib so callers never allocate the struct across module boundaries
  /// (avoids `EXC_BAD_ACCESS` when VLBeaconLib is a dynamic framework).
  public func submitAuthenticationBeaconEvent(
    eventName: UserBeaconEventEnum,
    source: String? = "VLAuthentication",
    type: AuthType? = nil,
    subType: AuthSubType? = nil,
    email: String? = nil,
    phoneNumber: String? = nil,
    mvpd: String? = nil,
    existingUser: Bool? = nil,
    additionalData: [String: String]? = nil
  ) {
    let payload = AuthenticationPayload(
      type: type,
      subType: subType,
      email: email,
      phoneNumber: phoneNumber,
      mvpd: mvpd,
      existingUser: existingUser,
      additionalData: additionalData,
      tokenIdentity: tokenIdentity
    )
    submitUserBeaconEvent(
      eventName: eventName,
      source: source,
      eventData: payload.toDictionary()
    )
  }

  /// Builds and submits a user beacon event inside VLBeaconLib.
  ///
  /// `eventData` must be a dictionary (call `payload.toDictionary()` in the caller).
  /// Passing `BeaconEventPayloadProtocol` existentials across a dynamic VLBeaconLib
  /// boundary causes `EXC_BAD_ACCESS` (null witness / metadata).
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
    eventData: [String: Any]? = nil,
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
