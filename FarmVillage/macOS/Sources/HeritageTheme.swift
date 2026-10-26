import AppKit
import CoreText
import SwiftUI

/// The original artwork provides the character; native views provide the controls.
@MainActor
enum HeritageTheme {
    static let ink = Color(red: 0.28, green: 0.18, blue: 0.10)
    static let mutedInk = Color(red: 0.45, green: 0.36, blue: 0.25)
    static let paper = Color(red: 1, green: 0.97, blue: 0.84)
    static let grass = Color(red: 0.36, green: 0.53, blue: 0.20)
    static let wood = Color(red: 0.42, green: 0.25, blue: 0.12)
    private static var images: [String: NSImage] = [:]
    private static var missing: Set<String> = []
    private static var didRegisterFonts = false
    private static var headingPostScriptName: String?

    static func resource(_ name: String) -> URL? {
        guard let root = Bundle.main.resourceURL else { return nil }
        let url = root.appendingPathComponent("Heritage", isDirectory: true).appendingPathComponent(name)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    static func image(_ name: String) -> NSImage? {
        if let value = images[name] { return value }
        guard !missing.contains(name), let url = resource(name), let value = NSImage(contentsOf: url) else {
            missing.insert(name)
            return nil
        }
        images[name] = value
        return value
    }

    static func displayFont(_ size: CGFloat) -> Font {
        registerFonts()
        return NSFont(name: "BadaBoomBB", size: size) != nil
            ? .custom("BadaBoomBB", size: size) : .system(size: size, weight: .bold, design: .rounded)
    }

    static func headingFont(_ size: CGFloat) -> Font {
        registerFonts()
        if let name = headingPostScriptName { return .custom(name, size: size) }
        return .system(size: size, weight: .semibold, design: .rounded)
    }

    static func bodyFont(_ size: CGFloat) -> Font { .system(size: size) }

    private static func registerFonts() {
        guard !didRegisterFonts else { return }
        didRegisterFonts = true
        for filename in ["display.ttf", "heading.ttf"] {
            guard let url = resource(filename) else { continue }
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
            if filename == "heading.ttf",
               let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor],
               let descriptor = descriptors.first,
               let name = CTFontDescriptorCopyAttribute(descriptor, kCTFontNameAttribute) as? String {
                headingPostScriptName = name
            }
        }
    }
}

struct HeritageImage: View {
    let name: String
    var body: some View {
        if let image = HeritageTheme.image(name) {
            Image(nsImage: image).resizable().interpolation(.high).scaledToFit()
                .accessibilityHidden(true)
        } else { Color.clear.accessibilityHidden(true) }
    }
}

struct HeritagePanel<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content
            .background {
                RoundedRectangle(cornerRadius: 18).fill(HeritageTheme.paper)
                    .shadow(color: .black.opacity(0.18), radius: 0, x: 0, y: 5)
                    .shadow(color: HeritageTheme.wood.opacity(0.10), radius: 18, x: 0, y: 12)
            }
            .overlay {
                RoundedRectangle(cornerRadius: 18)
                    .strokeBorder(HeritageTheme.wood, lineWidth: 5)
                    .overlay {
                        RoundedRectangle(cornerRadius: 12).inset(by: 7)
                            .strokeBorder(Color(red: 0.77, green: 0.58, blue: 0.31), lineWidth: 1)
                    }
                    .allowsHitTesting(false)
            }
    }
}

/// A native Button remains responsible for hit testing, focus and accessibility.
/// Only its visible face is skinned; no bitmap contains an invisible hit region.
struct HeritagePrimaryButton: View {
    let title: String
    var disabled = false
    var defaultAction = false
    let action: () -> Void
    @FocusState private var focused: Bool

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Text(title).font(.system(size: 17, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.8)
                Image(systemName: "arrow.right").font(.system(size: 17, weight: .bold))
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity).frame(minHeight: 54)
            .padding(.horizontal, 20)
            .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(HeritageButtonStyle())
        .focused($focused)
        .overlay {
            if focused {
                RoundedRectangle(cornerRadius: 15).stroke(Color.accentColor, lineWidth: 3)
                    .padding(-4).allowsHitTesting(false)
            }
        }
        .disabled(disabled)
        .keyboardShortcut(defaultAction ? .defaultAction : nil)
        .accessibilityLabel(title)
    }
}

private struct HeritageButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background {
                RoundedRectangle(cornerRadius: 12).fill(
                    LinearGradient(colors: configuration.isPressed
                               ? [Color(red: 0.29, green: 0.47, blue: 0.10), Color(red: 0.40, green: 0.58, blue: 0.15)]
                               : [Color(red: 0.58, green: 0.76, blue: 0.22), Color(red: 0.36, green: 0.58, blue: 0.13)],
                               startPoint: .top, endPoint: .bottom))
                    .shadow(color: HeritageTheme.wood.opacity(configuration.isPressed ? 0.1 : 0.4),
                            radius: 0, x: 0, y: configuration.isPressed ? 0 : 3)
            }
            .overlay {
                RoundedRectangle(cornerRadius: 12).strokeBorder(HeritageTheme.wood, lineWidth: 3)
                    .overlay {
                        RoundedRectangle(cornerRadius: 8).inset(by: 4)
                            .strokeBorder(.white.opacity(0.3), lineWidth: 1)
                    }
                    .allowsHitTesting(false)
            }
            .offset(y: configuration.isPressed ? 2 : 0)
            .opacity(enabled ? 1 : 0.45)
    }
}

extension Notification.Name {
    static let farmVillageShowSettings = Notification.Name("FarmVillage.ShowSettings")
    static let farmVillageShowLibrary = Notification.Name("FarmVillage.ShowLibrary")
    static let farmVillageShowGodBarn = Notification.Name("FarmVillage.ShowGodBarn")
    static let farmVillageReloadCurrentView = Notification.Name("FarmVillage.ReloadCurrentView")
}
