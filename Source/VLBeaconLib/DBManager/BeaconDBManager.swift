//
//  BeaconDBManager.swift
//  VLBeacon
//
//  Created by NEXGEN on 29/03/23.
//

import Foundation
@_implementationOnly import SQLite3

final class BeaconDBManager {
    /*!
     * @brief Path the documents directory.
     */
    var documentsDirectory: String = ""
    /*!
     * @brief Name of the database file.
     */
    var databaseFilename: String = ""
    /*!
     * @brief Results fetched after running the query.
     */
    var arrResults = [Any]()
    var results:Array<Dictionary<String,String>>=[]
    var arrColumnNames = [Any]()
    var affectedRows : Int = 01
    var lastInsertedRowID : Double  = 01
}

// MARK: - Internal methods
extension BeaconDBManager {
    func intializeData( dbFilename: String, tableName: String, tableColumnsQuery: String)  {
        // Set the documents directory path to the documentsDirectory property.
        let paths: [String] = NSSearchPathForDirectoriesInDomains(.documentDirectory, .userDomainMask, true)
        documentsDirectory = paths[0]
        // Keep the database filename.
        databaseFilename = dbFilename
        // Create database file in the documents directory if necessary.
        createDB(dbFileName: dbFilename,tableName: tableName,tableColumnsQuery: tableColumnsQuery)
    }
    
    func createDB(dbFileName: String, tableName: String, tableColumnsQuery: String) {
        //Build the path to keep the database
        let _database: String = URL(fileURLWithPath: documentsDirectory).appendingPathComponent(dbFileName).absoluteString
        let fileMngr = FileManager.default
        //Check if file already exists. If yes, do not create new.
        guard fileMngr.fileExists(atPath: _database) == false else { return }
        // Create a sqlite object.
        var _DB: OpaquePointer?
        //            let dbpath = _database.utf8
        if sqlite3_open(_database, &_DB) == SQLITE_OK {
            var errorMassage:String = ""
            
            if let error = sqlite3_errmsg(_DB){
                errorMassage = String(cString: error)
            }
            
            let sql_statement = "CREATE TABLE IF NOT EXISTS \(tableName) (\(tableColumnsQuery))"
            
            if sqlite3_exec(_DB, sql_statement, nil, nil, nil) != SQLITE_OK {
#if DEBUG
                debugPrint("error creating table: \(errorMassage)")
#endif
            }
            sqlite3_close(_DB)
        } else {
#if DEBUG
            debugPrint("Error to open/create the table")
#endif
        }
    }
    
    func loadData(fromDB query: String) -> Array<Dictionary<String,String>> {
        // Run the query and indicate that is not executable.
        // The query string is converted to a char* object.
        runQuery(query, isQueryExecutable: false)
        // Returned the loaded results.
        return (results)
    }
    
    func execute(_ query: String) {
        // Run the query and indicate that is executable.
        runQuery(query, isQueryExecutable: true)
    }
    
    /// Adds a column to an existing table when missing (safe for already-migrated DBs).
    func addColumnIfNeeded(tableName: String, columnName: String, columnType: String) {
        guard !documentsDirectory.isEmpty, !databaseFilename.isEmpty else { return }
        
        // Match path style used by `runQuery` / `createDB` so we migrate the same DB file.
        let databasePath = URL(fileURLWithPath: documentsDirectory)
            .appendingPathComponent(databaseFilename)
            .absoluteString
        
        var sqlite3Database: OpaquePointer?
        guard sqlite3_open(databasePath, &sqlite3Database) == SQLITE_OK else { return }
        defer { sqlite3_close(sqlite3Database) }
        
        guard tableHasColumn(db: sqlite3Database, tableName: tableName, columnName: columnName) == false else {
            return
        }
        
        let alterSQL = "ALTER TABLE \(tableName) ADD COLUMN \(columnName) \(columnType)"
        if sqlite3_exec(sqlite3Database, alterSQL, nil, nil, nil) != SQLITE_OK {
#if DEBUG
            let message = sqlite3_errmsg(sqlite3Database).map { String(cString: $0) } ?? "unknown"
            debugPrint("DB Error adding column \(columnName): \(message)")
#endif
        }
    }
}

