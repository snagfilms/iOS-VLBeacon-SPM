//
//  NetworkHandler.swift
//  VLBeacon
//
//  Created by NEXGEN on 28/03/23.
//

import Foundation
import AdSupport


enum RequestType: String
{
    case get    = "GET"
    case post   = "POST"
    case delete = "DELETE"
}

class NetworkHandler: NSObject {
    
    static let sharedInstance:NetworkHandler = {
        
        let instance = NetworkHandler()
        
        return instance
    }()
    //MARK: Method to trigger api calls for beacon events
    func callNetworkToPostBeaconData(apiURL:String, requestType:RequestType, authenticationToken:String?, requestHeaders:Dictionary<String, String>?, parameters : Array<Dictionary<String,Any>>, responseForConfiguration: @escaping ( (_ responseConfigData: Bool?) -> Void)) -> Void {
        Log.shared.d("Network: Posting to \(apiURL) -> \(parameters)")
        let encodedURL = apiURL.urlEncodedString_ch()
        var requestHeaders:Dictionary<String, String>? = requestHeaders
        
        if requestHeaders == nil {
            
            requestHeaders = [:]
        }
        requestHeaders?["Authorization"] = authenticationToken
        requestHeaders?["Content-Type"] = "application/json"
        
        guard let requestUrl = URL(string:encodedURL) else { return responseForConfiguration(false) }
        
        var request = URLRequest(url: requestUrl)
        request.httpMethod = requestType.rawValue
        request.httpBody = try! JSONSerialization.data(withJSONObject: parameters)
        requestHeaders?["User-Agent"] = Utility.sharedInstance.getDeviceUserAgent()
        request.allHTTPHeaderFields = requestHeaders
        getCURLRequest(request: request)
        
        let task = URLSession.shared.dataTask(with: request) {
            (data, response, error) in
            if error == nil {
                let queueResultJson = try? JSONSerialization.jsonObject(with: data!)
                if queueResultJson is Dictionary<String,AnyObject> {
                    let queueResultDict:Dictionary<String,AnyObject>? = queueResultJson as? Dictionary<String,AnyObject>
                    if queueResultDict != nil {
                        if let requestId = queueResultDict?["requestId"] {
                            Log.shared.s("Successfully Posted! ->> \(requestId)")
                            responseForConfiguration(true)
                        }
                        else
                        {
                            responseForConfiguration(false)
                        }
                        
                    } else {
                        responseForConfiguration(false)
                    }
                } else {
                    responseForConfiguration(false)
                }
            }
            else {
                responseForConfiguration(false)
            }
        }
        task.resume()
    }
    
    private func getCURLRequest(request: URLRequest) {
       
            var curlString = "THE CURL REQUEST:\n"
            curlString += "curl -X \(request.httpMethod!) \\\n"

            request.allHTTPHeaderFields?.forEach({ (key, value) in
                let headerKey = self.escapeQuotesInString(str: key)
                let headerValue = self.escapeQuotesInString(str: value)
                curlString += " -H \'\(headerKey): \(headerValue)\' \n"
            })

            curlString += " \(request.url!.absoluteString) \\\n"

            if let body = request.httpBody {
                if let str = String(data: body, encoding: String.Encoding.utf8) {
                    let bodyDataString = self.escapeQuotesInString(str: str)
                    curlString += " -d \'\(bodyDataString)\'"
                }
            }
        
        Log.shared.s("Beacon Curl Request ->> \(curlString)")
        
    }
}
