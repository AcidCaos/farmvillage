import AppKit
import SwiftUI

private enum LauncherSheet: String, Identifiable {
    case settings, farms
    var id: String { rawValue }
}

private enum LauncherSettingsTab: String { case general, setup, activity }

@MainActor
struct ContentView: View {
    @ObservedObject var runtime: RuntimeController
    @ObservedObject var game: GameWebController
    @ObservedObject var library: LauncherLibrary
    @StateObject private var barn = GameWebController()
    @StateObject private var audio = HeritageAudio()
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("FarmVillage.LauncherMotionEnabled") private var motionEnabled = true
    @AppStorage("FarmVillage.PlaybackVolume") private var playbackVolume = 0.65
    @State private var sheet: LauncherSheet?
    @State private var settingsTab: LauncherSettingsTab = .general
    @State private var isEditing = false
    @State private var isLeavingBarn = false

    private var presentsGame: Bool { runtime.phase == .running && library.isPresentingFarm }
    private var isBusy: Bool { runtime.isBusy || library.isLoading || library.isOpening }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            if runtime.phase == .running && isEditing { godBarnContent }
            else if presentsGame { gameContent }
            else { welcomeContent }
        }
        .background(HeritageTheme.paper)
        .preferredColorScheme(.light)
        .tint(HeritageTheme.grass)
        .sheet(item: $sheet) { selection in
            switch selection {
            case .settings: settingsSheet
            case .farms: farmLibrarySheet
            }
        }
        .onAppear {
            library.refresh()
            updateAudio()
        }
        .onDisappear { audio.setActive(false) }
        .onChange(of: scenePhase) { _, _ in updateAudio() }
        .onChange(of: library.isPresentingFarm) { _, _ in updateAudio() }
        .onChange(of: playbackVolume) { _, value in game.setVolume(value) }
        .onChange(of: runtime.phase) { _, phase in
            library.runtimeChanged(runtime: runtime, game: game)
            isEditing = false
            if phase == .running {
                game.errorMessage = nil
                barn.errorMessage = nil
            } else if !runtime.isBusy { library.refresh() }
            updateAudio()
        }
        .onReceive(NotificationCenter.default.publisher(for: .farmVillageShowSettings)) { _ in
            settingsTab = .general; sheet = .settings
        }
        .onReceive(NotificationCenter.default.publisher(for: .farmVillageShowLibrary)) { _ in showLibrary() }
        .onReceive(NotificationCenter.default.publisher(for: .farmVillageShowGodBarn)) { _ in openGodBarn() }
        .onReceive(NotificationCenter.default.publisher(for: .farmVillageReloadCurrentView)) { _ in
            if isEditing { barn.reload() } else if presentsGame { game.reload() }
        }
        .alert("FarmVillage needs attention", isPresented: Binding(
            get: { runtime.errorMessage != nil || library.errorMessage != nil },
            set: { if !$0 { runtime.dismissError(); library.errorMessage = nil } }
        )) {
            if runtime.errorMessage != nil {
                Button("Show Details") { settingsTab = .activity; sheet = .settings; runtime.dismissError() }
            }
            Button("OK", role: .cancel) { runtime.dismissError(); library.errorMessage = nil }
        } message: { Text(runtime.errorMessage ?? library.errorMessage ?? "") }
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            Text("FarmVillage").font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(HeritageTheme.ink)
            if presentsGame || isEditing {
                Divider().frame(height: 16)
                if isEditing {
                    Text("God Barn").font(.system(size: 12, weight: .medium))
                    Text("Farm paused while editing").font(.caption).foregroundStyle(.secondary)
                } else {
                    Text(library.selectedFarm?.name ?? "Your farm").font(.system(size: 12))
                        .lineLimit(1).truncationMode(.middle)
                }
            }
            Spacer()
            if presentsGame && !isEditing {
                Image(systemName: playbackVolume == 0 ? "speaker.slash" : "speaker.wave.2")
                    .foregroundStyle(HeritageTheme.mutedInk).accessibilityHidden(true)
                Slider(value: $playbackVolume, in: 0...1)
                    .frame(width: 88).accessibilityLabel("Game volume")
                    .help("Game volume · use the in-game music and sound buttons to choose what plays")
            }
            if presentsGame || isEditing {
                if isEditing {
                    Button("Return to Farm", systemImage: "arrow.turn.up.left") {
                        isEditing = false
                        updateAudio()
                    }
                    .help("Load your farm with the latest saved changes")
                } else {
                    Button("Choose Farm", systemImage: "house", action: showLibrary)
                }
                Menu {
                    Button("God Barn…", action: openGodBarn)
                        .disabled(game.isLoading || game.loadedFarmID == nil || game.loadedFarmID != library.selectedFarmID)
                    Button("Send Free Gifts…") {
                        captureFarmPreview()
                        game.navigate(to: runtime.gameURL.appendingPathComponent("sn_app_url/gifts.php"))
                    }
                    .disabled(isEditing || game.isLoading || game.loadedFarmID == nil)
                    Button(isEditing ? "Reload God Barn" : "Reload Farm") {
                        if isEditing { barn.reload() } else { game.reload() }
                    }
                    Divider()
                    Button("Settings…") { settingsTab = .general; sheet = .settings }
                    Button("Show Activity…") { settingsTab = .activity; sheet = .settings }
                    Divider()
                    Button("Stop Farm") { runtime.stop() }.disabled(!runtime.canStop)
                } label: { Label("Tools", systemImage: "wrench.and.screwdriver") }
                .menuStyle(.borderlessButton).fixedSize()
            } else {
                if runtime.isBusy || library.isOpening {
                    Button("Show Progress") { settingsTab = .activity; sheet = .settings }
                }
                Button {
                    audio.isEnabled.toggle()
                } label: { Image(systemName: audio.isEnabled ? "speaker.wave.2" : "speaker.slash") }
                    .help(audio.isEnabled ? "Mute launcher ambience" : "Enable original barnyard ambience")
                    .accessibilityLabel(audio.isEnabled ? "Mute launcher ambience" : "Enable launcher ambience")
                    .accessibilityValue(audio.isEnabled ? "On" : "Off")
                Button { settingsTab = .general; sheet = .settings } label: { Image(systemName: "gearshape") }
                    .help("Settings").accessibilityLabel("Settings")
            }
        }
        .buttonStyle(.borderless)
        .padding(.leading, 80).padding(.trailing, 18).frame(height: 48)
        .background(HeritageTheme.paper.opacity(0.98))
        .overlay(alignment: .bottom) {
            Rectangle().fill(HeritageTheme.wood.opacity(0.65)).frame(height: 2)
                .accessibilityHidden(true).allowsHitTesting(false)
        }
    }

    private var welcomeContent: some View {
        GeometryReader { geometry in
            ZStack {
                HeritageFarmScene(animated: motionEnabled && !systemReduceMotion && scenePhase == .active)
                ScrollView {
                    VStack(spacing: 17) {
                        if HeritageTheme.image("farmville-logo.png") != nil {
                            HeritageImage(name: "farmville-logo.png")
                                .frame(width: 335, height: 80).padding(.horizontal, 16).padding(.vertical, 8)
                                .background(.white, in: RoundedRectangle(cornerRadius: 6))
                        } else {
                            Text("FarmVille").font(HeritageTheme.displayFont(64)).foregroundStyle(HeritageTheme.wood)
                        }
                        VStack(spacing: 6) {
                            Text("Welcome home, farmer.")
                                .font(HeritageTheme.displayFont(34)).foregroundStyle(HeritageTheme.ink)
                            Text("A little patch of the good old days.")
                                .font(HeritageTheme.bodyFont(14)).foregroundStyle(HeritageTheme.mutedInk)
                        }
                        welcomeFarmPanel.frame(maxWidth: 440)
                        HStack(spacing: 20) {
                            Button("Create a farm") { audio.playClick(); library.createFarm(runtime: runtime, game: game) }
                            Button("Import a farm…") { audio.playClick(); library.importFarm(runtime: runtime, game: game) }
                        }
                        .font(.system(size: 12, weight: .medium)).buttonStyle(.plain)
                        .foregroundStyle(HeritageTheme.ink).disabled(isBusy)
                        Spacer(minLength: 12)
                        HStack(spacing: 6) {
                            Text("FarmVillage preservation project")
                            Text("·")
                            Button("About & credits") { settingsTab = .general; sheet = .settings }
                                .buttonStyle(.plain).underline()
                        }
                        .font(.system(size: 10)).foregroundStyle(HeritageTheme.ink.opacity(0.85))
                        .padding(.bottom, 15)
                    }
                    .padding(.top, max(14, min(40, (geometry.size.height - 610) / 3)))
                    .padding(.horizontal, 26)
                    .frame(maxWidth: .infinity, minHeight: geometry.size.height)
                }
            }
        }
    }

    private var welcomeFarmPanel: some View {
        HeritagePanel {
            VStack(spacing: 15) {
                if runtime.isBusy || library.isOpening {
                    HStack(spacing: 12) {
                        ProgressView().controlSize(.small)
                        Text(library.isOpening && !runtime.isBusy ? "Opening your farm" : runtime.phase.title)
                            .font(HeritageTheme.headingFont(19))
                    }
                    Text(runtime.message).font(.system(size: 12)).lineSpacing(3)
                        .multilineTextAlignment(.center).foregroundStyle(HeritageTheme.mutedInk)
                    Button("View progress") { settingsTab = .activity; sheet = .settings }
                    if runtime.canStop {
                        Button(runtime.phase == .preparing ? "Cancel setup" : "Cancel") { runtime.stop() }
                            .font(.caption)
                    }
                } else {
                    if let farm = library.selectedFarm {
                        HStack(spacing: 14) {
                            farmPortrait(farm: farm, size: 66)
                            VStack(alignment: .leading, spacing: 7) {
                                Text("YOUR FARM").font(.system(size: 9, weight: .bold)).tracking(1.5)
                                    .foregroundStyle(HeritageTheme.mutedInk)
                                Text(farm.name).font(HeritageTheme.headingFont(23))
                                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                                HStack(spacing: 5) {
                                    HeritageImage(name: "xp-star.png").frame(width: 17, height: 18)
                                    Text("\(farm.xp.formatted()) XP").font(.system(size: 12, weight: .medium))
                                }
                            }
                            Spacer(minLength: 0)
                        }
                    } else {
                        HeritageImage(name: "red-barn-icon.png").frame(width: 64, height: 64)
                        Text(runtime.isPrepared ? "Your farm is waiting." : "Let’s bring the farm home.")
                            .font(HeritageTheme.headingFont(22)).multilineTextAlignment(.center)
                        Text(runtime.isPrepared ? "Create a farm or bring back a saved village." : "Set up once, then return whenever you like.")
                            .font(.system(size: 12)).foregroundStyle(HeritageTheme.mutedInk)
                    }
                    if let error = library.errorMessage {
                        Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)
                    }
                    if runtime.phase == .failed {
                        Text(runtime.message).font(.caption).foregroundStyle(HeritageTheme.mutedInk)
                            .multilineTextAlignment(.center)
                    }
                    HeritagePrimaryButton(title: primaryTitle, disabled: library.isLoading, defaultAction: sheet == nil) {
                        audio.playClick()
                        if !runtime.isPrepared { settingsTab = .setup; sheet = .settings }
                        else if library.selectedFarm == nil { library.createFarm(runtime: runtime, game: game) }
                        else { library.returnToFarm(runtime: runtime, game: game) }
                    }
                    if !library.farms.isEmpty {
                        Button(library.farms.count == 1 ? "Manage your farm" : "Choose another farm (\(library.farms.count))", action: showLibrary)
                            .buttonStyle(.plain).font(.system(size: 12, weight: .medium)).underline()
                    }
                }
            }
            .foregroundStyle(HeritageTheme.ink).padding(27)
            .frame(maxWidth: .infinity)
        }
    }

    private var primaryTitle: String {
        if !runtime.isPrepared { return "Set Up FarmVillage" }
        return library.selectedFarm == nil ? "Create Your Farm" : "Return to Your Farm"
    }

    private func farmPortrait(farm: LauncherFarm, size: CGFloat) -> some View {
        ZStack {
            HeritageImage(name: "friend-frame.png")
            if let url = farm.thumbnailURL, let image = NSImage(contentsOf: url) {
                Image(nsImage: image).resizable().scaledToFill()
                    .frame(width: size * 0.72, height: size * 0.81)
                    .clipShape(RoundedRectangle(cornerRadius: 5)).offset(y: -size * 0.05)
            } else {
                HeritageImage(name: "red-barn-icon.png").padding(8)
            }
        }.frame(width: size, height: size * 1.22).accessibilityHidden(true)
    }

    private var farmLibrarySheet: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Your farms").font(HeritageTheme.headingFont(27))
                    Text("Every village here is saved on this Mac.").font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Done") { sheet = nil }.keyboardShortcut(.cancelAction)
            }.padding(25)
            Divider()
            if library.isLoading {
                ProgressView("Finding your farms…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if library.farms.isEmpty {
                ContentUnavailableView("A fresh patch of land", systemImage: "leaf",
                                       description: Text("Create a farm or import a FarmVillage save to begin."))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(library.farms) { farm in
                            Button {
                                library.select(farm)
                                audio.playClick()
                            } label: {
                                HStack(spacing: 17) {
                                    farmPortrait(farm: farm, size: 44)
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(farm.name).font(HeritageTheme.headingFont(18)).foregroundStyle(HeritageTheme.ink)
                                        Text("\(farm.xp.formatted()) XP").font(.caption).foregroundStyle(HeritageTheme.mutedInk)
                                    }
                                    Spacer()
                                    if farm.id == library.selectedFarm?.id {
                                        Image(systemName: "checkmark.circle.fill").font(.title3).foregroundStyle(HeritageTheme.grass)
                                    }
                                }
                                .padding(14).frame(maxWidth: .infinity)
                                .background(farm.id == library.selectedFarm?.id ? HeritageTheme.grass.opacity(0.12) : Color.white.opacity(0.6),
                                            in: RoundedRectangle(cornerRadius: 12))
                                .contentShape(RoundedRectangle(cornerRadius: 12))
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("\(farm.name), \(farm.xp.formatted()) experience points")
                            .accessibilityAddTraits(farm.id == library.selectedFarm?.id ? .isSelected : [])
                        }
                    }.padding(20)
                }
            }
            if let error = library.errorMessage {
                Text(error).font(.caption).foregroundStyle(.red).padding(.horizontal, 25).padding(.bottom, 10)
            }
            Divider()
            HStack(spacing: 14) {
                Button("Create Farm") { sheet = nil; library.createFarm(runtime: runtime, game: game) }
                Button("Import…") { sheet = nil; library.importFarm(runtime: runtime, game: game) }
                Spacer()
                Button("Open Farm") {
                    sheet = nil
                    isEditing = false
                    library.returnToFarm(runtime: runtime, game: game)
                }
                .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                .disabled(library.selectedFarm == nil || runtime.isBusy || library.isOpening)
            }.padding(22).disabled(library.isLoading)
        }
        .frame(width: 650, height: 530).background(HeritageTheme.paper)
    }

    private var settingsSheet: some View {
        VStack(spacing: 0) {
            HStack {
                Text("FarmVillage Settings").font(.title2.weight(.medium))
                Spacer()
                Button("Done") { sheet = nil }.keyboardShortcut(.cancelAction)
            }.padding(22)
            Picker("Settings section", selection: $settingsTab) {
                Text("General").tag(LauncherSettingsTab.general)
                Text("Setup").tag(LauncherSettingsTab.setup)
                Text("Activity").tag(LauncherSettingsTab.activity)
            }
            .pickerStyle(.segmented).labelsHidden().frame(width: 390).padding(.bottom, 14)
            Group {
                switch settingsTab {
                case .general: generalSettings
                case .setup: setupSettings
                case .activity: activityContent
                }
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.horizontal, 20).padding(.bottom, 20)
        }
        .frame(width: 760, height: 610).background(Color(nsColor: .windowBackgroundColor))
    }

    private var generalSettings: some View {
        ScrollView {
            Form {
                Section("At the farm gate") {
                    Toggle("Original barnyard ambience", isOn: $audio.isEnabled)
                    Slider(value: $audio.volume, in: 0...1) {
                        Text("Farm gate volume")
                    }
                    .disabled(!audio.isEnabled)
                    Text("Optional launcher sounds. They stop when the game opens so its own music can take over.")
                        .font(.caption).foregroundStyle(.secondary)
                    Slider(value: $playbackVolume, in: 0...1) { Text("Game volume") }
                    Text("The original game’s music and sound buttons work independently. This volume controls both.")
                        .font(.caption).foregroundStyle(.secondary)
                    Toggle("Animate farm animals", isOn: $motionEnabled).disabled(systemReduceMotion)
                    if systemReduceMotion {
                        Text("Reduce Motion is enabled in macOS; the farm gate stays still.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Section("Your farms") {
                    Button("Choose or manage a farm…", action: showLibrary)
                    Button("Show Farm Data in Finder", action: runtime.revealData)
                    if presentsGame {
                        Button("Open God Barn…") { sheet = nil; openGodBarn() }
                        Text("God Barn pauses the game while you edit. Returning loads your saved changes.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Section("Made from the original farm") {
                    Text("Original FarmVille artwork and sounds, preserved by the FarmVillage project. The local game runs with the experimental Ruffle player; some legacy features may be incomplete.")
                        .font(.callout).foregroundStyle(.secondary)
                    HStack {
                        Link("FarmVillage project", destination: URL(string: "https://github.com/AcidCaos/farmvillage")!)
                        Link("Ruffle compatibility", destination: URL(string: "https://ruffle.rs/compatibility/")!)
                        Button("Artwork credits") {
                            if let url = HeritageTheme.resource("manifest.json") { NSWorkspace.shared.open(url) }
                        }
                    }
                }
            }.formStyle(.grouped)
        }
    }

    private var setupSettings: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(runtime.isPrepared ? "The farm is ready to open." : "A little preparation, then you’re home.")
                    .font(HeritageTheme.headingFont(23))
                Text("FarmVillage keeps its runtime and saves together on this Mac. First prepare the player, then open your farm. The original artwork download is about 18 GiB and needs additional space while extracting.")
                    .font(.callout).foregroundStyle(.secondary).lineSpacing(3)
                HStack {
                    Button(runtime.isPrepared ? "Prepare Runtime Again" : "Prepare Runtime") {
                        runtime.prepare(); settingsTab = .activity
                    }.disabled(!runtime.canPrepare)
                    if runtime.isPrepared {
                        Button("Open Farm") {
                            sheet = nil
                            if library.selectedFarm != nil { library.returnToFarm(runtime: runtime, game: game) }
                            else { library.createFarm(runtime: runtime, game: game) }
                        }.buttonStyle(.borderedProminent).disabled(!runtime.canStart)
                    }
                }
                Divider()
                DisclosureGroup("Advanced runtime options") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Python executable (optional)").font(.headline)
                        TextField("Automatic discovery, or an absolute Python 3 path", text: $runtime.pythonPath)
                            .textFieldStyle(.roundedBorder).font(.system(.callout, design: .monospaced))
                            .disabled(runtime.hasOwnedProcess || runtime.isBusy)
                        Text("Leave blank to find a compatible installed Python automatically.").font(.caption).foregroundStyle(.secondary)
                        Text(runtime.dataDirectory.path).font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary).textSelection(.enabled)
                        HStack {
                            Button("Show Farm Data", action: runtime.revealData)
                            Button("Show Log File", action: runtime.revealLog)
                        }
                    }.padding(.top, 12)
                }
                if runtime.isBusy {
                    HStack { ProgressView().controlSize(.small); Text(runtime.phase.title) }
                    Button("View progress") { settingsTab = .activity }
                }
            }.padding(26).frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var activityContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                if runtime.isBusy { ProgressView().controlSize(.small).padding(.top, 3) }
                else { Image(systemName: runtime.phase.symbol).foregroundStyle(HeritageTheme.grass) }
                VStack(alignment: .leading, spacing: 5) {
                    Text(runtime.phase.title).font(.headline)
                    Text(runtime.message).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                }
                Spacer()
                if runtime.canStop {
                    Button(runtime.phase == .preparing ? "Cancel Setup" : "Stop Farm", action: runtime.stop)
                }
                Button("Show Log", action: runtime.revealLog)
            }.padding(18)
            Divider()
            ScrollViewReader { proxy in
                ScrollView([.vertical, .horizontal]) {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(runtime.logs.isEmpty ? "Progress and server output appear here when you prepare or open a farm." : runtime.logs)
                            .font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Color.clear.frame(height: 1).id("log-end")
                    }.padding(17)
                }.onChange(of: runtime.logs) { _, _ in proxy.scrollTo("log-end", anchor: .bottom) }
            }.background(Color(nsColor: .textBackgroundColor))
            HStack {
                Text("Local server · 127.0.0.1:5501").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Clear View", action: runtime.clearVisibleLogs).disabled(runtime.logs.isEmpty)
            }.padding(12)
        }.background(Color(nsColor: .windowBackgroundColor))
    }

    private var gameContent: some View {
        VStack(spacing: 0) {
            if let error = game.errorMessage { webError(error, reload: game.reload, dismiss: { game.errorMessage = nil }) }
            GameWebView(url: runtime.gameURL, controller: game, onFarmLoaded: { library.didLoadFarm(uid: $0) })
                .overlay(alignment: .top) {
                    if game.isLoading { ProgressView().controlSize(.small).padding(10).background(.regularMaterial, in: Capsule()).padding(10) }
                }
        }
    }

    private var godBarnContent: some View {
        VStack(spacing: 0) {
            if let error = barn.errorMessage { webError(error, reload: barn.reload, dismiss: { barn.errorMessage = nil }) }
            GameWebView(url: runtime.godBarnURL, controller: barn, onReturnToFarm: { isEditing = false; updateAudio() })
                .overlay(alignment: .top) {
                    if barn.isLoading { ProgressView().controlSize(.small).padding(10).background(.regularMaterial, in: Capsule()).padding(10) }
                }
        }
    }

    private func webError(_ message: String, reload: @escaping () -> Void, dismiss: @escaping () -> Void) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
            Text(message).font(.callout).textSelection(.enabled)
            Spacer()
            Button("Reload", action: reload)
            Button(action: dismiss) { Image(systemName: "xmark") }.buttonStyle(.plain).accessibilityLabel("Dismiss error")
        }.padding(13).background(Color.orange.opacity(0.10))
    }

    private func showLibrary() {
        guard !isLeavingBarn else { return }
        if isEditing {
            isLeavingBarn = true
            Task { @MainActor in
                defer { isLeavingBarn = false }
                do {
                    guard let uid = try await barn.leaveGodBarn() else {
                        barn.errorMessage = "Wait for God Barn to finish opening, then choose your farm again."
                        return
                    }
                    guard isEditing, runtime.phase == .running else { return }
                    library.didLoadFarm(uid: uid)
                    presentFarmLibrary()
                } catch {
                    barn.errorMessage = "God Barn could not finish its editing session: \(error.localizedDescription)"
                }
            }
        } else { presentFarmLibrary() }
    }

    private func presentFarmLibrary() {
        captureFarmPreview()
        isEditing = false
        library.showHome()
        library.refresh()
        sheet = .farms
        updateAudio()
    }

    private func openGodBarn() {
        guard presentsGame, !isEditing, !game.isLoading,
              game.loadedFarmID != nil, game.loadedFarmID == library.selectedFarmID else { return }
        captureFarmPreview()
        sheet = nil
        game.loadOnNextPresentation(runtime.godBarnResumeURL)
        isEditing = true
        audio.setActive(false)
    }

    private func updateAudio() { audio.setActive(!presentsGame && !isEditing && scenePhase == .active) }

    private func captureFarmPreview() {
        guard presentsGame, !isEditing, let uid = library.selectedFarmID else { return }
        game.capturePreview(uid: uid, in: runtime.dataDirectory)
    }
}

