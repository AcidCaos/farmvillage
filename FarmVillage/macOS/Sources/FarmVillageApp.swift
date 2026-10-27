import AppKit
import SwiftUI

@main
@MainActor
struct FarmVillageApp: App {
    @NSApplicationDelegateAdaptor(FarmVillageAppDelegate.self) private var appDelegate
    @StateObject private var runtime: RuntimeController
    @StateObject private var game: GameWebController
    @StateObject private var library: LauncherLibrary

    init() {
        let controller = RuntimeController()
        _runtime = StateObject(wrappedValue: controller)
        _game = StateObject(wrappedValue: GameWebController())
        _library = StateObject(wrappedValue: LauncherLibrary(dataDirectory: controller.dataDirectory, allowsDataAccess: controller.isConfigured))
    }

    var body: some Scene {
        Window("FarmVillage", id: "farm") {
            ContentView(runtime: runtime, game: game, library: library)
                .frame(minWidth: 1000, minHeight: 680)
                .onAppear { appDelegate.runtime = runtime }
        }
        .defaultSize(width: 1380, height: 900)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandGroup(replacing: .appSettings) {
                Button("Settings…") { NotificationCenter.default.post(name: .farmVillageShowSettings, object: nil) }
                    .keyboardShortcut(",", modifiers: .command)
            }
            CommandMenu("Farm") {
                Button("Return to Farm") { library.returnToFarm(runtime: runtime, game: game) }
                    .keyboardShortcut("r", modifiers: [.command, .shift])
                    .disabled(library.isOpening || library.isPresentingFarm || (!runtime.canStart && runtime.phase != .running))
                Button("Choose Farm…") { NotificationCenter.default.post(name: .farmVillageShowLibrary, object: nil) }
                    .keyboardShortcut("l", modifiers: [.command, .shift])
                    .disabled(library.isOpening)
                Button("Create Farm…") { library.createFarm(runtime: runtime, game: game) }
                    .disabled(library.isOpening || library.isPresentingFarm || (!runtime.canStart && runtime.phase != .running))
                Button("Import Farm…") { library.importFarm(runtime: runtime, game: game) }
                    .disabled(library.isOpening || library.isPresentingFarm || (!runtime.canStart && runtime.phase != .running))
                Divider()
                Button(runtime.phase == .preparing ? "Cancel Setup" : "Stop Farm") { runtime.stop() }
                    .disabled(!runtime.canStop)
                Divider()
                Button("Reload Current View") { NotificationCenter.default.post(name: Notification.Name("FarmVillage.ReloadCurrentView"), object: nil) }
                    .keyboardShortcut("r", modifiers: .command)
                    .disabled(runtime.phase != .running)
            }
            CommandMenu("Tools") {
                Button("God Barn") { NotificationCenter.default.post(name: .farmVillageShowGodBarn, object: nil) }
                    .disabled(runtime.phase != .running || !library.isPresentingFarm || game.isLoading || game.loadedFarmID == nil || game.loadedFarmID != library.selectedFarmID)
                Button("Prepare Runtime") { runtime.prepare() }
                    .disabled(!runtime.canPrepare)
                Button("Show Farm Data in Finder") { runtime.revealData() }
                Button("Show Log File in Finder") { runtime.revealLog() }
            }
            CommandGroup(after: .windowSize) {
                Button("Toggle Full Screen") { NSApp.keyWindow?.toggleFullScreen(nil) }
                    .keyboardShortcut("f", modifiers: [.control, .command])
            }
            CommandGroup(replacing: .help) {
                Button("FarmVillage on GitHub") {
                    NSWorkspace.shared.open(URL(string: "https://github.com/AcidCaos/farmvillage")!)
                }
                Button("About Ruffle Compatibility") {
                    NSWorkspace.shared.open(URL(string: "https://ruffle.rs/compatibility/")!)
                }
            }
        }
    }
}

@MainActor
final class FarmVillageAppDelegate: NSObject, NSApplicationDelegate {
    weak var runtime: RuntimeController?
    private var awaitingTermination = false

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let runtime, runtime.hasOwnedProcess else { return .terminateNow }
        if !awaitingTermination {
            awaitingTermination = true
            runtime.shutdown { sender.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
}
