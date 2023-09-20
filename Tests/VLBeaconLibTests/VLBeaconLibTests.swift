import XCTest
@testable import VLBeaconLib

final class VLBeaconLibTests: XCTestCase {
    func testExample() throws {
        XCTAssertNotNil(VLBeacon.sharedInstance.getBeaconBaseUrl())
    }
}
