import AppKit
import Combine
import CoreFoundation
import CryptoKit
import Foundation
import UniformTypeIdentifiers

struct LauncherFarm: Identifiable, Hashable, Sendable {
    let id: String
    let name: String
    let xp: Double
    let gold: Double
    let thumbnailURL: URL?
}

/// Reads only the selected profile and opens farms through the game's normal session login.
@MainActor
final class LauncherLibrary: ObservableObject {
    @Published private(set) var farms: [LauncherFarm] = []
    @Published var selectedFarmID: String?
    @Published private(set) var isLoading = false
    @Published private(set) var isOpening = false
    @Published var isPresentingFarm = false
    @Published var errorMessage: String?

    let dataDirectory: URL
    private let allowsDataAccess: Bool
    private let selectionKey: String
    private var pending: Pending?
    private var operation = UUID()
    private var refreshOperation = UUID()
    private enum Pending { case open(String), chooseCreation, create(String, String), importFile(Data) }
    private struct CreationStyle: Decodable, Sendable {
        let id: String
        let name: String
        static let classic = CreationStyle(id: "classic", name: "Classic farm")
    }

    var selectedFarm: LauncherFarm? { farms.first { $0.id == selectedFarmID } }

    init(dataDirectory: URL, allowsDataAccess: Bool = true) {
        self.dataDirectory = dataDirectory
        self.allowsDataAccess = allowsDataAccess
        let identity = SHA256.hash(data: Data(dataDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        selectionKey = "FarmVillage.LastFarm.\(identity)"
        selectedFarmID = UserDefaults.standard.string(forKey: selectionKey)
        refresh()
    }

    func refresh() {
        guard allowsDataAccess else { return }
        let identifier = UUID()
        refreshOperation = identifier
        isLoading = true
        let directory = dataDirectory
        Task { [weak self] in
            let result = await Task.detached(priority: .userInitiated) {
                Self.readFarms(in: directory)
            }.value
            guard let self, self.refreshOperation == identifier else { return }
            self.farms = result
            if !result.contains(where: { $0.id == self.selectedFarmID }) {
                self.selectedFarmID = result.first?.id
            }
            self.rememberSelection()
            self.isLoading = false
        }
    }

    func select(_ farm: LauncherFarm) {
        guard farms.contains(where: { $0.id == farm.id }) else { return }
        selectedFarmID = farm.id
        rememberSelection()
    }

    func didLoadFarm(uid: String) {
        guard uid.range(of: "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", options: .regularExpression) != nil else { return }
        selectedFarmID = uid
        rememberSelection()
        refresh()
    }

    func showHome() { isPresentingFarm = false; refresh() }

    func returnToFarm(runtime: RuntimeController, game: GameWebController) {
        guard let selectedFarm else {
            createFarm(runtime: runtime, game: game)
            return
        }
        enqueue(.open(selectedFarm.id), runtime: runtime, game: game)
    }

    func createFarm(runtime: RuntimeController, game: GameWebController) {
        guard !isOpening else { return }
        enqueue(.chooseCreation, runtime: runtime, game: game)
    }

    private func presentCreation(styles: [CreationStyle], runtime: RuntimeController, game: GameWebController) {
        let alert = NSAlert()
        alert.messageText = "A new farm, a familiar beginning"
        alert.informativeText = "Choose your farmer name. Your existing farms stay in the farm picker."
        alert.addButton(withTitle: "Create Farm")
        alert.addButton(withTitle: "Cancel")
        let field = NSTextField(string: "Farmer")
        field.frame = NSRect(x: 0, y: 0, width: 320, height: 26)
        field.placeholderString = "Farmer name"
        field.setAccessibilityLabel("Farmer name")
        let picker = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 320, height: 26), pullsDown: false)
        picker.setAccessibilityLabel("Village style")
        for style in styles {
            picker.addItem(withTitle: style.name)
            picker.lastItem?.representedObject = style.id
        }
        if styles.count > 1 {
            let accessory = NSStackView(views: [field, NSTextField(labelWithString: "Village style"), picker])
            accessory.orientation = .vertical
            accessory.alignment = .leading
            accessory.spacing = 8
            accessory.frame = NSRect(x: 0, y: 0, width: 320, height: 84)
            field.widthAnchor.constraint(equalToConstant: 320).isActive = true
            picker.widthAnchor.constraint(equalToConstant: 320).isActive = true
            alert.accessoryView = accessory
        } else {
            alert.accessoryView = field
        }
        let complete: (NSApplication.ModalResponse) -> Void = { [weak self, weak runtime, weak game] result in
            guard result == .alertFirstButtonReturn, let self, let runtime, let game else { return }
            let name = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name.unicodeScalars.count <= 80 else { self.errorMessage = "Use a farmer name between 1 and 80 characters."; return }
            let preset = picker.selectedItem?.representedObject as? String ?? "classic"
            self.enqueue(.create(name, preset), runtime: runtime, game: game)
        }
        if let window = NSApp.keyWindow { alert.beginSheetModal(for: window, completionHandler: complete) }
        else { complete(alert.runModal()) }
    }