private struct HeritageFarmScene: View {
    let animated: Bool

    var body: some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let height = geometry.size.height
            ZStack {
                LinearGradient(colors: [Color(red: 0.69, green: 0.87, blue: 0.96), Color(red: 1.0, green: 0.98, blue: 0.81)],
                               startPoint: .top, endPoint: .bottom)
                HeritageImage(name: "hills.png")
                    .frame(width: max(width * 1.3, 1500), height: 180)
                    .position(x: width * 0.5, y: height * 0.68)
                Rectangle().fill(Color(red: 0.49, green: 0.68, blue: 0.25))
                    .frame(height: height * 0.30).position(x: width / 2, y: height * 0.86)
                HeritageImage(name: "grass.png").frame(width: 480, height: 195)
                    .position(x: width * 0.13, y: height * 0.79)
                HeritageImage(name: "grass.png").frame(width: 430, height: 174)
                    .position(x: width * 0.9, y: height * 0.80)
                HeritageImage(name: "tree.png").frame(width: 145, height: 133)
                    .position(x: width * 0.045, y: height * 0.56)
                HeritageImage(name: "cherry-blossom.png").frame(width: 225, height: 239)
                    .position(x: width * 0.90, y: height * 0.57)
                HeritageImage(name: "red-barn.png").frame(width: 160, height: 149)
                    .rotationEffect(.degrees(-2)).position(x: width * 0.14, y: height * 0.65)
                HeritageCropField(crops: ["wheat-grown.png", "strawberry-grown.png"])
                    .frame(width: 250, height: 180)
                    .position(x: width * 0.14, y: height * 0.84)
                HeritageCropField(crops: ["eggplant-grown.png", "sunflowers-grown.png"])
                    .frame(width: 250, height: 180)
                    .position(x: width * 0.85, y: height * 0.84)
                ForEach(0..<3, id: \.self) { index in
                    HeritageImage(name: "sunflowers-grown.png").frame(width: 90, height: 90)
                        .position(x: width * 0.29 + CGFloat(index) * 29, y: height * 0.82 + CGFloat(index) * 8)
                    HeritageImage(name: "sunflowers-grown.png").frame(width: 90, height: 90)
                        .position(x: width * 0.71 - CGFloat(index) * 29, y: height * 0.82 + CGFloat(index) * 8)
                }
                HeritageIdleAnimal(kind: "cow", animated: animated).frame(width: 105, height: 92)
                    .position(x: width * 0.77, y: height * 0.69)
                HeritageIdleAnimal(kind: "chicken", animated: animated).frame(width: 52, height: 51)
                    .position(x: width * 0.23, y: height * 0.71)
                HeritageIdleAnimal(kind: "chicken", animated: animated).frame(width: 46, height: 45)
                    .position(x: width * 0.96, y: height * 0.92)
            }
            .clipped().accessibilityHidden(true).allowsHitTesting(false)
        }
    }
}

private struct HeritageCropField: View {
    let crops: [String]

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                ForEach(0..<9, id: \.self) { index in
                    let row = index / 3
                    let column = index % 3
                    HeritageImage(name: crops[row % crops.count])
                        .frame(width: 90, height: 90)
                        .position(x: geometry.size.width / 2 + CGFloat(column - row) * 36,
                                  y: 38 + CGFloat(column + row) * 21)
                }
            }
        }
    }
}

private struct HeritageIdleAnimal: View {
    let kind: String
    let animated: Bool
    var body: some View {
        TimelineView(.animation(minimumInterval: 0.5, paused: !animated)) { context in
            let frame = animated ? Int(context.date.timeIntervalSinceReferenceDate * 2) % 4 + 1 : 1
            let name = String(format: "%@-idle-%02d.png", kind, frame)
            HeritageImage(name: HeritageTheme.image(name) == nil ? "\(kind).png" : name)
        }
    }
}
