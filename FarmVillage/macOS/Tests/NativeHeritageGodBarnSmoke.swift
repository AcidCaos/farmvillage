import AppKit
import Darwin
import Foundation
import SwiftUI
import WebKit

/// Exercises the actual native launcher and God Barn with one newly owned farm.
/// The caller supplies this repository's prepared LocalData and final app resources.
@main
struct NativeHeritageGodBarnSmoke {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let operation = Task { @MainActor in
            do { try await run(); exit(EXIT_SUCCESS) }
            catch { print("FAIL: \(error.localizedDescription)"); exit(error is CleanupFailure ? 75 : EXIT_FAILURE) }
        }
        var sources: [DispatchSourceSignal] = []
        for number in [SIGINT, SIGTERM] {
            signal(number, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
            source.setEventHandler { operation.cancel() }
            source.resume()
            sources.append(source)
        }
        withExtendedLifetime(sources) { app.run() }
        print("FAIL: native AppKit run loop ended before the async validation completed")
        exit(EXIT_FAILURE)
    }

    @MainActor
    static func run() async throws {
        guard CommandLine.arguments.count == 3, CommandLine.arguments[1].hasPrefix("/"), CommandLine.arguments[2].hasPrefix("/") else {
            throw Failure("usage: NativeHeritageGodBarnSmoke /absolute/repository/LocalData /absolute/output")
        }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().standardizedFileURL
        let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true).standardizedFileURL
        let expected = root.appendingPathComponent("LocalData", isDirectory: true).standardizedFileURL
        guard directory.path == expected.path,
              directory.resolvingSymlinksInPath().path == expected.resolvingSymlinksInPath().path,
              directory.resolvingSymlinksInPath().path.hasPrefix(root.resolvingSymlinksInPath().path + "/") else {
            throw Failure("This check only uses this repository's owned prepared LocalData (expected \(expected.path), received \(directory.path)).")
        }
        let output = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        guard await health() == nil else { throw Failure("Port 5501 is already occupied; no process was started.") }
        let runtime = RuntimeController(dataDirectory: directory)
        guard runtime.canStart else { throw Failure("The supplied profile is not prepared; this check never installs runtime dependencies.") }
        let game = GameWebController()
        let library = LauncherLibrary(dataDirectory: directory)
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 1380, height: 900),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "FarmVillage native God Barn validation — input belongs to the test"
        window.ignoresMouseEvents = true
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: ContentView(runtime: runtime, game: game, library: library))
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        defer { window.close() }
        var ownedUID: String?
        do {
            runtime.start()
            try await eventually("owned native runtime startup", timeout: 90) {
                if runtime.phase == .failed { throw Failure(runtime.message) }
                return runtime.phase == .running && runtime.serverToken != nil
            }
            guard let token = runtime.serverToken, await health() == token else { throw Failure("The server token does not match this native controller.") }
            print("PASS: actual RuntimeController started final bundled resources and verified its owned server")
            let name = "Native launcher audit \(UUID().uuidString.prefix(8))"
            var create = URLRequest(url: runtime.gameURL.appendingPathComponent("launcher/create"))
            create.httpMethod = "POST"
            create.setValue("application/json", forHTTPHeaderField: "Content-Type")
            create.setValue(token, forHTTPHeaderField: "X-FarmVillage-Token")
            create.httpBody = try JSONSerialization.data(withJSONObject: ["name": name])
            let (created, response) = try await URLSession.shared.data(for: create)
            guard (response as? HTTPURLResponse)?.statusCode == 200,
                  let result = try JSONSerialization.jsonObject(with: created) as? [String: Any],
                  let uid = result["uid"] as? String else { throw Failure("Native farm creation did not succeed: \(String(decoding: created, as: UTF8.self))") }
            ownedUID = uid
            try created.write(to: output.appendingPathComponent("created-farm.json"))
            library.refresh()
            try await eventually("the newly owned farm in the native picker", timeout: 10) { !library.isLoading && library.farms.contains { $0.id == uid } }
            guard let farm = library.farms.first(where: { $0.id == uid }) else { throw Failure("The new farm is missing from its picker.") }
            library.select(farm)
            library.isPresentingFarm = true
            var initialBrowser: WKWebView?
            try await eventually("the actual ContentView game WebView", timeout: 10) {
                initialBrowser = webViews(window.contentView).first
                return initialBrowser != nil
            }
            guard let initialBrowser else { throw Failure("ContentView did not create its real WebView.") }
            installCapture(initialBrowser)
            library.returnToFarm(runtime: runtime, game: game)
            try await gameReady(initialBrowser, timeout: 120)
            let firstEpoch = try await epoch(initialBrowser)
            let firstOrigin = try await initialBrowser.evaluateJavaScript("performance.timeOrigin") as? Double
            try await snapshot(initialBrowser, to: output.appendingPathComponent("game-before-barn.png"))
            try await saveDiagnostics(initialBrowser, to: output.appendingPathComponent("game-before-barn.json"))
            print("PASS: native farm selection submitted the real login; Ruffle initUser/postInit and interactive world loaded")

            try await eventually("the resumed selected-farm identity to settle", timeout: 10) { game.loadedFarmID == uid && !game.isLoading }
            NotificationCenter.default.post(name: .farmVillageShowGodBarn, object: nil)
            var editor: WKWebView?
            try await eventually("exclusive native God Barn presentation", timeout: 30) {
                let browsers = webViews(window.contentView)
                guard !browsers.contains(where: { $0 === initialBrowser }) else { return false }
                editor = browsers.first { $0.url?.path.hasPrefix("/god-barn") == true }
                return editor != nil
            }
            guard let editor else { throw Failure("The editor WebView did not replace the game.") }
            try await eventually("God Barn's live local farm controls", timeout: 60) {
                (try? await editor.evaluateJavaScript("Boolean(document.querySelector('[data-action=\"open-bank\"]') && document.querySelector('[data-action=\"return-farm\"]'))")) as? Bool == true
            }
            let editorState = try await editor.callAsyncJavaScript("return await (await fetch('/god-barn/api/state')).json();", arguments: [:], in: nil, contentWorld: .page)
            guard let state = editorState as? [String: Any], state["mode"] as? String == "live",
                  let barnFarm = state["farm"] as? [String: Any], barnFarm["id"] as? String == uid else {
                throw Failure("God Barn did not bind to the actual selected farm: \(String(describing: editorState))")
            }
            // The parked editor owns this revision after all game-side startup awards.
            let originalGold = try savedGold(uid, in: directory)
            try JSONSerialization.data(withJSONObject: state, options: [.prettyPrinted, .sortedKeys])
                .write(to: output.appendingPathComponent("god-barn-state-before-edit.json"))
            try await snapshot(editor, to: output.appendingPathComponent("god-barn-live.png"))
            print("PASS: opening God Barn removed Ruffle and retained the selected live farm through the real browser session")
            _ = try await editor.evaluateJavaScript("document.querySelector('[data-action=\"open-bank\"]').click()")
            try await eventually("the real coin adjustment form", timeout: 10) {
                (try? await editor.evaluateJavaScript("Boolean(document.querySelector('form[data-balance=\"gold\"]'))")) as? Bool == true
            }
            _ = try await editor.evaluateJavaScript("""
                (()=>{const form=document.querySelector('form[data-balance="gold"]');
                form.elements.mode.value='add';form.elements.amount.value='12345';form.requestSubmit();})()
                """)
            try await eventually("the coin-change preview", timeout: 15) {
                (try? await editor.evaluateJavaScript("Boolean(document.querySelector('[data-action=\"apply-preview\"]:not(:disabled)'))")) as? Bool == true
            }
            try await snapshot(editor, to: output.appendingPathComponent("god-barn-preview.png"))
            _ = try await editor.evaluateJavaScript("document.querySelector('[data-action=\"apply-preview\"]').click()")
            let expectedGold = originalGold + 12345
            try await eventually("the live edit to be durably saved", timeout: 20) {
                try savedGold(uid, in: directory) == expectedGold
            }
            try await eventually("the real preview to close after successful apply", timeout: 15) {
                (try? await editor.evaluateJavaScript("document.querySelector('[data-action=\"apply-preview\"]') === null")) as? Bool == true
            }
            print("PASS: God Barn's actual DOM preview/apply added 12,345 coins to the dedicated test farm")
            _ = try await editor.evaluateJavaScript("document.querySelector('[data-action=\"return-farm\"]').click()")
            var resumed: WKWebView?
            try await eventually("the native return bridge to replace God Barn", timeout: 20) {
                let browsers = webViews(window.contentView)
                guard !browsers.contains(where: { $0 === editor }) else { return false }
                resumed = browsers.first { $0 !== initialBrowser }
                return resumed != nil
            }
            guard let resumed else { throw Failure("Return did not create a fresh game WebView.") }
            installCapture(resumed)
            try await gameReady(resumed, timeout: 120)
            let resumedEpoch = try await epoch(resumed)
            let resumedOrigin = try await resumed.evaluateJavaScript("performance.timeOrigin") as? Double
            guard resumed !== initialBrowser, firstEpoch != resumedEpoch, !resumedEpoch.isEmpty, resumedOrigin != firstOrigin,
                  library.selectedFarmID == uid, try savedGold(uid, in: directory) == expectedGold else {
                throw Failure("The resumed game did not retain the farm, edited coins and a fresh epoch/document.")
            }
            try await snapshot(resumed, to: output.appendingPathComponent("game-after-barn.png"))
            try await saveDiagnostics(resumed, to: output.appendingPathComponent("game-after-barn.json"))
            let evidence: [String: Any] = ["uid": uid, "name": name, "goldBefore": originalGold, "goldAfter": expectedGold,
                                           "firstEpoch": firstEpoch, "resumedEpoch": resumedEpoch,
                                           "freshWebView": true, "freshDocument": true, "exclusiveEditor": true]
            try JSONSerialization.data(withJSONObject: evidence, options: [.prettyPrinted, .sortedKeys])
                .write(to: output.appendingPathComponent("result.json"))
            print("PASS: real native return loaded a new Ruffle document and epoch, successful initUser/postInit, and the edited saved balance")

            NotificationCenter.default.post(name: .farmVillageShowGodBarn, object: nil)
            var secondEditor: WKWebView?
            try await eventually("God Barn reopening before the native farm chooser", timeout: 30) {
                secondEditor = webViews(window.contentView).first { $0.url?.path.hasPrefix("/god-barn") == true }
                guard let secondEditor else { return false }
                return (try? await secondEditor.evaluateJavaScript("Boolean(document.querySelector('[data-action=\"return-farm\"]'))")) as? Bool == true
            }
            NotificationCenter.default.post(name: .farmVillageShowLibrary, object: nil)
            try await Task.sleep(nanoseconds: 1_000_000_000)
            try captureWindow(window, to: output.appendingPathComponent("chooser-transition.png"))
            try await eventually("the native chooser to release and remove God Barn", timeout: 20) {
                !library.isPresentingFarm && webViews(window.contentView).isEmpty && window.attachedSheet != nil
            }
            guard let secondEditor, secondEditor.superview == nil || !webViews(window.contentView).contains(where: { $0 === secondEditor }) else {
                throw Failure("The editor remained attached behind the farm chooser.")
            }
            print("PASS: Choose Farm from God Barn released the editing session and removed its WebView before showing the native picker")
            runtime.stop()
            try await stopped(runtime)
            guard await health() == nil else { throw Failure("The owned native runtime retained port 5501 after Stop.") }
            print("PASS: native Stop reaped the owned runtime and released port 5501")
            try archiveOwnedFarm(uid, in: directory, output: output)
            print("PASS: only the newly owned validation save was archived into the evidence folder; existing farms were left intact")
        } catch {
            print("Owned test farm: \(ownedUID ?? "none")")
            print("Runtime diagnostics:\n\(runtime.logs.suffix(14000))")
            if let browser = webViews(window.contentView).first {
                try? captureWindow(window, to: output.appendingPathComponent("failure-native-window.png"))
                try? await snapshot(browser, to: output.appendingPathComponent("failure.png"))
                try? await saveDiagnostics(browser, to: output.appendingPathComponent("failure.json"))
                if let html = try? await browser.evaluateJavaScript("document.documentElement.outerHTML") as? String {
                    try? Data(html.utf8).write(to: output.appendingPathComponent("failure.html"))
                }
            }
            if runtime.canStop { runtime.stop() }
            let cleaned = await Task { @MainActor in (try? await stopped(runtime)) != nil }.value
            if !cleaned { throw CleanupFailure(message: "\(error.localizedDescription) Inspect the owned runtime before starting another server.") }
            else if let ownedUID { try? archiveOwnedFarm(ownedUID, in: directory, output: output) }
            throw error
        }
    }

    @MainActor static func installCapture(_ browser: WKWebView) {
        // This content controller can outlive a game document during the native editor transition.
        // Keep its hooks on the game page and retain capture state in each callback's closure.
        let script = "(()=>{if(location.pathname !== '/ruffle.html' || window.__nativeSmoke)return;\n" + captureScript + "\n})();"
        browser.configuration.userContentController.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        browser.evaluateJavaScript(script, completionHandler: nil)
    }

    @MainActor static func gameReady(_ browser: WKWebView, timeout: TimeInterval) async throws {
        try await eventually("the real Ruffle initUser/postInit and interactive world", timeout: timeout) {
            guard browser.url?.path == "/ruffle.html",
                  let text = try? await browser.evaluateJavaScript(diagnosticsScript) as? String,
                  let value = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any] else { return false }
            if value["fatalRendererFailure"] as? Bool == true { throw Failure("The actual renderer emitted a fatal error: \(text)") }
            return value["hasSuccessfulInit"] as? Bool == true && value["hasSuccessfulPostInit"] as? Bool == true
                && value["isInteractive"] as? Bool == true
        }
    }

    @MainActor static func epoch(_ browser: WKWebView) async throws -> String {
        guard let value = try await browser.evaluateJavaScript("""
            (()=>{const script=document.getElementById('god-barn-game-epoch');if(!script)return '';
            const match=script.textContent.match(/const epoch=("[^"]+")/);return match?JSON.parse(match[1]):'';})()
            """) as? String, !value.isEmpty else { throw Failure("The game did not expose its injected ownership epoch.") }
        return value
    }

    static func savedGold(_ uid: String, in directory: URL) throws -> Double {
        let data = try Data(contentsOf: directory.appendingPathComponent("saves/\(uid).save.json"))
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let user = json["userInfo"] as? [String: Any], let player = user["player"] as? [String: Any],
              let value = player["gold"] as? NSNumber else { throw Failure("The dedicated test farm has no saved gold.") }
        return value.doubleValue
    }

    static func archiveOwnedFarm(_ uid: String, in directory: URL, output: URL) throws {
        let file = directory.appendingPathComponent("saves/\(uid).save.json")
        guard file.resolvingSymlinksInPath() == file else { throw Failure("The newly owned validation save changed its path; it was preserved.") }
        let bytes = try Data(contentsOf: file)
        guard let json = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let user = json["userInfo"] as? [String: Any], let player = user["player"] as? [String: Any],
              String(describing: player["userId"] ?? "") == uid else { throw Failure("The owned validation save identity changed; it was preserved.") }
        try bytes.write(to: output.appendingPathComponent("\(uid).save.json"), options: .atomic)
        try FileManager.default.removeItem(at: file)
        let preview = directory.appendingPathComponent("Launcher/Previews/\(uid).png")
        if FileManager.default.fileExists(atPath: preview.path), preview.resolvingSymlinksInPath() == preview {
            let previewBytes = try Data(contentsOf: preview)
            try previewBytes.write(to: output.appendingPathComponent("\(uid)-preview.png"), options: .atomic)
            try FileManager.default.removeItem(at: preview)
        }
    }

    static func health() async -> String? {
        guard let url = URL(string: "http://127.0.0.1:5501/health"),
              let (data, response) = try? await URLSession.shared.data(from: url),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let state = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return state["wrapper_token"] as? String
    }

    @MainActor static func stopped(_ runtime: RuntimeController) async throws {
        try await eventually("owned runtime cleanup", timeout: 30) { !runtime.hasOwnedProcess }
    }

    @MainActor static func eventually(_ label: String, timeout: TimeInterval, condition: @MainActor () async throws -> Bool) async throws {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            try Task.checkCancellation()
            if try await condition() { return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw Failure("Timed out waiting for \(label).")
    }

    @MainActor static func webViews(_ view: NSView?) -> [WKWebView] {
        guard let view else { return [] }
        if let browser = view as? WKWebView { return [browser] }
        return view.subviews.flatMap(webViews)
    }

    @MainActor static func snapshot(_ browser: WKWebView, to url: URL) async throws {
        let configuration = WKSnapshotConfiguration()
        configuration.afterScreenUpdates = true
        let image = try await browser.takeSnapshot(configuration: configuration)
        guard let tiff = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else { throw Failure("The owned browser snapshot could not be encoded.") }
        try png.write(to: url)
    }

    @MainActor static func captureWindow(_ window: NSWindow, to url: URL) throws {
        guard let view = window.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        if let bytes = bitmap.representation(using: .png, properties: [:]) { try bytes.write(to: url) }
    }

    @MainActor static func saveDiagnostics(_ browser: WKWebView, to url: URL) async throws {
        guard let text = try await browser.evaluateJavaScript(diagnosticsScript) as? String else { return }
        try Data(text.utf8).write(to: url)
        if let wire = try await browser.evaluateJavaScript("JSON.stringify(window.__nativeSmoke.gatewayResponses)") as? String {
            try Data(wire.utf8).write(to: url.deletingPathExtension().appendingPathExtension("wire.json"))
        }
    }

    struct Failure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }

    struct CleanupFailure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    // Renderer instrumentation is copied from the existing NativeWebSmoke harness.
    static let captureScript = #"""
    const smokeState = window.__nativeSmoke = { documentId: String(performance.timeOrigin), messages: [], traceMarkers: [], criticalMessages: [], fatalRendererFailure:false, renderer:null, inputEvents: [], importantInputEvents:[], events: [], errorEvents: [], network: [], gatewayRequests: [], gatewayResponses: [], catalogBodies: [], invalidObjectErrors: [], interactive: false, worldLoaded: false };
    for (const type of ['pointerenter', 'pointermove', 'pointerdown', 'pointerup', 'mousedown', 'mouseup', 'click', 'keydown', 'keyup']) {
      addEventListener(type, event => {
        const entry = {type, time:performance.now(), x:event.clientX, y:event.clientY, offsetX:event.offsetX, offsetY:event.offsetY, button:event.button, buttons:event.buttons, key:event.key, trusted:event.isTrusted, target:event.composedPath().map(node=>node.nodeName||node.constructor.name).slice(0,5)};
        smokeState.inputEvents.push(entry);
        if (smokeState.inputEvents.length > 100) smokeState.inputEvents.shift();
        if (!['pointermove','pointerenter'].includes(type) && smokeState.importantInputEvents.length < 300) smokeState.importantInputEvents.push(entry);
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
      const record = {documentId: smokeState.documentId, id: smokeState.gatewayRequests.length, url: new URL(url, location.href).href, time: performance.now(), base64: base64(bytes),
                      initUser: text.includes('UserService.initUser'), postInit: text.includes('UserService.postInit'),
                      worldAction: text.includes('WorldService.performAction'), harvest: text.includes('harvest')};
      smokeState.gatewayRequests.push(record);
      return record;
    };
    const originalArrayBuffer = Response.prototype.arrayBuffer;
    Response.prototype.arrayBuffer = async function() {
      const buffer = await originalArrayBuffer.call(this);
      smokeState.network.push({phase: 'body', url: this.url, time: performance.now(), bytes: buffer.byteLength});
      if (new URL(this.url, location.href).pathname.includes('.amf')) {
        const bytes = new Uint8Array(buffer);
        smokeState.catalogBodies.push({url: this.url, time: performance.now(), bytes: bytes.length,
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
        smokeState.network.push({phase: 'failure', url: new URL(url, location.href).href, status: 0, time: performance.now(), error: String(error)});
        throw error;
      }
      smokeState.network.push({phase: 'headers', url: response.url, status: response.status, time: performance.now()});
      if (isGateway(url)) {
        const bytes = new Uint8Array(await response.clone().arrayBuffer());
        smokeState.gatewayResponses.push({documentId: smokeState.documentId, id: request && request.id, url: response.url, status: response.status, time: performance.now(), base64: base64(bytes),
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
      this.addEventListener('loadend', () => smokeState.network.push({phase: 'xhr', url: this.__nativeURL, status: this.status, time: performance.now()}));
      return originalSend.call(this, body);
    };
    for (const level of ['log', 'info', 'warn', 'error']) {
      const original = console[level].bind(console);
      console[level] = (...args) => {
        const text = args.map(value => value instanceof Error ? value.stack || String(value) : String(value)).join(' ');
        const record = {level, text, time: performance.now()};
        if (text.includes('[FV-FTUE-DIAG]')) smokeState.traceMarkers.push(record);
        const rendererMatch = text.match(/Used renderer:\s*([^)]+)/);
        if (rendererMatch) smokeState.renderer = rendererMatch[1];
        if (/panicked|panic|unable to lock ruffle core|unreachable|runtimeerror|rusterror/i.test(text)) smokeState.fatalRendererFailure = true;
        if (text.includes('onLoadStep interactive')) smokeState.interactive = true;
        if (text === 'onWorldLoad') smokeState.worldLoaded = true;
        if (text.includes('RustError') && text.includes('Invalid object')) {
          record.stack = new Error('Ruffle console context').stack;
          smokeState.invalidObjectErrors.push(record);
        }
        if ((level === 'error' || /ERROR|panicked|panic|RustError|unreachable|RuntimeError/.test(text)) && smokeState.criticalMessages.length < 100) {
          smokeState.criticalMessages.push({...record, stack: new Error('Renderer error context').stack});
        }
        smokeState.messages.push(record);
        if (smokeState.messages.length > 80) smokeState.messages.shift();
        original(...args);
      };
    }
    addEventListener('error', event => {
      smokeState.events.push('error: ' + event.message);
      smokeState.fatalRendererFailure = true;
      if (smokeState.errorEvents.length < 20) smokeState.errorEvents.push({time:performance.now(), message:event.message, stack:event.error && event.error.stack, filename:event.filename, line:event.lineno, column:event.colno});
    });
    addEventListener('unhandledrejection', event => { smokeState.fatalRendererFailure = true; smokeState.events.push('rejection: ' + String(event.reason)); });
    const observer = new MutationObserver(() => {
      const player = document.getElementById('flashapp');
      if (player && !player.__nativeObserved) {
        player.__nativeObserved = true;
        for (const type of ['loadedmetadata', 'loadeddata', 'error']) {
          player.addEventListener(type, event => {
            smokeState.events.push(type + ': ' + String(event.message || ''));
            if (type !== 'error' && !player.__nativeTraceInstalled) {
              player.ruffle().traceObserver = line => {
                if (String(line).includes('[FV-FTUE-DIAG]')) smokeState.traceMarkers.push({text:String(line),time:performance.now()});
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