// MARK: - Private methods
private extension BeaconDBManager {
    func tableHasColumn(db: OpaquePointer?, tableName: String, columnName: String) -> Bool {
        let pragmaSQL = "PRAGMA table_info(\(tableName))"
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, pragmaSQL, -1, &statement, nil) == SQLITE_OK else {
            return false
        }
        defer { sqlite3_finalize(statement) }
        
        while sqlite3_step(statement) == SQLITE_ROW {
            // PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
            if let nameCString = sqlite3_column_text(statement, 1) {
                let existingName = String(cString: nameCString)
                if existingName == columnName {
                    return true
                }
            }
        }
        return false
    }
    
    func runQuery(_ query: String, isQueryExecutable queryExecutable: Bool) {
        // Create a sqlite object.
        var sqlite3Database: OpaquePointer?
        // Set the database file path.
        let databasePath: String = URL(fileURLWithPath: documentsDirectory).appendingPathComponent(databaseFilename).absoluteString
        // Initialize the results array.
        if !results.isEmpty {
            results.removeAll()
            // arrResults = nil
        }
        
        arrResults = [Any]()
        // Initialize the column names array.
        if !arrColumnNames.isEmpty {
            arrColumnNames.removeAll()
            //arrColumnNames = nil
        }
        
        //var result:Array<Dictionary<String,AnyObject>>=[]
        arrColumnNames = [Any]()
        // Open the database.
        //  let openDatabaseResult: Bool = sqlite3_open(databasePath, &sqlite3Database)
        if sqlite3_open(databasePath, &sqlite3Database) == SQLITE_OK {
            // Declare a sqlite3_stmt object in which will be stored the query after having been compiled into a SQLite statement.
            var compiledStatement: OpaquePointer?
            // Load all data from database to memory.
            //  let prepareStatementResult: Bool = sqlite3_prepare_v2(sqlite3Database, query, -1, &compiledStatement, nil)
            if sqlite3_prepare_v2(sqlite3Database, query, -1, &compiledStatement, nil) == SQLITE_OK {
                // Check if the query is non-executable.
                if !queryExecutable {
                    // In this case data must be loaded from the database.
                    // Declare an array to keep the data for each fetched row.
                    var dict=Dictionary<String, String>()
                    // Loop through the results and add them to the results array row by row.
                    while sqlite3_step(compiledStatement) == SQLITE_ROW {
                        // Initialize the mutable array that will contain the data of a fetched row.
                        // arrDataRow = [String : AnyObject]
                        // Get the total number of columns.
                        let totalColumns: Int = Int(sqlite3_column_count(compiledStatement))
                        // Go through all columns and fetch each column data.
                        for i in 0..<totalColumns {
                            // Convert the column data to text (characters).
                            let strF=sqlite3_column_name(compiledStatement, Int32(i))
                            let strV = sqlite3_column_text(compiledStatement, Int32(i))
                            
                            guard let strF else { continue }
                            let rFiled = String(cString: strF)
                            let rValue = strV.map { String(cString: $0) } ?? ""
                            dict[rFiled] = rValue
                        }
                        
                        results.insert(dict , at: results.count)
                        
                    }
                    // Store each fetched data row in the results array, but first check if there is actually data.
                } else {
                    // This is the case of an executable query (insert, update, ...).
                    // Execute the query.
                    if SQLITE_DONE == sqlite3_step(compiledStatement) {
                        // Keep the affected rows.
                        affectedRows = Int(sqlite3_changes(sqlite3Database))
                        // Keep the last inserted row ID.
                        //lastInsertedRowID = Double(sqlite3_last_insert_rowid(sqlite3Database))
                    } else {
                        // If could not execute the query show the error message on the debugger.
#if DEBUG
                        debugPrint("DB Error: \(String(describing: sqlite3_errmsg(sqlite3Database))) \(query)")
#endif
                    }
                }
            }
            
            sqlite3_finalize(compiledStatement)
        }
        
        sqlite3_close(sqlite3Database)
    }
}
