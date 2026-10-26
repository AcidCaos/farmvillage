import Darwin
import Foundation

@main
struct NativeLogSmoke {
    @MainActor
    static func main() {
        do { try run() }
        catch {
            print("FAIL: \(error.localizedDescription)")
            exit(EXIT_FAILURE)
        }
    }

    @MainActor
    static func run() throws {
        let manager = FileManager.default
        let temporary = manager.temporaryDirectory.appendingPathComponent("FarmVillageLogSmoke-\(UUID().uuidString)", isDirectory: true)
        try manager.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: temporary) }

        let normal = temporary.appendingPathComponent("normal", isDirectory: true)
        let first = try RuntimeController.openLogFiles(in: normal)
        let second = try RuntimeController.openLogFiles(in: normal)
        defer {
            try? first.writer.close(); try? first.reader.close()
            try? second.writer.close(); try? second.reader.close()
        }
        try first.writer.write(contentsOf: Data("A".utf8))
        try second.writer.write(contentsOf: Data("B".utf8))
        guard try String(contentsOf: normal.appendingPathComponent("Logs/wrapper.log"), encoding: .utf8) == "AB",
              try first.reader.read(upToCount: 64) == Data("AB".utf8) else {
            throw SmokeFailure("Independent log writers did not append without clobbering existing data.")
        }
        print("PASS: independent native log writers append and the log reader observes both records")

        let outside = temporary.appendingPathComponent("outside", isDirectory: true)
        try manager.createDirectory(at: outside, withIntermediateDirectories: true)
        let sentinel = outside.appendingPathComponent("wrapper.log")
        try Data("KEEP".utf8).write(to: sentinel)

        let parentLink = temporary.appendingPathComponent("parent-link", isDirectory: true)
        try manager.createDirectory(at: parentLink, withIntermediateDirectories: true)
        try manager.createSymbolicLink(at: parentLink.appendingPathComponent("Logs"), withDestinationURL: outside)
        try expectRejected(parentLink, name: "a Logs directory symlink")

        let leafLink = try dataRoot("leaf-link", under: temporary)
        try manager.createSymbolicLink(at: leafLink.appendingPathComponent("Logs/wrapper.log"), withDestinationURL: sentinel)
        try expectRejected(leafLink, name: "a wrapper.log symlink")

        let hardLink = try dataRoot("hard-link", under: temporary)
        try manager.linkItem(at: sentinel, to: hardLink.appendingPathComponent("Logs/wrapper.log"))
        try expectRejected(hardLink, name: "a wrapper.log hard link")

        let directoryLeaf = try dataRoot("directory-leaf", under: temporary)
        try manager.createDirectory(at: directoryLeaf.appendingPathComponent("Logs/wrapper.log"), withIntermediateDirectories: true)
        try expectRejected(directoryLeaf, name: "a wrapper.log directory")

        let fifoLeaf = try dataRoot("fifo-leaf", under: temporary)
        let fifo = fifoLeaf.appendingPathComponent("Logs/wrapper.log")
        guard mkfifo(fifo.path, 0o600) == 0 else { throw SmokeFailure("Could not create the FIFO fixture.") }
        let start = Date()
        try expectRejected(fifoLeaf, name: "a wrapper.log FIFO")
        guard Date().timeIntervalSince(start) < 1 else { throw SmokeFailure("Opening the malformed log FIFO blocked.") }

        guard try Data(contentsOf: sentinel) == Data("KEEP".utf8) else {
            throw SmokeFailure("A rejected log path changed the external sentinel.")
        }
        print("PASS: all rejected log paths preserved the external sentinel; FIFO rejection did not block")
    }

    static func dataRoot(_ name: String, under temporary: URL) throws -> URL {
        let root = temporary.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: root.appendingPathComponent("Logs"), withIntermediateDirectories: true)
        return root
    }

    @MainActor
    static func expectRejected(_ root: URL, name: String) throws {
        var rejected = false
        do {
            let files = try RuntimeController.openLogFiles(in: root)
            try? files.writer.close(); try? files.reader.close()
        } catch { rejected = true }
        guard rejected else { throw SmokeFailure("Native logging accepted \(name).") }
        print("PASS: native logging rejects \(name)")
    }

    struct SmokeFailure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}
