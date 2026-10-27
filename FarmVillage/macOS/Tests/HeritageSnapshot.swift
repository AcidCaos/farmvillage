import AppKit
import Darwin
import Foundation
import SwiftUI

/// Captures only an owned offscreen window and isolated fixture profiles.
/// This harness never opens a runtime, reads a real farm, or uses the global mouse.
@main
struct HeritageSnapshot {
    @MainActor
    static func main() async {
        do { try await run() }
        catch { print("FAIL: \(error.localizedDescription)"); exit(EXIT_FAILURE) }
    }

    @MainActor
    static func run() async throws {
        guard CommandLine.arguments.count == 2, CommandLine.arguments[1].hasPrefix("/") else {
            throw SnapshotFailure("usage: HeritageSnapshot /absolute/output-directory")
        }
        let manager = FileManager.default
        let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        try manager.createDirectory(at: output, withIntermediateDirectories: true)
        let fixture = manager.temporaryDirectory.appendingPathComponent("FarmVillageHeritageSnapshot-\(UUID().uuidString)", isDirectory: true)
        try manager.createDirectory(at: fixture.appendingPathComponent("saves"), withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: fixture) }
        for (uid, name, xp, gold) in [("1001", "Willow Creek", 13786, 7520), ("1002", "A Very Long Farm Name to Check the Farm Picker", 280, 610)] {
            let save: [String: Any] = ["userInfo": ["player": ["userId": uid, "xp": xp, "gold": gold], "attr": ["name": name],
                                                   "featureOptions": [String: Any](), "worldSummaryData": ["farm": [String: Any]()]],
                                       "flashHotParams": [String: Any](), "world": ["objectsArray": [Any]()]]
            let data = try JSONSerialization.data(withJSONObject: save)
            try data.write(to: fixture.appendingPathComponent("saves/\(uid).json"))
        }
        try manager.createDirectory(at: fixture.appendingPathComponent("venv/bin"), withIntermediateDirectories: true)
        try Data("#!/bin/sh\nexit 0\n".utf8).write(to: fixture.appendingPathComponent("venv/bin/python"))
        try manager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: fixture.appendingPathComponent("venv/bin/python").path)
        try Data("{\"schema\":2}".utf8).write(to: fixture.appendingPathComponent("prepared.json"))

        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        UserDefaults.standard.set(false, forKey: "FarmVillage.LauncherSoundEnabled")
        UserDefaults.standard.set(false, forKey: "FarmVillage.LauncherMotionEnabled")
        let runtime = RuntimeController(dataDirectory: fixture)
        let game = GameWebController()
        let library = LauncherLibrary(dataDirectory: fixture)
        let deadline = Date().addingTimeInterval(5)
        while library.isLoading && Date() < deadline { try await Task.sleep(nanoseconds: 50_000_000) }
        guard library.farms.count == 2, let selected = library.farms.first(where: { $0.id == "1001" }) else {
            throw SnapshotFailure("The isolated farm picker fixture did not load.")
        }
        library.select(selected)
        let window = NSWindow(contentRect: NSRect(x: -5000, y: -5000, width: 1380, height: 900),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "FarmVillage isolated heritage capture"
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: ContentView(runtime: runtime, game: game, library: library))
        window.orderFrontRegardless()
        defer { window.close() }
        for size in [NSSize(width: 1380, height: 900), NSSize(width: 1000, height: 680)] {
            window.setContentSize(size)
            try await Task.sleep(nanoseconds: 700_000_000)
            try capture(window.contentView, to: output.appendingPathComponent("home-\(Int(size.width))x\(Int(size.height)).png"))
        }
        window.setContentSize(NSSize(width: 1380, height: 900))
        NotificationCenter.default.post(name: .farmVillageShowLibrary, object: nil)
        try await Task.sleep(nanoseconds: 700_000_000)
        guard let picker = window.attachedSheet else { throw SnapshotFailure("The farm picker sheet was not presented.") }
        try capture(picker.contentView, to: output.appendingPathComponent("farm-picker.png"))
        // Dismiss through the sheet's Escape key, allowing SwiftUI to clear its binding.
        if let escape = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                                        windowNumber: picker.windowNumber, context: nil, characters: "\u{1b}",
                                        charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53) {
            picker.sendEvent(escape)
        }
        try await Task.sleep(nanoseconds: 500_000_000)
        guard window.attachedSheet == nil else { throw SnapshotFailure("Escape did not dismiss the owned farm picker.") }
        NotificationCenter.default.post(name: .farmVillageShowSettings, object: nil)
        try await Task.sleep(nanoseconds: 700_000_000)
        guard let settings = window.attachedSheet else { throw SnapshotFailure("The settings sheet was not presented.") }
        try capture(settings.contentView, to: output.appendingPathComponent("settings.png"))
        try await dismissSheet(of: window)
        window.close()

        let freshDirectory = fixture.appendingPathComponent("Fresh", isDirectory: true)
        try manager.createDirectory(at: freshDirectory, withIntermediateDirectories: true)
        let freshRuntime = RuntimeController(dataDirectory: freshDirectory)
        let freshLibrary = LauncherLibrary(dataDirectory: freshDirectory)
        let freshWindow = NSWindow(contentRect: NSRect(x: -5000, y: -5000, width: 1000, height: 680),
                                   styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        freshWindow.isReleasedWhenClosed = false
        freshWindow.contentView = NSHostingView(rootView: ContentView(runtime: freshRuntime, game: GameWebController(), library: freshLibrary))
        freshWindow.orderFrontRegardless()
        defer { freshWindow.close() }
        try await Task.sleep(nanoseconds: 700_000_000)
        try capture(freshWindow.contentView, to: output.appendingPathComponent("first-run-1000x680.png"))
        if let enter = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                                       windowNumber: freshWindow.windowNumber, context: nil, characters: "\r",
                                       charactersIgnoringModifiers: "\r", isARepeat: false, keyCode: 36) {
            freshWindow.sendEvent(enter)
        }
        try await Task.sleep(nanoseconds: 700_000_000)
        guard let setup = freshWindow.attachedSheet, !freshRuntime.hasOwnedProcess else {
            throw SnapshotFailure("The native default action did not open Setup without starting a runtime.")
        }
        try capture(setup.contentView, to: output.appendingPathComponent("first-run-setup.png"))
        print("PASS: isolated original-asset launcher captured at 1380×900 and 1000×680, farm picker, Settings, and fresh-profile Setup")
        print("PASS: native Escape dismisses the picker; native Return activates the visible setup button without starting a runtime; no global input used")
    }

    @MainActor
    private static func capture(_ view: NSView?, to destination: URL) throws {
        guard let view else { throw SnapshotFailure("The owned capture view is missing.") }
        view.layoutSubtreeIfNeeded()
        guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
            throw SnapshotFailure("The owned view could not create its capture bitmap.")
        }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        guard let bytes = bitmap.representation(using: .png, properties: [:]) else {
            throw SnapshotFailure("The owned view did not encode a PNG.")
        }
        try bytes.write(to: destination)
    }

    @MainActor
    private static func dismissSheet(of window: NSWindow) async throws {
        guard let sheet = window.attachedSheet else { return }
        if let escape = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                                        windowNumber: sheet.windowNumber, context: nil, characters: "\u{1b}",
                                        charactersIgnoringModifiers: "\u{1b}", isARepeat: false, keyCode: 53) {
            sheet.sendEvent(escape)
        }
        try await Task.sleep(nanoseconds: 500_000_000)
        guard window.attachedSheet == nil else { throw SnapshotFailure("Escape did not dismiss the owned sheet.") }
    }

    struct SnapshotFailure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}