    func importFarm(runtime: RuntimeController, game: GameWebController) {
        guard !isOpening else { return }
        let panel = NSOpenPanel()
        panel.title = "Bring your farm home"
        panel.message = "Choose a FarmVillage JSON save. A matching existing farm is never replaced."
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        let complete: (NSApplication.ModalResponse) -> Void = { [weak self, weak runtime, weak game] result in
            guard result == .OK, let self, let runtime, let game, let file = panel.url else { return }
            do {
                let attributes = try file.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
                guard attributes.isRegularFile == true, let size = attributes.fileSize, size <= 64 * 1024 * 1024 else {
                    throw LibraryFailure("Choose a JSON save smaller than 64 MiB.")
                }
                let bytes = try Data(contentsOf: file)
                self.enqueue(.importFile(bytes), runtime: runtime, game: game)
            } catch { self.errorMessage = error.localizedDescription }
        }
        if let window = NSApp.keyWindow { panel.beginSheetModal(for: window, completionHandler: complete) }
        else { panel.begin(completionHandler: complete) }
    }

    func runtimeChanged(runtime: RuntimeController, game: GameWebController) {
        if runtime.phase == .running, pending != nil { finishPending(runtime: runtime, game: game) }
        else if [.failed, .stopping].contains(runtime.phase) {
            operation = UUID(); pending = nil; isOpening = false
            if runtime.phase == .failed { isPresentingFarm = false }
        } else if runtime.phase == .idle { isPresentingFarm = false; refresh() }
    }

    private func enqueue(_ action: Pending, runtime: RuntimeController, game: GameWebController) {
        guard allowsDataAccess, !isOpening else { return }
        guard runtime.phase == .running || runtime.canStart else {
            errorMessage = runtime.isPrepared ? "Wait for the farm to finish stopping, then try again." : "Prepare the local runtime in Settings first."
            return
        }
        errorMessage = nil
        operation = UUID()
        pending = action
        isOpening = true
        if runtime.phase == .running { finishPending(runtime: runtime, game: game) }
        else { runtime.start() }
    }

    private func finishPending(runtime: RuntimeController, game: GameWebController) {
        guard let action = pending else { return }
        pending = nil
        let identifier = operation
        Task { [weak self, weak runtime, weak game] in
            guard let self, let runtime, let game else { return }
            do {
                let uid: String
                switch action {
                case .open(let id): uid = id
                case .chooseCreation:
                    let styles = try await self.creationStyles(runtime: runtime)
                    guard self.operation == identifier, runtime.phase == .running else { return }
                    self.isOpening = false
                    self.presentCreation(styles: styles, runtime: runtime, game: game)
                    return
                case .create(let name, let preset):
                    let value = preset == "classic" ? ["name": name] : ["name": name, "preset": preset]
                    let body = try JSONSerialization.data(withJSONObject: value)
                    uid = try await self.mutate("create", body: body, runtime: runtime)
                case .importFile(let body): uid = try await self.mutate("import", body: body, runtime: runtime)
                }
                guard self.operation == identifier, runtime.phase == .running else { return }
                self.selectedFarmID = uid
                self.rememberSelection()
                game.openFarm(uid: uid, baseURL: runtime.gameURL)
                self.isPresentingFarm = true
                self.isOpening = false
                self.refresh()
            } catch {
                guard self.operation == identifier else { return }
                self.isOpening = false
                self.errorMessage = error.localizedDescription
            }
        }
    }

