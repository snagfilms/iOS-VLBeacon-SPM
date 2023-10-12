//
//  NetworkSpeedTest.swift
//  ConnectionSpeedTest
//
//  Created by Faraz Habib on 16/09/23.
//

import Foundation

protocol NetworkSpeedProviderDelegate: AnyObject {
    
    func connectionInfo(networkSpeed: NetworkConnectionStatus, bandwidth: CGFloat?, unit: NetworkBandwidthUnit)
    
    func didFailToConnect(error: Error)
    
}

public enum NetworkConnectionStatus: String {
    case poor
    case good
    case disConnected
}

public enum NetworkBandwidthUnit: String {
    case mbps
    case kbps
    case bps
}

class ConnectionSpeedTest: NSObject {
    
    weak var delegate: NetworkSpeedProviderDelegate?
    
    private var startTime = CFAbsoluteTime()
    private var stopTime = CFAbsoluteTime()
    private var bytesReceived: CGFloat = 0
    private var testURL:String
    private var speedTestCompletionHandler: ((_ megabytesPerSecond: CGFloat?, _ error: Error?) -> Void)? = nil
    private var timerForSpeedTest:Timer?
    private var timeInterval: TimeInterval = 30
    private var timeout: TimeInterval = 30
    private var unit: NetworkBandwidthUnit
    
    init(testURL: String, timeInterval: TimeInterval?, unit: NetworkBandwidthUnit) {
        self.testURL = testURL
        self.unit = unit
        if let timeInterval {
            self.timeInterval = timeInterval
            self.timeout = timeInterval
        }
    }
    
    func startTest() {
        speedTestCompletionHandler = { [weak self] (megabytesPerSecond: CGFloat?, error: Error?) in
            guard let this = self else { return }
            
            print("%0.3f; mbps = \(megabytesPerSecond ?? 0)")
            
            if let error = error as? NSError {
                if error.code == -1009 {
                    this.delegate?.connectionInfo(networkSpeed: .disConnected, bandwidth: 0, unit: this.unit)
                } else {
                    this.delegate?.didFailToConnect(error: error)
                }
            } else {
                guard let megabytesPerSecond, megabytesPerSecond > 0 else {
                    this.delegate?.connectionInfo(networkSpeed: .disConnected, bandwidth: 0, unit: this.unit)
                    return
                }
                
                switch megabytesPerSecond {
                case 0...1:
                    this.delegate?.connectionInfo(networkSpeed: .poor,
                                                  bandwidth: this.convertUnitForMeasuredValue(mbps: megabytesPerSecond),
                                                  unit: this.unit)
                default:
                    this.delegate?.connectionInfo(networkSpeed: .good,
                                                  bandwidth: this.convertUnitForMeasuredValue(mbps: megabytesPerSecond),
                                                  unit: this.unit)
                }
            }
        }
        timerForSpeedTest = Timer.scheduledTimer(withTimeInterval: timeInterval, repeats: true, block: { [weak self] _ in
            guard let this = self else { return }
            
            this.testDownloadSpeed(withTimout: this.timeout)
            
        })
//        self.testDownloadSpeed(withTimout: timeInterval)
    }
    
    private func convertUnitForMeasuredValue(mbps: CGFloat) -> CGFloat {
        switch self.unit {
        case .kbps:
            return round(mbps * pow(10, 3) * 100) / 100
        case .mbps:
            return round(mbps * 100) / 100
        case .bps:
            return round(mbps * pow(10, 6) * 100) / 100
        }
    }
    
}

extension ConnectionSpeedTest: URLSessionDataDelegate, URLSessionDelegate {
    
    private func testDownloadSpeed(withTimout timeout: TimeInterval) {
        let urlForSpeedTest = URL(string: testURL)
        
        startTime = CFAbsoluteTimeGetCurrent()
        bytesReceived = 0
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForResource = timeout
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        
        guard let checkedUrl = urlForSpeedTest else { return }
     
        session.dataTask(with: checkedUrl).resume()
    }
    
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        bytesReceived += CGFloat(data.count)
    }
    
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let elapsed = (CFAbsoluteTimeGetCurrent() - startTime)
        if error == nil {
            let bps = Double(bytesReceived) / elapsed
            let speedInMbps = (bps / pow(10, 6))
            speedTestCompletionHandler?(speedInMbps, nil)
        }
        else {
            speedTestCompletionHandler?(nil, error)
        }
    }
}
