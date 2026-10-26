import AppKit
import Combine
import Foundation

/// Launcher audio is opt-in, and never competes with the Flash game's soundtrack.
@MainActor
final class HeritageAudio: ObservableObject {
    @Published var isEnabled: Bool {
        didSet {
            UserDefaults.standard.set(isEnabled, forKey: "FarmVillage.LauncherSoundEnabled")
            updatePlayback()
        }
    }
    @Published var volume: Double {
        didSet {
            UserDefaults.standard.set(volume, forKey: "FarmVillage.LauncherVolume")
            ambience?.volume = Float(min(1, max(0, volume)))
        }
    }
    private var active = false
    private var ambience: NSSound?
    private var click: NSSound?

    init() {
        isEnabled = UserDefaults.standard.bool(forKey: "FarmVillage.LauncherSoundEnabled")
        let rememberedVolume = UserDefaults.standard.object(forKey: "FarmVillage.LauncherVolume") as? Double ?? 0.18
        volume = rememberedVolume.isFinite ? min(1, max(0, rememberedVolume)) : 0.18
        if let url = HeritageTheme.resource("optional-barnyard.mp3") {
            ambience = NSSound(contentsOf: url, byReference: true)
            ambience?.loops = true
            ambience?.volume = Float(volume)
        }
        if let url = HeritageTheme.resource("click.mp3") {
            click = NSSound(contentsOf: url, byReference: true)
            click?.volume = 0.32
        }
    }

    func setActive(_ value: Bool) {
        active = value
        updatePlayback()
    }

    func playClick() {
        guard active, isEnabled else { return }
        click?.stop()
        click?.play()
    }

    private func updatePlayback() {
        if active, isEnabled {
            if ambience?.isPlaying != true { ambience?.play() }
        } else {
            ambience?.stop()
            click?.stop()
        }
    }
}
