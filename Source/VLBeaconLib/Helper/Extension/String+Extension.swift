//
//  String+Extension.swift
//  VLBeacon
//
//  Created by NEXGEN on 28/03/23.
//

import Foundation

extension String{
    
    func urlEncodedString_ch() -> String {
        let output = NSMutableString()
        guard let source = self.cString(using: String.Encoding.utf8) else { return self }
        let sourceLen = source.count
        var i = 0
        while i < sourceLen - 1 {
            let thisChar = source[i]
            if thisChar == 32 {
                output.append("+")
            }
            else {
                output.appendFormat("%c", thisChar)
            }
            i += 1
        }
        
        return output as String
    }

}
