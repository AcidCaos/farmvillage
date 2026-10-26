import AppKit
import Foundation
import SwiftUI
import WebKit

/// Exercises the shipped representable against an explicitly identified fixture server.
/// The caller must prepare that server and its isolated assets independently.
@main
struct NativeWebSmoke {
    @MainActor
    static func main() {
        let application = NSApplication.shared
        application.setActivationPolicy(.regular)
        Task { @MainActor in
            do {
                try await run()
                exit(EXIT_SUCCESS)
            } catch {
                print("FAIL: \(error.localizedDescription)")
                print("Diagnostic error detail: \((error as NSError).userInfo)")
                exit(EXIT_FAILURE)
            }
        }
        application.run()
        print("FAIL: native AppKit run loop ended before the async validation completed")
        exit(EXIT_FAILURE)
    }

    @MainActor
    static func run() async throws {
        let arguments = CommandLine.arguments
        let isFullGame = arguments.count == 7 && arguments[3] == "--full-game" && arguments[5] == "--actions"
        guard (arguments.count == 3 || isFullGame), let url = URL(string: arguments[1]),
              url.scheme == "http", url.host == "127.0.0.1", url.port == 5501 else {
            throw SmokeFailure("usage: NativeWebSmoke http://127.0.0.1:5501/ EXPECTED_FIXTURE_TOKEN [--full-game /absolute/isolated-data --actions /absolute/actions.json]")
        }
        let fullData = isFullGame ? try fullGameDataDirectory(arguments[4]) : nil
        if isFullGame && !arguments[6].hasPrefix("/") { throw SmokeFailure("The owned-window action plan must use an absolute path.") }
        let healthRequest = URLRequest(url: url.appendingPathComponent("health"), timeoutInterval: 5)
        let (data, response) = try await URLSession.shared.data(for: healthRequest)
        let health = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard (response as? HTTPURLResponse)?.statusCode == 200,
              health?["wrapper_token"] as? String == arguments[2] else {
            throw SmokeFailure("The server token did not match the explicitly supplied fixture token; no village was created.")
        }

        let controller = GameWebController()
        let view = NSHostingView(rootView: GameWebView(url: url, controller: controller, websiteDataStore: .nonPersistent()))
        let visibleFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1280, height: 900)
        let origin = NSPoint(x: visibleFrame.minX + min(100, max(0, visibleFrame.width - 1280)),
                             y: visibleFrame.minY + min(100, max(0, visibleFrame.height - 930)))
        let window = NSWindow(contentRect: NSRect(origin: origin, size: NSSize(width: 1280, height: 900)),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.title = "FarmVillage automated renderer validation — please leave input to the test"
        window.ignoresMouseEvents = isFullGame
        window.contentView = view
        // WebKit and Ruffle pause occluded pages. This owned validation window
        // must be visible to exercise the default renderer playback behavior.
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        if isFullGame {
            try writeArtifact(JSONSerialization.data(withJSONObject: ["ignoresNativeMouseEvents": window.ignoresMouseEvents,
                "rendererPreference": ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_RENDERER"] ?? "default",
                "backgroundTickRequested": ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_BACKGROUND_TICK"] == "1"]), name: "harness-configuration.json")
        }
        view.layoutSubtreeIfNeeded()
        defer { window.close() }

        var browser: WKWebView?
        try await eventually("SwiftUI to create its WebKit view", timeout: 10) {
            view.layoutSubtreeIfNeeded()
            browser = findWebView(view)
            return browser != nil
        }
        guard let browser else { throw SmokeFailure("The representable did not create a WKWebView.") }
        let renderer = ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_RENDERER"]
        guard renderer == nil || renderer == "canvas" else { throw SmokeFailure("Only the optional canvas renderer A/B override is supported.") }
        let rendererOverride = renderer == "canvas" ? """
        window.RufflePlayer = window.RufflePlayer || {};
        { let configuration = {preferredRenderer:'canvas'};
          Object.defineProperty(window.RufflePlayer, 'config', {configurable:true, get:()=>configuration, set:value=>{configuration={...value,preferredRenderer:'canvas'};}});
        }
        """ : ""
        browser.configuration.userContentController.addUserScript(WKUserScript(source: rendererOverride + captureScript,
            injectionTime: .atDocumentStart, forMainFrameOnly: true))
        try await eventually("the login page", timeout: 15) {
            (try? await browser.evaluateJavaScript("Boolean(document.querySelector('a[href=\"/new.html\"]'))")) as? Bool == true
        }
        guard controller.errorMessage == nil else { throw SmokeFailure(controller.errorMessage!) }
        print("PASS: actual GameWebView loaded the local login page")

        _ = try await browser.evaluateJavaScript("document.querySelector('a[href=\"/new.html\"]').click()")
        try await eventually("the new-village name form", timeout: 15) {
            (try? await browser.evaluateJavaScript("Boolean(document.querySelector('form[action=\"/new.html\"] #name'))")) as? Bool == true
        }
        _ = try await browser.evaluateJavaScript(
            "document.getElementById('name').value = 'Smoke Farmer'; document.querySelector('form[action=\"/new.html\"]').submit()")
        try await eventually("the new-village Ruffle page", timeout: 20) {
            let hasPlayer = (try? await browser.evaluateJavaScript("Boolean(document.getElementById('flashapp'))")) as? Bool == true
            return browser.url?.path == "/ruffle.html" && hasPlayer
        }
        print("PASS: new-village creation navigated to the self-hosted Ruffle client")

        var diagnostics = ""
        do {
            try await eventually("Ruffle JavaScript/WASM and Flash initialization", timeout: 60) {
                diagnostics = (try? await browser.evaluateJavaScript(diagnosticsScript)) as? String ?? "{}"
                let data = Data(diagnostics.utf8)
                let state = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
                return state["hasWasm"] as? Bool == true && state["hasMetadata"] as? Bool == true
            }
        } catch {
            print("Ruffle diagnostics: \(diagnostics)")
            throw error
        }
        print("PASS: self-hosted Ruffle fetched WASM and reported Flash movie metadata")
        try await snapshot(browser, name: "preloader")
        if ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_BACKGROUND_TICK"] == "1" {
            let visibility = try await browser.evaluateJavaScript("document.visibilityState") as? String ?? "unknown"
            if visibility == "hidden" {
                _ = try await browser.evaluateJavaScript("window.__nativeSmoke.backgroundTickRequested = true; document.dispatchEvent(new Event('visibilitychange')); true")
                progress("QUALIFICATION: document remains hidden; requested Ruffle's configured background tick via its visibility handler. Foreground rendering is not established by this run.")
            }
        }
        do {
            try await eventually("the preloader to fetch FarmGame.swf", timeout: 30) {
                diagnostics = (try? await browser.evaluateJavaScript(diagnosticsScript)) as? String ?? "{}"
                let state = (try? JSONSerialization.jsonObject(with: Data(diagnostics.utf8))) as? [String: Any] ?? [:]
                return state["hasGame"] as? Bool == true
            }
        } catch {
            try? await snapshot(browser, name: "preloader-timeout")
            print("Ruffle diagnostics: \(diagnostics)")
            throw error
        }
        do {
            try await eventually("a real initUser AMF response", timeout: 30) {
                diagnostics = (try? await browser.evaluateJavaScript(diagnosticsScript)) as? String ?? "{}"
                let state = (try? JSONSerialization.jsonObject(with: Data(diagnostics.utf8))) as? [String: Any] ?? [:]
                let failures = state["gatewayFailures"] as? [[String: Any]] ?? []
                return state["hasSuccessfulInit"] as? Bool == true || !failures.isEmpty
            }
        } catch {
            try? await saveWireCapture(browser)
            print("Ruffle diagnostics: \(diagnostics)")
            throw error
        }
        let postInitDeadline = Date().addingTimeInterval(isFullGame ? 90 : 15)
        while Date() < postInitDeadline {
            diagnostics = (try? await browser.evaluateJavaScript(diagnosticsScript)) as? String ?? diagnostics
            let state = (try? JSONSerialization.jsonObject(with: Data(diagnostics.utf8))) as? [String: Any] ?? [:]
            if state["hasSuccessfulPostInit"] as? Bool == true { break }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        if let fullData {
            try await eventually("postInit and the interactive full-art world", timeout: 90) {
                let state = try await state(browser)
                return state["hasSuccessfulPostInit"] as? Bool == true && state["isInteractive"] as? Bool == true
            }
            let state = try await state(browser)
            try await snapshot(browser, name: "game-ready")
            try await saveWireCapture(browser)
            try requireNoMissingAssets(state)
            try await exerciseCanvasHarvest(browser, controller: controller, window: window, data: fullData,
                                            actionPlan: URL(fileURLWithPath: arguments[6]))
        }
        diagnostics = (try? await browser.evaluateJavaScript(diagnosticsScript)) as? String ?? diagnostics
        print("PASS: the Flash preloader fetched the real FarmGame.swf")
        try await snapshot(browser, name: "game")
        try await saveWireCapture(browser)
        print("Ruffle diagnostics: \(diagnostics)")
        let finalState = (try? JSONSerialization.jsonObject(with: Data(diagnostics.utf8))) as? [String: Any] ?? [:]
        let gatewayFailures = finalState["gatewayFailures"] as? [[String: Any]] ?? []
        let hasSuccessfulInit = finalState["hasSuccessfulInit"] as? Bool == true
        let invalidObjectErrors = finalState["invalidObjectErrors"] as? [String] ?? []
        if isFullGame { try requireNoMissingAssets(finalState) }
        try requireNoFatalRendererErrors(finalState)
        guard controller.errorMessage == nil else { throw SmokeFailure(controller.errorMessage!) }

        controller.returnToLogin()
        try await eventually("Return to Login", timeout: 15) {
            let hasLogin = (try? await browser.evaluateJavaScript("Boolean(document.querySelector('a[href=\"/new.html\"]'))")) as? Bool == true
            return browser.url?.path == "/" && hasLogin
        }
        guard let previousTimeOrigin = try await browser.evaluateJavaScript("performance.timeOrigin") as? Double else {
            throw SmokeFailure("The login document did not expose a navigation time origin.")
        }
        controller.reload()
        try await eventually("Reload", timeout: 15) {
            let hasLogin = (try? await browser.evaluateJavaScript("Boolean(document.querySelector('a[href=\"/new.html\"]'))")) as? Bool == true
            let timeOrigin = (try? await browser.evaluateJavaScript("performance.timeOrigin")) as? Double
            return timeOrigin != nil && timeOrigin != previousTimeOrigin && !browser.isLoading && !controller.isLoading && hasLogin
        }
        print("PASS: Return to Login and Reload kept the same owned WebKit view usable")
        guard gatewayFailures.isEmpty else { throw SmokeFailure("The real Flash client received unsuccessful AMF gateway responses: \(gatewayFailures)") }
        guard hasSuccessfulInit else { throw SmokeFailure("The real Flash client's initUser request did not receive HTTP 200.") }
        guard invalidObjectErrors.isEmpty else { throw SmokeFailure("The renderer still reported an Invalid-object AMF/catalog error: \(invalidObjectErrors)") }
        print("PASS: the real Flash initUser request received a successful AMF response")
        print("PASS: no Invalid-object AMF/catalog error was emitted by the renderer")
    }

    static func fullGameDataDirectory(_ path: String) throws -> URL {
        guard path.hasPrefix("/") else { throw SmokeFailure("The full-game fixture data path must be absolute.") }
        let buildRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(".build", isDirectory: true).standardizedFileURL
        let localData = buildRoot.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("LocalData", isDirectory: true).standardizedFileURL
        let selected = URL(fileURLWithPath: path, isDirectory: true).standardizedFileURL
        let resolved = selected.resolvingSymlinksInPath()
        let inBuild = selected.path.hasPrefix(buildRoot.path + "/")
            && resolved.path.hasPrefix(buildRoot.resolvingSymlinksInPath().path + "/")
        let inLocalData = selected == localData && resolved == localData.resolvingSymlinksInPath()
            && resolved.path.hasPrefix(localData.deletingLastPathComponent().resolvingSymlinksInPath().path + "/")
        guard inBuild || inLocalData else {
            throw SmokeFailure("Full-game validation data must use this repository's LocalData or macOS/.build folder.")
        }
        return selected
    }

    @MainActor
    static func state(_ browser: WKWebView) async throws -> [String: Any] {
        guard let value = try await browser.evaluateJavaScript(diagnosticsScript) as? String,
              let result = try JSONSerialization.jsonObject(with: Data(value.utf8)) as? [String: Any] else {
            throw SmokeFailure("The native renderer did not return diagnostics.")
        }
        if ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_BACKGROUND_TICK"] == "1",
           result["visibility"] as? String == "hidden", result["hasMetadata"] as? Bool == true {
            _ = try await browser.evaluateJavaScript("if (!window.__nativeSmoke.backgroundTickRequested) { window.__nativeSmoke.backgroundTickRequested = true; document.dispatchEvent(new Event('visibilitychange')); } true")
        }
        return result
    }

    static func requireNoMissingAssets(_ state: [String: Any]) throws {
        let missing = state["missingLocalAssets"] as? [[String: Any]] ?? []
        guard missing.isEmpty else { throw SmokeFailure("Complete-art validation encountered missing local assets: \(missing)") }
    }

    static func requireNoFatalRendererErrors(_ state: [String: Any]) throws {
        let capture = state["capture"] as? [String: Any] ?? [:]
        let exceptions = capture["errorEvents"] as? [[String: Any]] ?? []
        let events = capture["events"] as? [String] ?? []
        let messages = capture["criticalMessages"] as? [[String: Any]] ?? []
        let fatal = messages.compactMap { $0["text"] as? String }.filter { text in
            let lower = text.lowercased()
            return ["panicked", "panic", "unable to lock ruffle core", "unreachable", "runtimeerror", "rusterror", "verifyerror", "error running avm2"].contains { lower.contains($0) }
        }
        guard state["fatalRendererFailure"] as? Bool != true, exceptions.isEmpty, !events.contains(where: { $0.hasPrefix("error:") || $0.hasPrefix("rejection:") }), fatal.isEmpty else {
            throw SmokeFailure("The renderer emitted a fatal exception or core failure; inspect the preserved diagnostic errorEvents/criticalMessages: \(exceptions.first?["message"] ?? fatal.first ?? events.first ?? "unknown error")")
        }
    }

    struct ActionPlan: Decodable {
        let steps: [ActionStep]
        let expectedGoldAdjustment: Double?
    }
    struct ActionStep: Codable {
        let kind: String
        let x: Double
        let y: Double
        let waitMilliseconds: Int?
    }
    struct StarterPlot: Equatable {
        let state: String
        let x: Int
        let y: Int
        let z: Int
    }
    struct SavedFarm {
        let bytes: Data
        let gold: Double
        let plots: [Int: StarterPlot]
    }

    static func savedFarm(_ file: URL, uid: String) throws -> SavedFarm {
        let bytes = try Data(contentsOf: file)
        guard let root = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let user = root["userInfo"] as? [String: Any], let player = user["player"] as? [String: Any],
              player["userId"] as? String == uid, let gold = player["gold"] as? NSNumber,
              let world = root["world"] as? [String: Any], let objects = world["objectsArray"] as? [[String: Any]] else {
            throw SmokeFailure("The selected fixture save did not match the rendered village.")
        }
        var plots: [Int: StarterPlot] = [:]
        for object in objects {
            guard let id = object["id"] as? NSNumber, [4, 5].contains(id.intValue),
                  let position = object["position"] as? [String: Any],
                  let x = position["x"] as? NSNumber, let y = position["y"] as? NSNumber,
                  let z = position["z"] as? NSNumber, let state = object["state"] as? String else { continue }
            plots[id.intValue] = StarterPlot(state: state, x: x.intValue, y: y.intValue, z: z.intValue)
        }
        return SavedFarm(bytes: bytes, gold: gold.doubleValue, plots: plots)
    }

    static func writeArtifact(_ bytes: Data, name: String) throws {
        guard let output = ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_OUTPUT_DIR"], output.hasPrefix("/") else {
            throw SmokeFailure("Full-game validation requires an absolute FARMVILLAGE_SMOKE_OUTPUT_DIR.")
        }
        let directory = URL(fileURLWithPath: output, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try bytes.write(to: directory.appendingPathComponent(name), options: .atomic)
    }

    @MainActor
    static func exerciseCanvasHarvest(_ browser: WKWebView, controller: GameWebController, window: NSWindow, data: URL, actionPlan: URL) async throws {
        guard let uid = try await browser.evaluateJavaScript("String(getUserInfo().uid)") as? String, UUID(uuidString: uid) != nil else {
            throw SmokeFailure("The full-art client did not expose a valid fixture village UID.")
        }
        let save = data.appendingPathComponent("saves/\(uid).save.json")
        let baseline = try savedFarm(save, uid: uid)
        guard baseline.plots.values.contains(where: { $0.state == "grown" }) else {
            throw SmokeFailure("The new fixture has no ripe starter crop to harvest.")
        }
        try writeArtifact(baseline.bytes, name: "save-before.json")
        try await snapshot(browser, name: "gameplay-action-before")
        try await saveWireCapture(browser)
        let baselineRequests = (try await browser.evaluateJavaScript("window.__nativeSmoke.gatewayRequests.length") as? NSNumber)?.intValue ?? 0
        let initialPlan = try JSONDecoder().decode(ActionPlan.self, from: Data(contentsOf: actionPlan))
        let expectedGoldAdjustment = initialPlan.expectedGoldAdjustment ?? 0
        guard expectedGoldAdjustment.isFinite else {
            throw SmokeFailure("The declared action-plan gold adjustment must be finite.")
        }
        progress("READY FOR CANVAS ACTION: append player-relative CSS-pixel clicks to \(actionPlan.path); inspect gameplay-action-before.png. Only this owned validation window receives events.")

        var consumed = 0
        var harvested: [Int] = []
        var finalSave: SavedFarm?
        let deadline = Date().addingTimeInterval(600)
        while Date() < deadline {
            do {
                let current = try await state(browser)
                try requireNoFatalRendererErrors(current)
                try requireNoMissingAssets(current)
            } catch {
                try? await saveWireCapture(browser, suffix: "-failure")
                try? await snapshot(browser, name: "renderer-failure")
                throw error
            }
            if let bytes = try? Data(contentsOf: actionPlan), let plan = try? JSONDecoder().decode(ActionPlan.self, from: bytes) {
                while consumed < plan.steps.count {
                    let step = plan.steps[consumed]
                    try await sendCanvasInput(step, browser: browser, window: window, number: consumed + 1)
                    consumed += 1
                    try await Task.sleep(nanoseconds: UInt64(min(max(step.waitMilliseconds ?? 600, 0), 5000)) * 1_000_000)
                    try await snapshot(browser, name: String(format: "action-%03d", consumed))
                    try await saveWireCapture(browser, suffix: String(format: "-action-%03d", consumed))
                    try requireNoFatalRendererErrors(try await state(browser))
                    progress("Applied owned canvas action \(consumed); snapshot action-\(String(format: "%03d", consumed)).png")
                }
            }
            let successful = try await browser.evaluateJavaScript("window.__nativeSmoke.gatewayResponses.some(entry => entry.id >= \(baselineRequests) && entry.worldAction && entry.harvest && entry.status === 200)") as? Bool == true
            if successful, let updated = try? savedFarm(save, uid: uid) {
                harvested = baseline.plots.keys.filter { id in
                    guard let before = baseline.plots[id], let after = updated.plots[id] else { return false }
                    return before.state == "grown" && after.state == "fallow"
                        && before.x == after.x && before.y == after.y && before.z == after.z
                }.sorted()
                if !harvested.isEmpty && updated.gold - baseline.gold == expectedGoldAdjustment + Double(harvested.count * 88) {
                    finalSave = updated
                    break
                }
            }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        try await saveWireCapture(browser, suffix: "-before-reload")
        let originalState = try await state(browser)
        try requireNoFatalRendererErrors(originalState)
        try requireNoMissingAssets(originalState)
        guard let finalSave else {
            try? await snapshot(browser, name: "gameplay-action-timeout")
            throw SmokeFailure("No owned canvas harvest produced both a successful client WorldService.performAction and the expected persisted starter-crop/gold delta.")
        }
        try writeArtifact(finalSave.bytes, name: "save-after.json")
        let summary: [String: Any] = ["uid": uid, "harvestedIDs": harvested, "goldBefore": baseline.gold,
                                      "goldAfter": finalSave.gold, "nativeInputSteps": consumed,
                                      "declaredGoldAdjustment": expectedGoldAdjustment]
        try writeArtifact(JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys]), name: "harvest-summary.json")
        try await snapshot(browser, name: "gameplay-action-after")
        progress("PASS: actual Flash-canvas harvest persisted plots \(harvested), gold \(baseline.gold) → \(finalSave.gold)")

        guard let previous = try await browser.evaluateJavaScript("performance.timeOrigin") as? Double else { throw SmokeFailure("The gameplay document had no time origin.") }
        let beforeReload = try await state(browser)
        try requireNoFatalRendererErrors(beforeReload)
        try requireNoMissingAssets(beforeReload)
        controller.reload()
        try await eventually("a new full-game document after the harvest", timeout: 120) {
            guard let origin = try? await browser.evaluateJavaScript("performance.timeOrigin") as? Double, origin != previous else { return false }
            let state = try await state(browser)
            return state["hasSuccessfulPostInit"] as? Bool == true && state["isInteractive"] as? Bool == true
        }
        let reloaded = try savedFarm(save, uid: uid)
        guard reloaded.gold == finalSave.gold, harvested.allSatisfy({ reloaded.plots[$0] == finalSave.plots[$0] }) else {
            throw SmokeFailure("The harvested crop or gold changed unexpectedly after reloading the client.")
        }
        try writeArtifact(reloaded.bytes, name: "save-reloaded.json")
        try requireNoMissingAssets(try await state(browser))
        try requireNoFatalRendererErrors(try await state(browser))
        try await snapshot(browser, name: "game-reloaded")
        progress("PASS: client reload retained the harvested plot and earned gold")
    }

    @MainActor
    static func sendCanvasInput(_ step: ActionStep, browser: WKWebView, window: NSWindow, number: Int) async throws {
        guard ["click", "move", "pointer", "hover", "enter", "escape"].contains(step.kind), step.x.isFinite, step.y.isFinite else { throw SmokeFailure("Only finite owned canvas click/move/pointer/hover coordinates and Enter/Escape keys are supported.") }
        if step.kind == "enter" || step.kind == "escape" {
            window.makeKeyAndOrderFront(nil)
            _ = window.makeFirstResponder(browser)
            let characters = step.kind == "enter" ? "\r" : "\u{1b}"
            let keyCode: UInt16 = step.kind == "enter" ? 36 : 53
            for type in [NSEvent.EventType.keyDown, .keyUp] {
                guard let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                    context: nil, characters: characters, charactersIgnoringModifiers: characters,
                    isARepeat: false, keyCode: keyCode) else { throw SmokeFailure("The owned keyboard event could not be constructed.") }
                window.sendEvent(event)
                try await Task.sleep(nanoseconds: 80_000_000)
            }
            try writeArtifact(JSONEncoder().encode(step), name: String(format: "action-%03d.json", number))
            return
        }
        let script = "(() => { const r = document.getElementById('flashapp').getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,viewWidth:innerWidth,viewHeight:innerHeight}; })()"
        guard let rect = try await browser.evaluateJavaScript(script) as? [String: Any],
              let x = rect["x"] as? Double, let y = rect["y"] as? Double,
              let width = rect["width"] as? Double, let height = rect["height"] as? Double,
              let viewWidth = rect["viewWidth"] as? Double, let viewHeight = rect["viewHeight"] as? Double,
              step.x >= 0, step.x < width, step.y >= 0, step.y < height, viewWidth > 0, viewHeight > 0 else {
            throw SmokeFailure("The requested action is outside the owned Flash player.")
        }
        let cssX = x + step.x, cssY = y + step.y
        if step.kind == "pointer" || step.kind == "hover" {
            let script = """
            (() => {
              const player = document.getElementById('flashapp');
              const canvas = player.shadowRoot && player.shadowRoot.querySelector('canvas');
              if (!canvas) throw new Error('No owned Ruffle canvas found');
              const options = {bubbles:true, composed:true, cancelable:true, clientX:\(cssX), clientY:\(cssY), pointerId:1, pointerType:'mouse', isPrimary:true, button:0};
              canvas.focus();
              canvas.dispatchEvent(new PointerEvent('pointerenter', {...options, buttons:0}));
              canvas.dispatchEvent(new PointerEvent('pointermove', {...options, buttons:0}));
              window.__nativeSmoke.pointerTarget = canvas;
              window.__nativeSmoke.pointerOptions = options;
              return true;
            })()
            """
            _ = try await browser.evaluateJavaScript(script)
            try await Task.sleep(nanoseconds: 80_000_000)
            if step.kind == "pointer" {
                _ = try await browser.evaluateJavaScript("window.__nativeSmoke.pointerTarget.dispatchEvent(new PointerEvent('pointerdown', {...window.__nativeSmoke.pointerOptions, buttons:1}))")
                try await Task.sleep(nanoseconds: 80_000_000)
                _ = try await browser.evaluateJavaScript("window.__nativeSmoke.pointerTarget.dispatchEvent(new PointerEvent('pointerup', {...window.__nativeSmoke.pointerOptions, buttons:0}))")
            }
            try writeArtifact(JSONEncoder().encode(step), name: String(format: "action-%03d.json", number))
            return
        }
        let localX = cssX / viewWidth * browser.bounds.width
        let topY = cssY / viewHeight * browser.bounds.height
        let localY = browser.isFlipped ? topY : browser.bounds.height - topY
        let location = browser.convert(NSPoint(x: localX, y: localY), to: nil)
        window.acceptsMouseMovedEvents = true
        window.makeKeyAndOrderFront(nil)
        _ = window.makeFirstResponder(browser)
        func send(_ type: NSEvent.EventType, pressure: Float) throws {
            guard let event = NSEvent.mouseEvent(with: type, location: location, modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                context: nil, eventNumber: number, clickCount: type == .mouseMoved ? 0 : 1, pressure: pressure) else {
                throw SmokeFailure("The owned canvas event could not be constructed.")
            }
            window.sendEvent(event)
        }
        try send(.mouseMoved, pressure: 0)
        if step.kind == "click" {
            try send(.leftMouseDown, pressure: 1)
            try await Task.sleep(nanoseconds: 80_000_000)
            try send(.leftMouseUp, pressure: 0)
        }
        let record = try JSONEncoder().encode(step)
        try writeArtifact(record, name: String(format: "action-%03d.json", number))
    }

    static func progress(_ text: String) { print(text); fflush(nil) }

    @MainActor
    static func findWebView(_ view: NSView) -> WKWebView? {
        if let view = view as? WKWebView { return view }
        for child in view.subviews {
            if let match = findWebView(child) { return match }
        }
        return nil
    }

    @MainActor
    static func eventually(_ description: String, timeout: TimeInterval,
                           condition: @MainActor () async throws -> Bool) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if try await condition() { return }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        throw SmokeFailure("Timed out waiting for \(description).")
    }