    private func creationStyles(runtime: RuntimeController) async throws -> [CreationStyle] {
        guard let token = runtime.serverToken else { throw LibraryFailure("The local server is not ready yet.") }
        var request = URLRequest(url: runtime.gameURL.appendingPathComponent("launcher/presets"))
        request.timeoutInterval = 30
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue(token, forHTTPHeaderField: "X-FarmVillage-Token")
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        let session = URLSession(configuration: configuration)
        defer { session.finishTasksAndInvalidate() }
        let (bytes, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode
        // Earlier prepared runtimes still accept the unchanged classic request.
        if status == 404 { return [.classic] }
        struct Presets: Decodable { let presets: [CreationStyle] }
        guard status == 200, let value = try? JSONDecoder().decode(Presets.self, from: bytes),
              value.presets.first?.id == "classic",
              Set(value.presets.map(\.id)).count == value.presets.count else {
            throw LibraryFailure("The village styles could not be loaded. Check Activity and try again.")
        }
        return value.presets
    }

    private func mutate(_ endpoint: String, body: Data, runtime: RuntimeController) async throws -> String {
        guard let token = runtime.serverToken else { throw LibraryFailure("The local server is not ready yet.") }
        var request = URLRequest(url: runtime.gameURL.appendingPathComponent("launcher/\(endpoint)"))
        request.httpMethod = "POST"
        request.httpBody = body
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(token, forHTTPHeaderField: "X-FarmVillage-Token")
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        let session = URLSession(configuration: configuration)
        defer { session.finishTasksAndInvalidate() }
        let (bytes, response) = try await session.data(for: request)
        let value = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any]
        guard (response as? HTTPURLResponse)?.statusCode == 200, let uid = value?["uid"] as? String else {
            throw LibraryFailure(value?["error"] as? String ?? "The farm could not be opened. View Activity for details.")
        }
        if let warning = value?["warning"] as? String { errorMessage = warning }
        return uid
    }

    private func rememberSelection() { UserDefaults.standard.set(selectedFarmID, forKey: selectionKey) }

    nonisolated static func readFarms(in directory: URL) -> [LauncherFarm] {
        let root = directory.standardizedFileURL.resolvingSymlinksInPath()
        let saves = root.appendingPathComponent("saves", isDirectory: true)
        guard saves.resolvingSymlinksInPath() == saves,
              let files = try? FileManager.default.contentsOfDirectory(at: saves, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey], options: [.skipsHiddenFiles]) else { return [] }
        var candidates: [String: [LauncherFarm]] = [:]
        for file in files.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
            let name = file.lastPathComponent.lowercased()
            guard name.hasSuffix(".json"), !name.hasSuffix(".bak.json"), !name.hasSuffix(".backup.json"), !name.hasSuffix(".tmp.json"), !name.hasPrefix("~"),
                  let attributes = try? file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey]),
                  attributes.isRegularFile == true, attributes.isSymbolicLink != true,
                  let size = attributes.fileSize, size <= 64 * 1024 * 1024,
                  let bytes = try? Data(contentsOf: file), let json = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any],
                  let user = json["userInfo"] as? [String: Any], let player = user["player"] as? [String: Any],
                  user["featureOptions"] is [String: Any],
                  let summary = user["worldSummaryData"] as? [String: Any], summary["farm"] is [String: Any],
                  json["flashHotParams"] is [String: Any], let world = json["world"] as? [String: Any],
                  world["objectsArray"] is [[String: Any]],
                  let attr = user["attr"] as? [String: Any], let farmerName = attr["name"] as? String,
                  let rawID = player["userId"], let xp = player["xp"] as? NSNumber, let gold = player["gold"] as? NSNumber,
                  CFGetTypeID(xp) != CFBooleanGetTypeID(), CFGetTypeID(gold) != CFBooleanGetTypeID(),
                  xp.doubleValue.isFinite, gold.doubleValue.isFinite else { continue }
            let uid: String
            if let string = rawID as? String { uid = string }
            else if let number = rawID as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
                    !["f", "d"].contains(String(cString: number.objCType)) { uid = number.stringValue }
            else { continue }
            guard uid.range(of: "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", options: .regularExpression) != nil else { continue }
            let preview = root.appendingPathComponent("Launcher/Previews/\(uid).png")
            let thumbnail = preview.resolvingSymlinksInPath().path.hasPrefix(root.path + "/") && FileManager.default.fileExists(atPath: preview.path) ? preview : nil
            candidates[uid, default: []].append(LauncherFarm(id: uid, name: farmerName, xp: xp.doubleValue, gold: gold.doubleValue, thumbnailURL: thumbnail))
        }
        return candidates.values.compactMap { $0.count == 1 ? $0.first : nil }.sorted {
            $0.name.localizedStandardCompare($1.name) == .orderedAscending
        }
    }
}

private struct LibraryFailure: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}
