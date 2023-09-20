//
//  Logger.swift
//  VLBeaconLib
//
//  Created by NEXGEN on 21/06/23.
//

import Foundation

/// Enum which maps an appropiate symbol which added as prefix for each log message
///
/// - error: Log type error
/// - info: Log type info
/// - debug: Log type debug
/// - verbose: Log type verbose
/// - warning: Log type warning
/// - severe: Log type severe
enum LogEvent: String {
    case e = "[‼️]" // error
    case i = "[ℹ️]" // info
    case d = "[💬]" // debug
    case v = "[🔬]" // verbose
    case w = "[⚠️]" // warning
    case s = "[🔥]" // severe
}


/// Wrapping Swift.print() within DEBUG flag
///
/// - Note: *print()* might cause [security vulnerabilities](https://codifiedsecurity.com/mobile-app-security-testing-checklist-ios/)
///
/// - Parameter object: The object which is to be logged
///
class Log {
    
    static let shared = Log()
    private init(){}
    
    var dateFormat = "yyyy-MM-dd hh:mm:ssSSS"
    var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = dateFormat
        formatter.locale = Locale.current
        formatter.timeZone = TimeZone.current
        return formatter
    }
    
    internal var isLoggingEnabled: Bool = false
    
    private func print(_ object: Any) {
        // Only allowing in DEBUG mode
        #if RELEASE
        #else
        Swift.print(object)
        #endif
    }


    
    // MARK: - Loging methods
    
    
    /// Logs error messages on console with prefix [‼️]
    ///
    /// - Parameters:
    ///   - object: Object or message to be logged
    ///   - filename: File name from where loggin to be done
    ///   - line: Line number in file from where the logging is done
    ///   - column: Column number of the log message
    ///   - funcName: Name of the function from where the logging is done
    func e( _ object: Any, filename: String = #file, line: Int = #line, column: Int = #column, funcName: String = #function, detailedLog: Bool = false) {
        if isLoggingEnabled {
            if detailedLog {
                print("\(Date().toString()) \(LogEvent.e.rawValue)[\(sourceFileName(filePath: filename))]:\(line) \(column) \(funcName) -> \(object)")
            } else {
                print("\(Date().toString()) \(LogEvent.e.rawValue)[\(sourceFileName(filePath: filename))]: -> \(object)")
            }
        }
    }
    
    /// Logs info messages on console with prefix [ℹ️]
    ///
    /// - Parameters:
    ///   - object: Object or message to be logged
    ///   - filename: File name from where loggin to be done
    ///   - line: Line number in file from where the logging is done
    ///   - column: Column number of the log message
    ///   - funcName: Name of the function from where the logging is done
    func i ( _ object: Any, filename: String = #file, line: Int = #line, column: Int = #column, funcName: String = #function, detailedLog: Bool = false) {
        if isLoggingEnabled {
            if detailedLog {
                print("\(Date().toString()) \(LogEvent.i.rawValue)[\(sourceFileName(filePath: filename))]:\(line) \(column) \(funcName) -> \(object)")
            } else {
                print("\(Date().toString()) \(LogEvent.i.rawValue)[\(sourceFileName(filePath: filename))]: -> \(object)")
            }
            
        }
    }
    
    /// Logs debug messages on console with prefix [💬]
    ///
    /// - Parameters:
    ///   - object: Object or message to be logged
    ///   - filename: File name from where loggin to be done
    ///   - line: Line number in file from where the logging is done
    ///   - column: Column number of the log message
    ///   - funcName: Name of the function from where the logging is done
    func d( _ object: Any, filename: String = #file, line: Int = #line, column: Int = #column, funcName: String = #function, detailedLog: Bool = false) {
        if isLoggingEnabled {
            if detailedLog {
                print("\(Date().toString()) \(LogEvent.d.rawValue)[\(sourceFileName(filePath: filename))]:\(line) \(column) \(funcName) -> \(object)")
            } else {
                print("\(Date().toString()) \(LogEvent.d.rawValue)[\(sourceFileName(filePath: filename))] -> \(object)")
            }
        }
    }
    
    /// Logs messages verbosely on console with prefix [🔬]
    ///
    /// - Parameters:
    ///   - object: Object or message to be logged
    ///   - filename: File name from where loggin to be done
    ///   - line: Line number in file from where the logging is done
    ///   - column: Column number of the log message
    ///   - funcName: Name of the function from where the logging is done
    func v( _ object: Any, filename: String = #file, line: Int = #line, column: Int = #column, funcName: String = #function, detailedLog: Bool = false) {
        if isLoggingEnabled {
            if detailedLog {
            print("\(Date().toString()) \(LogEvent.v.rawValue)[\(sourceFileName(filePath: filename))]:\(line) \(column) \(funcName) -> \(object)")
            } else {
                print("\(Date().toString()) \(LogEvent.v.rawValue)[\(sourceFileName(filePath: filename))]: -> \(object)")
            }
        }
    }
    
    /// Logs warnings verbosely on console with prefix [⚠️]
    ///
    /// - Parameters:
    ///   - object: Object or message to be logged
    ///   - filename: File name from where loggin to be done
    ///   - line: Line number in file from where the logging is done
    ///   - column: Column number of the log message
    ///   - funcName: Name of the function from where the logging is done
    func w( _ object: Any, filename: String = #file, line: Int = #line, column: Int = #column, funcName: String = #function, detailedLog: Bool = false) {
        if isLoggingEnabled {
            if detailedLog {
            print("\(Date().toString()) \(LogEvent.w.rawValue)[\(sourceFileName(filePath: filename))]:\(line) \(column) \(funcName) -> \(object)")
            } else {
                print("\(Date().toString()) \(LogEvent.w.rawValue)[\(sourceFileName(filePath: filename))]: -> \(object)")
            }
        }
    }
    
    /// Logs severe events on console with prefix [🔥]
    ///
    /// - Parameters:
    ///   - object: Object or message to be logged
    ///   - filename: File name from where loggin to be done
    ///   - line: Line number in file from where the logging is done
    ///   - column: Column number of the log message
    ///   - funcName: Name of the function from where the logging is done
    func s( _ object: Any, filename: String = #file, line: Int = #line, column: Int = #column, funcName: String = #function, detailedLog: Bool = false) {
        if isLoggingEnabled {
            if detailedLog {
            print("\(Date().toString()) \(LogEvent.s.rawValue)[\(sourceFileName(filePath: filename))]:\(line) \(column) \(funcName) -> \(object)")
            } else {
                print("\(Date().toString()) \(LogEvent.d.rawValue)[\(sourceFileName(filePath: filename))] -> \(object)")
            }
        }
    }
    
    
    /// Extract the file name from the file path
    ///
    /// - Parameter filePath: Full file path in bundle
    /// - Returns: File Name with extension
    private func sourceFileName(filePath: String) -> String {
        let components = filePath.components(separatedBy: "/")
        return components.isEmpty ? "" : components.last!
    }
}

internal extension Date {
    func toString() -> String {
        return Log.shared.dateFormatter.string(from: self as Date)
    }
}