    struct SmokeFailure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }

    @MainActor
    static func snapshot(_ browser: WKWebView, name: String) async throws {
        guard let outputPath = ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_OUTPUT_DIR"] else { return }
        guard outputPath.hasPrefix("/") else { throw SmokeFailure("The snapshot output folder must be absolute.") }
        let directory = URL(fileURLWithPath: outputPath, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let configuration = WKSnapshotConfiguration()
        configuration.afterScreenUpdates = true
        let image = try await browser.takeSnapshot(configuration: configuration)
        guard let tiff = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw SmokeFailure("The WebKit snapshot could not be encoded as PNG.")
        }
        let file = directory.appendingPathComponent("\(name).png")
        try png.write(to: file, options: .atomic)
        print("Snapshot: \(file.path)")
    }

    @MainActor
    static func saveWireCapture(_ browser: WKWebView, suffix: String = "-wire") async throws {
        guard let outputPath = ProcessInfo.processInfo.environment["FARMVILLAGE_SMOKE_OUTPUT_DIR"], outputPath.hasPrefix("/") else { return }
        let script = "JSON.stringify({requests: window.__nativeSmoke.gatewayRequests, responses: window.__nativeSmoke.gatewayResponses, catalogs: window.__nativeSmoke.catalogBodies})"
        guard let contents = try await browser.evaluateJavaScript(script) as? String else { return }
        let file = URL(fileURLWithPath: outputPath, isDirectory: true).appendingPathComponent("gateway\(suffix).json")
        try Data(contents.utf8).write(to: file, options: .atomic)
        let rawScript = "JSON.stringify({fatalRendererFailure:window.__nativeSmoke.fatalRendererFailure,criticalMessages:window.__nativeSmoke.criticalMessages,errorEvents:window.__nativeSmoke.errorEvents,events:window.__nativeSmoke.events,traceMarkers:window.__nativeSmoke.traceMarkers,importantInputEvents:window.__nativeSmoke.importantInputEvents})"
        if let raw = try await browser.evaluateJavaScript(rawScript) as? String {
            try Data(raw.utf8).write(to: file.deletingLastPathComponent().appendingPathComponent("raw-renderer\(suffix).json"), options: .atomic)
        }
        if let diagnostics = try await browser.evaluateJavaScript(diagnosticsScript) as? String {
            let diagnosticFile = file.deletingLastPathComponent().appendingPathComponent("diagnostics\(suffix == "-wire" ? "" : suffix).json")
            try Data(diagnostics.utf8).write(to: diagnosticFile, options: .atomic)
        }
        print("Gateway wire capture: \(file.path)")
    }

    static let captureScript = #"""
    window.__nativeSmoke = { documentId: String(performance.timeOrigin), messages: [], traceMarkers: [], criticalMessages: [], fatalRendererFailure:false, renderer:null, inputEvents: [], importantInputEvents:[], events: [], errorEvents: [], network: [], gatewayRequests: [], gatewayResponses: [], catalogBodies: [], invalidObjectErrors: [], interactive: false, worldLoaded: false };
    for (const type of ['pointerenter', 'pointermove', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'keydown', 'keyup']) {
      addEventListener(type, event => {
        const entry = {type, time:performance.now(), x:event.clientX, y:event.clientY, offsetX:event.offsetX, offsetY:event.offsetY, button:event.button, buttons:event.buttons, key:event.key, trusted:event.isTrusted, target:event.composedPath().map(node=>node.nodeName||node.constructor.name).slice(0,5)};
        window.__nativeSmoke.inputEvents.push(entry);
        if (window.__nativeSmoke.inputEvents.length > 100) window.__nativeSmoke.inputEvents.shift();
        if (!['pointermove','pointerenter'].includes(type) && window.__nativeSmoke.importantInputEvents.length < 300) window.__nativeSmoke.importantInputEvents.push(entry);
      }, true);
    }
    const isGateway = url => new URL(url, location.href).pathname === '/flashservices/gateway.php';
    const base64 = bytes => {
      let text = '';
      for (let index = 0; index < bytes.length; index += 32768) {
        text += String.fromCharCode(...bytes.subarray(index, index + 32768));
      }
      return btoa(text);
    };
    const recordBody = async (url, body) => {
      let bytes;
      if (body instanceof ArrayBuffer) bytes = new Uint8Array(body);
      else if (ArrayBuffer.isView(body)) bytes = new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
      else if (body instanceof Blob) bytes = new Uint8Array(await body.arrayBuffer());
      else if (typeof body === 'string') bytes = new TextEncoder().encode(body);
      else return;
      const text = new TextDecoder().decode(bytes);
      const record = {documentId: window.__nativeSmoke.documentId, id: window.__nativeSmoke.gatewayRequests.length, url: new URL(url, location.href).href, time: performance.now(), base64: base64(bytes),
                      initUser: text.includes('UserService.initUser'), postInit: text.includes('UserService.postInit'),
                      worldAction: text.includes('WorldService.performAction'), harvest: text.includes('harvest')};
      window.__nativeSmoke.gatewayRequests.push(record);
      return record;
    };
    const originalArrayBuffer = Response.prototype.arrayBuffer;
    Response.prototype.arrayBuffer = async function() {
      const buffer = await originalArrayBuffer.call(this);
      window.__nativeSmoke.network.push({phase: 'body', url: this.url, time: performance.now(), bytes: buffer.byteLength});
      if (new URL(this.url, location.href).pathname.includes('.amf')) {
        const bytes = new Uint8Array(buffer);
        window.__nativeSmoke.catalogBodies.push({url: this.url, time: performance.now(), bytes: bytes.length,
                                               first256: base64(bytes.subarray(0, 256))});
      }
      return buffer;
    };
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, options) => {
      const url = typeof input === 'string' || input instanceof URL ? String(input) : input.url;
      let request = null;
      if (isGateway(url)) {
        const body = options && options.body !== undefined ? options.body : input instanceof Request ? await input.clone().arrayBuffer() : null;
        request = await recordBody(url, body);
      }
      let response;
      try { response = await originalFetch(input, options); }
      catch (error) {
        window.__nativeSmoke.network.push({phase: 'failure', url: new URL(url, location.href).href, status: 0, time: performance.now(), error: String(error)});
        throw error;
      }
      window.__nativeSmoke.network.push({phase: 'headers', url: response.url, status: response.status, time: performance.now()});
      if (isGateway(url)) {
        const bytes = new Uint8Array(await response.clone().arrayBuffer());
        window.__nativeSmoke.gatewayResponses.push({documentId: window.__nativeSmoke.documentId, id: request && request.id, url: response.url, status: response.status, time: performance.now(), base64: base64(bytes),
                                                   initUser: !!(request && request.initUser), postInit: !!(request && request.postInit),
                                                   worldAction: !!(request && request.worldAction), harvest: !!(request && request.harvest)});
      }
      return response;
    };
    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
      this.__nativeURL = new URL(url, location.href).href;
      return originalOpen.call(this, method, url, ...rest);
    };
    XMLHttpRequest.prototype.send = function(body) {
      if (isGateway(this.__nativeURL)) recordBody(this.__nativeURL, body);
      this.addEventListener('loadend', () => window.__nativeSmoke.network.push({phase: 'xhr', url: this.__nativeURL, status: this.status, time: performance.now()}));
      return originalSend.call(this, body);
    };
    for (const level of ['log', 'info', 'warn', 'error']) {
      const original = console[level].bind(console);
      console[level] = (...args) => {
        const text = args.map(value => value instanceof Error ? value.stack || String(value) : String(value)).join(' ');
        const avmStack = args.find(value => value && typeof value.avmStack === 'string')?.avmStack;
        const record = {level, text, time: performance.now(), ...(avmStack ? {avmStack} : {})};
        if (text.includes('[FV-FTUE-DIAG]')) window.__nativeSmoke.traceMarkers.push(record);
        const rendererMatch = text.match(/Used renderer:\s*([^)]+)/);
        if (rendererMatch) window.__nativeSmoke.renderer = rendererMatch[1];
        if (/panicked|panic|unable to lock ruffle core|unreachable|runtimeerror|rusterror|verifyerror|error running avm2/i.test(text)) window.__nativeSmoke.fatalRendererFailure = true;
        if (text.includes('onLoadStep interactive')) window.__nativeSmoke.interactive = true;
        if (text === 'onWorldLoad') window.__nativeSmoke.worldLoaded = true;
        if (text.includes('RustError') && text.includes('Invalid object')) {
          record.stack = new Error('Ruffle console context').stack;
          window.__nativeSmoke.invalidObjectErrors.push(record);
        }
        if ((level === 'error' || /ERROR|panicked|panic|RustError|unreachable|RuntimeError|VerifyError/.test(text)) && window.__nativeSmoke.criticalMessages.length < 100) {
          window.__nativeSmoke.criticalMessages.push({...record, stack: new Error('Renderer error context').stack});
        }
        window.__nativeSmoke.messages.push(record);
        if (window.__nativeSmoke.messages.length > 80) window.__nativeSmoke.messages.shift();
        original(...args);
      };
    }
    addEventListener('error', event => {
      window.__nativeSmoke.events.push('error: ' + event.message);
      window.__nativeSmoke.fatalRendererFailure = true;
      if (window.__nativeSmoke.errorEvents.length < 20) window.__nativeSmoke.errorEvents.push({time:performance.now(), message:event.message, stack:event.error && event.error.stack, avmStack:event.error && event.error.avmStack, filename:event.filename, line:event.lineno, column:event.colno});
    });
    addEventListener('unhandledrejection', event => { window.__nativeSmoke.fatalRendererFailure = true; window.__nativeSmoke.events.push('rejection: ' + String(event.reason)); });
    const observer = new MutationObserver(() => {
      const player = document.getElementById('flashapp');
      if (player && !player.__nativeObserved) {
        player.__nativeObserved = true;
        for (const type of ['loadedmetadata', 'loadeddata', 'error']) {
          player.addEventListener(type, event => {
            window.__nativeSmoke.events.push(type + ': ' + String(event.message || ''));
            if (type !== 'error' && !player.__nativeTraceInstalled) {
              player.ruffle().traceObserver = line => {
                if (String(line).includes('[FV-FTUE-DIAG]')) window.__nativeSmoke.traceMarkers.push({text:String(line),time:performance.now()});
              };
              player.__nativeTraceInstalled = true;
            }
          });
        }
      }
    });
    observer.observe(document, {childList: true, subtree: true});
    """#

    static let diagnosticsScript = #"""
    (() => {
      const player = document.getElementById('flashapp');
      const inspectionErrors = [];
      const readAPI = (name, callback) => { try { return callback(); } catch(error) { inspectionErrors.push({name,message:String(error),stack:error.stack}); return null; } };
      const api = player && readAPI('ruffle',()=>player.ruffle());
      const metadata = api && readAPI('metadata',()=>api.metadata);
      const readyState = api && readAPI('readyState',()=>api.readyState);
      const isPlaying = api && readAPI('isPlaying',()=>typeof api.suspended === 'boolean' ? !api.suspended : typeof api.isPlaying === 'function' ? api.isPlaying() : api.isPlaying);
      const resources = performance.getEntriesByType('resource').map(entry => entry.name);
      const resourceTiming = performance.getEntriesByType('resource')
        .filter(entry => entry.name.includes('/xml/') || entry.name.includes('.amf') || entry.name.includes('.swf') || entry.name.includes('/gateway.php'))
        .map(entry => ({url: entry.name, started: entry.startTime, ended: entry.responseEnd, duration: entry.duration,
                       encodedBytes: entry.encodedBodySize, decodedBytes: entry.decodedBodySize}));
      return JSON.stringify({
        url: location.href, title: document.title,
        hasRuffle: !!window.RufflePlayer,
        visibility: document.visibilityState,
        readyState, isPlaying, metadata, inspectionErrors,
        hasMetadata: !!metadata,
        hasWasm: resources.some(name => name.includes('.wasm')),
        hasGame: resources.some(name => new URL(name).pathname.endsWith('/FarmGame.swf')),
        hasSuccessfulInit: window.__nativeSmoke.gatewayResponses.some(entry => entry.initUser && entry.status === 200),
        hasSuccessfulPostInit: window.__nativeSmoke.gatewayResponses.some(entry => entry.postInit && entry.status === 200),
        isInteractive: window.__nativeSmoke.interactive, hasWorldLoaded: window.__nativeSmoke.worldLoaded,
        selectedRenderer: window.__nativeSmoke.renderer, fatalRendererFailure: window.__nativeSmoke.fatalRendererFailure,
        traceObserverInstalled: !!(player && player.__nativeTraceInstalled),
        viewport: {width: innerWidth, height: innerHeight, pixelRatio: devicePixelRatio},
        playerRect: player && player.getBoundingClientRect().toJSON(),
        invalidObjectErrors: window.__nativeSmoke.invalidObjectErrors.map(entry => entry.text),
        invalidObjectContexts: window.__nativeSmoke.invalidObjectErrors,
        resources: resources.filter(name => name.includes('/ruffle/') || name.includes('.swf') || name.includes('/gateway.php')),
        resourceTiming, network: window.__nativeSmoke.network,
        gatewayFailures: window.__nativeSmoke.network.filter(entry => new URL(entry.url, location.href).pathname === '/flashservices/gateway.php' && entry.status >= 400),
        missingLocalAssets: window.__nativeSmoke.network.filter(entry => {
          const url = new URL(entry.url, location.href);
          return url.origin === location.origin && ['/assets/', '/embeds/', '/xml/', '/assethash/', '/masterysigns/'].some(prefix => url.pathname.startsWith(prefix))
            && (entry.status >= 400 || entry.phase === 'failure');
        }),
        capture: {messages: window.__nativeSmoke.messages, traceMarkers: window.__nativeSmoke.traceMarkers, criticalMessages: window.__nativeSmoke.criticalMessages, inputEvents: window.__nativeSmoke.inputEvents, importantInputEvents:window.__nativeSmoke.importantInputEvents, events: window.__nativeSmoke.events, errorEvents: window.__nativeSmoke.errorEvents,
                  gatewayRequests: window.__nativeSmoke.gatewayRequests.length}
      });
    })()
    """#
}
