//
//  VLConfiguration.swift
//  VLAuthentication
//
//  Created by Gaurav Vig on 29/12/22.
//

import Foundation

struct VLConfiguration:Decodable {
	let beaconApiUrl: String?
	
    private enum CodingKeys:String, CodingKey {
		case beaconApiUrl = "BeaconApiUrl"
    }
}
