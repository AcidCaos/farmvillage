import Foundation

/// Exercises the production offline save reader, without creating an app,
/// touching UserDefaults, starting a server, or reading a user's data directory.
@main
enum LauncherLibrarySmoke {
    static func main() throws {
        let manager = FileManager.default
        let work = manager.temporaryDirectory.appendingPathComponent("FarmVillageLibrarySmoke-\(UUID().uuidString)", isDirectory: true)
        try manager.createDirectory(at: work, withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: work) }
        var count = 0

        func profile(_ label: String) throws -> URL {
            let root = work.appendingPathComponent(label, isDirectory: true)
            try manager.createDirectory(at: root.appendingPathComponent("saves"), withIntermediateDirectories: true)
            return root
        }
        func fixture(_ uid: Any = "farm-1", name: String = "Farmer", xp: Any = 125, gold: Any = 288) -> [String: Any] {
            ["userInfo": ["attr": ["name": name], "player": ["userId": uid, "xp": xp, "gold": gold],
                          "featureOptions": [:], "worldSummaryData": ["farm": [:]]],
             "flashHotParams": [:], "world": ["objectsArray": []]]
        }
        func save(_ json: [String: Any], in root: URL, filename: String = "farm.json") throws {
            let bytes = try JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
            try bytes.write(to: root.appendingPathComponent("saves/\(filename)"))
        }
        func check(_ condition: @autoclosure () -> Bool, _ label: String) throws {
            guard condition() else { throw NSError(domain: "LauncherLibrarySmoke", code: 1, userInfo: [NSLocalizedDescriptionKey: label]) }
            count += 1
            print("PASS \(label)")
        }

        let valid = try profile("valid-legacy-shape")
        try save(fixture(), in: valid)
        let read = LauncherLibrary.readFarms(in: valid)
        try check(read.count == 1 && read[0].id == "farm-1" && read[0].name == "Farmer" && read[0].xp == 125 && read[0].gold == 288,
                  "minimal legacy-compatible structural save exposes genuine metadata")

        let numeric = try profile("integer-id")
        try save(fixture(42), in: numeric)
        try check(LauncherLibrary.readFarms(in: numeric).map(\.id) == ["42"], "integer IDs remain supported")

        for (label, json) in [
            ("boolean-xp", fixture(xp: true)), ("boolean-gold", fixture(gold: false)),
            ("boolean-id", fixture(true)), ("fractional-id", fixture(42.5)),
            ("path-id", fixture("../escape")),
        ] {
            let root = try profile(label)
            try save(json, in: root)
            try check(LauncherLibrary.readFarms(in: root).isEmpty, "reject \(label)")
        }

        let malformed = try profile("malformed")
        try Data("{not valid JSON}".utf8).write(to: malformed.appendingPathComponent("saves/bad.json"))
        try check(LauncherLibrary.readFarms(in: malformed).isEmpty, "corrupt JSON is skipped")

        let backups = try profile("backup-exclusion")
        for filename in ["one.bak.json", "two.backup.json", "three.tmp.json", "~four.json", ".hidden.json"] {
            try save(fixture(filename), in: backups, filename: filename)
        }
        try check(LauncherLibrary.readFarms(in: backups).isEmpty, "backup, temporary, and hidden files are excluded")

        let duplicate = try profile("duplicate-id")
        try save(fixture("same-id", name: "Alpha"), in: duplicate, filename: "a.json")
        try save(fixture("same-id", name: "Beta"), in: duplicate, filename: "b.json")
        try check(LauncherLibrary.readFarms(in: duplicate).isEmpty, "duplicate UID files never choose an ambiguous farm")

        let sorted = try profile("name-sort")
        try save(fixture("b", name: "Ben"), in: sorted, filename: "a.json")
        try save(fixture("a", name: "Amy"), in: sorted, filename: "z.json")
        try check(LauncherLibrary.readFarms(in: sorted).map(\.name) == ["Amy", "Ben"], "farm names determine picker order")

        let missingWorld = try profile("missing-world")
        var noWorld = fixture()
        noWorld.removeValue(forKey: "world")
        try save(noWorld, in: missingWorld)
        try check(LauncherLibrary.readFarms(in: missingWorld).isEmpty, "missing required world structure is skipped")

        let invalidObjects = try profile("invalid-object-array")
        var wrongObjects = fixture()
        wrongObjects["world"] = ["objectsArray": ["not an object"]]
        try save(wrongObjects, in: invalidObjects)
        try check(LauncherLibrary.readFarms(in: invalidObjects).isEmpty, "world object entries must be dictionaries")

        let outside = try profile("outside-target")
        try save(fixture("outside"), in: outside)
        let leafLink = try profile("leaf-symlink")
        try manager.createSymbolicLink(at: leafLink.appendingPathComponent("saves/link.json"),
                                       withDestinationURL: outside.appendingPathComponent("saves/farm.json"))
        try check(LauncherLibrary.readFarms(in: leafLink).isEmpty, "save symlinks are skipped")

        let directoryLink = try profile("directory-symlink")
        try manager.removeItem(at: directoryLink.appendingPathComponent("saves"))
        try manager.createSymbolicLink(at: directoryLink.appendingPathComponent("saves"),
                                       withDestinationURL: outside.appendingPathComponent("saves"))
        try check(LauncherLibrary.readFarms(in: directoryLink).isEmpty, "saves directory cannot redirect outside selected profile")

        let previews = try profile("preview-confinement")
        try save(fixture(), in: previews)
        try manager.createDirectory(at: previews.appendingPathComponent("Launcher/Previews"), withIntermediateDirectories: true)
        let externalImage = work.appendingPathComponent("external.png")
        try Data("not important image bytes".utf8).write(to: externalImage)
        try manager.createSymbolicLink(at: previews.appendingPathComponent("Launcher/Previews/farm-1.png"), withDestinationURL: externalImage)
        try check(LauncherLibrary.readFarms(in: previews).first?.thumbnailURL == nil, "thumbnail symlinks cannot expose files outside profile")

        let oversized = try profile("oversized")
        let large = oversized.appendingPathComponent("saves/large.json")
        try Data().write(to: large)
        let handle = try FileHandle(forWritingTo: large)
        try handle.truncate(atOffset: 64 * 1024 * 1024 + 1)
        try handle.close()
        try check(LauncherLibrary.readFarms(in: oversized).isEmpty, "oversized save is skipped before reading")
        try check(LauncherLibrary.readFarms(in: work.appendingPathComponent("does-not-exist")).isEmpty, "unprepared profile has an empty library")
        print("Launcher library metadata: \(count) checks passed. No app or server was launched.")
    }
}
