import Foundation

extension VLBeacon {

  public var isUserBeaconConfigured: Bool {
    guard let userBeaconUrl, !userBeaconUrl.isEmpty else { return false }
    return true
  }

  /// Convenience for authentication beacon events — constructs `AuthenticationPayload`
  /// inside VLBeaconLib so callers never allocate the struct across module boundaries
  /// (avoids `EXC_BAD_ACCESS` when VLBeaconLib is a dynamic framework).
  ///
  /// - Important: Pass plain `String`s for `eventName` / `type` / `subType`. Passing
  ///   `UserBeaconEventEnum` / `AuthType` / `AuthSubType` across a dynamic VLBeaconLib
  ///   boundary causes `EXC_BAD_ACCESS` (null type metadata) at the call site.
  public func submitAuthenticationBeaconEvent(
    eventName: String,
    source: String? = "VLAuthentication",
    type: String? = nil,
    subType: String? = nil,
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
  /// - Important: `eventName` must be a `String` (not `UserBeaconEventEnum`) when called
  ///   from another module. Passing `UserBeaconEventEnum` across a dynamic VLBeaconLib
  ///   boundary causes `EXC_BAD_ACCESS` (null type metadata) at the call site.
  /// - `eventData` must be a dictionary (call `payload.toDictionary()` in the caller).
  public func submitUserBeaconEvent(
    eventName: String,
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
