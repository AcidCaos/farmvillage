import AppKit
import Combine
import SwiftUI
import UniformTypeIdentifiers
import WebKit

@MainActor
final class GameWebController: ObservableObject {
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published fileprivate(set) var loadedFarmID: String?
    fileprivate weak var webView: WKWebView?
    fileprivate var initialURL: URL?
    fileprivate var hasCommittedPage = false
    fileprivate var nextPresentationURL: URL?
    fileprivate var nextPresentationRequest: URLRequest?
    fileprivate var playbackVolume: Double = {
        let value = UserDefaults.standard.object(forKey: "FarmVillage.PlaybackVolume") as? Double ?? 0.65
        return value.isFinite ? min(1, max(0, value)) : 0.65
    }()
    // WKDownload holds its delegate weakly. The controller survives switching
    // tabs, so an approved export can finish after the Barn view is dismantled.
    fileprivate var downloads: [UUID: GodBarnDownloadDelegate] = [:]

    func setVolume(_ value: Double) {
        guard value.isFinite else { return }
        playbackVolume = min(1, max(0, value))
        UserDefaults.standard.set(playbackVolume, forKey: "FarmVillage.PlaybackVolume")
        webView?.evaluateJavaScript("""
            window.farmVillageVolume = \(playbackVolume);
            { const player = document.getElementById('flashapp');
              if (player && typeof player.ruffle === 'function') player.ruffle().volume = window.farmVillageVolume; }
            """, completionHandler: nil)
    }

    /// A God Barn edit session ends by loading a fresh game document and epoch.
    /// Keep the original login URL separate for the explicit login action.
    func loadOnNextPresentation(_ url: URL) {
        loadedFarmID = nil
        nextPresentationRequest = nil
        nextPresentationURL = url
    }

    func navigate(to url: URL) {
        errorMessage = nil
        loadedFarmID = nil
        if let webView { webView.load(URLRequest(url: url)) }
        else { loadOnNextPresentation(url) }
    }

    func openFarm(uid: String, baseURL: URL) {
        loadedFarmID = nil
        var fields = URLComponents()
        fields.queryItems = [URLQueryItem(name: "UID", value: uid), URLQueryItem(name: "RUFFLE", value: "1")]
        var request = URLRequest(url: baseURL)
        request.httpMethod = "POST"
        request.httpBody = Data((fields.percentEncodedQuery ?? "").utf8)
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        errorMessage = nil
        if let webView { webView.load(request) }
        else { nextPresentationURL = nil; nextPresentationRequest = request }
    }

    /// Capture the actual farm for the native picker; unavailable previews keep the original barn art.
    func capturePreview(uid: String, in directory: URL) {
        guard uid.range(of: "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", options: .regularExpression) != nil,
              loadedFarmID == uid, let webView, !isLoading, webView.url?.path == "/ruffle.html" else { return }
        let root = directory.standardizedFileURL.resolvingSymlinksInPath()
        let previews = root.appendingPathComponent("Launcher/Previews", isDirectory: true)
        guard previews.resolvingSymlinksInPath() == previews else { return }
        let configuration = WKSnapshotConfiguration()
        configuration.snapshotWidth = 400
        configuration.afterScreenUpdates = false
        webView.takeSnapshot(with: configuration) { image, _ in
            guard let image, let tiff = image.tiffRepresentation,
                  let bitmap = NSBitmapImageRep(data: tiff), let png = bitmap.representation(using: .png, properties: [:]),
                  previews.resolvingSymlinksInPath() == previews else { return }
            do {
                try FileManager.default.createDirectory(at: previews, withIntermediateDirectories: true)
                let destination = previews.appendingPathComponent("\(uid).png")
                guard destination.resolvingSymlinksInPath() == destination else { return }
                try png.write(to: destination, options: .atomic)
            } catch { /* A missing preview must never block leaving the farm. */ }
        }
    }

    /// Release this editor session before the native farm chooser removes its WebView.
    func leaveGodBarn() async throws -> String? {
        guard let webView, let path = webView.url?.path,
              path == "/god-barn" || path.hasPrefix("/god-barn/") else { return nil }
        let value = try await webView.callAsyncJavaScript("""
            const stateResponse = await fetch('/god-barn/api/state', {credentials:'same-origin'});
            if (!stateResponse.ok) throw new Error('God Barn could not read its current farm.');
            const state = await stateResponse.json();
            const resumeResponse = await fetch(state.resumeURL, {credentials:'same-origin'});
            if (!resumeResponse.ok) throw new Error('God Barn could not release its editing session.');
            return state.farm.id;
            """, arguments: [:], in: nil, contentWorld: .page)
        return value as? String
    }

    func reload() {
        errorMessage = nil
        loadedFarmID = nil
        guard let webView else { return }
        if hasCommittedPage && webView.url != nil {
            webView.reloadFromOrigin()
        } else if let initialURL {
            // A failed first navigation leaves no committed page to reload.
            webView.load(URLRequest(url: initialURL))
        }
    }

    func returnToLogin() {
        errorMessage = nil
        loadedFarmID = nil
        nextPresentationRequest = nil
        guard let initialURL else { return }
        if let webView { webView.load(URLRequest(url: initialURL)) }
        else { nextPresentationURL = initialURL }
    }
}

@MainActor
fileprivate final class GodBarnDownloadDelegate: NSObject, WKDownloadDelegate {
    let identifier = UUID()
    private weak var owner: GameWebController?
    private weak var window: NSWindow?
    private var download: WKDownload?
    private var panel: NSSavePanel?
    private var destination: URL?
    private var stagedFile: URL?
    private var finished = false

    init(download: WKDownload, owner: GameWebController, window: NSWindow?) {
        self.download = download
        self.owner = owner
        self.window = window
    }

    static func permits(_ url: URL) -> Bool {
        url.scheme?.lowercased() == "http" && url.host?.lowercased() == "127.0.0.1"
            && url.port == 5501 && url.user == nil && url.password == nil
            && url.path.hasPrefix("/god-barn/")
    }

    private static func filename(_ suggestion: String) -> String {
        let basename = (suggestion.replacingOccurrences(of: "\\", with: "/") as NSString).lastPathComponent
        let cleaned = String(basename.unicodeScalars.filter {
            !CharacterSet.controlCharacters.contains($0) && $0 != "/" && $0 != "\\" && $0 != ":"
        }).trimmingCharacters(in: .whitespacesAndNewlines)
        var name = String(cleaned.prefix(150))
        if name.isEmpty || name == "." || name == ".." { name = "God Barn export.json" }
        if !name.lowercased().hasSuffix(".json") { name += ".json" }
        return name
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping @MainActor (URL?) -> Void) {
        guard !finished, let url = response.url, Self.permits(url),
              (response as? HTTPURLResponse).map({ $0.statusCode < 400 }) ?? true else {
            owner?.errorMessage = "The farm export did not return a valid local download."
            completionHandler(nil)
            finish()
            return
        }
        let savePanel = NSSavePanel()
        savePanel.title = "Export FarmVillage Save"
        savePanel.message = "Choose where to save this God Barn JSON export."
        savePanel.nameFieldStringValue = Self.filename(suggestedFilename)
        savePanel.allowedContentTypes = [.json]
        savePanel.canCreateDirectories = true
        savePanel.isExtensionHidden = false
        panel = savePanel
        let complete: (NSApplication.ModalResponse) -> Void = { [weak self, weak savePanel] result in
            guard let self, !self.finished else { completionHandler(nil); return }
            self.panel = nil
            guard result == .OK, let selected = savePanel?.url else {
                completionHandler(nil)
                self.finish()
                return
            }
            self.destination = selected
            // WebKit requires a destination that does not yet exist. Stage
            // alongside the chosen file and publish only after it completes;
            // an existing export survives any cancelled or failed download.
            let stage = selected.deletingLastPathComponent()
                .appendingPathComponent(".god-barn-\(UUID().uuidString).download")
            self.stagedFile = stage
            completionHandler(stage)
        }
        if let window { savePanel.beginSheetModal(for: window, completionHandler: complete) }
        else { savePanel.begin(completionHandler: complete) }
    }

    func download(_ download: WKDownload, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest,
                  decisionHandler: @escaping @MainActor (WKDownload.RedirectPolicy) -> Void) {
        guard let url = request.url, Self.permits(url) else {
            owner?.errorMessage = "The farm export tried to leave the local God Barn."
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard !finished else { return }
        do {
            guard let stagedFile, let destination else { finish(); return }
            if FileManager.default.fileExists(atPath: destination.path) {
                _ = try FileManager.default.replaceItemAt(destination, withItemAt: stagedFile)
            } else {
                try FileManager.default.moveItem(at: stagedFile, to: destination)
            }
            self.stagedFile = nil
        } catch {
            owner?.errorMessage = "The farm export could not be saved: \(error.localizedDescription)"
        }
        finish()
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        let failure = error as NSError
        if failure.domain != NSURLErrorDomain || failure.code != NSURLErrorCancelled {
            owner?.errorMessage = "The farm export could not be downloaded: \(error.localizedDescription)"
        }
        finish()
    }

    private func finish() {
        guard !finished else { return }
        finished = true
        panel?.cancel(nil)
        panel = nil
        download?.delegate = nil
        download = nil
        if let stagedFile { try? FileManager.default.removeItem(at: stagedFile) }
        stagedFile = nil
        owner?.downloads.removeValue(forKey: identifier)
    }
}

/// WebKit hosts the upstream client using self-hosted Ruffle (JavaScript/WASM).
/// Normal page subresources remain available; only top-level navigation is restricted.
@MainActor
struct GameWebView: NSViewRepresentable {
    let url: URL
    @ObservedObject var controller: GameWebController
    var websiteDataStore: WKWebsiteDataStore = .default()
    var onReturnToFarm: (() -> Void)? = nil
    var onFarmLoaded: ((String) -> Void)? = nil

    func makeCoordinator() -> Coordinator {
        Coordinator(controller: controller, onReturnToFarm: onReturnToFarm, onFarmLoaded: onFarmLoaded)
    }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = websiteDataStore
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        configuration.preferences.isElementFullscreenEnabled = true
        configuration.applicationNameForUserAgent = "FarmVillageMac/1.0"
        configuration.userContentController.addUserScript(WKUserScript(
            source: "window.farmVillageVolume = \(controller.playbackVolume);",
            injectionTime: .atDocumentStart, forMainFrameOnly: true))
        if onReturnToFarm != nil {
            configuration.userContentController.add(context.coordinator, name: "godBarn")
        }
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = false
        webView.allowsMagnification = true
        webView.underPageBackgroundColor = .windowBackgroundColor
        controller.initialURL = url
        controller.hasCommittedPage = false
        controller.webView = webView
        let destination = controller.nextPresentationRequest ?? URLRequest(url: controller.nextPresentationURL ?? url)
        controller.nextPresentationRequest = nil
        controller.nextPresentationURL = nil
        webView.load(destination)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        // Runtime and log updates must never reload an active game session.
    }

    static func dismantleNSView(_ webView: WKWebView, coordinator: Coordinator) {
        coordinator.invalidated = true
        webView.stopLoading()
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "godBarn")
        webView.navigationDelegate = nil
        webView.uiDelegate = nil
        if coordinator.controller.webView === webView {
            coordinator.controller.webView = nil
            coordinator.controller.hasCommittedPage = false
        }
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        let controller: GameWebController
        let onReturnToFarm: (() -> Void)?
        let onFarmLoaded: ((String) -> Void)?
        var invalidated = false
        private var navigationGeneration = UUID()

        init(controller: GameWebController, onReturnToFarm: (() -> Void)? = nil, onFarmLoaded: ((String) -> Void)? = nil) {
            self.controller = controller
            self.onReturnToFarm = onReturnToFarm
            self.onFarmLoaded = onFarmLoaded
        }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard !invalidated, onReturnToFarm != nil, message.name == "godBarn",
                  message.frameInfo.isMainFrame, message.webView === controller.webView,
                  let source = message.frameInfo.request.url, permitsMainFrame(source),
                  source.path == "/god-barn" || source.path.hasPrefix("/god-barn/"),
                  let body = message.body as? [String: Any],
                  body["type"] as? String == "returnToFarm" else { return }
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.invalidated else { return }
                self.onReturnToFarm?()
            }
        }

        private func permitsMainFrame(_ url: URL) -> Bool {
            url.scheme?.lowercased() == "http"
                && url.host?.lowercased() == "127.0.0.1"
                && url.port == 5501
                && url.user == nil && url.password == nil
        }

        private func publish(loading: Bool, error: String? = nil) {
            // WebKit can call a delegate during the representable's update.
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.invalidated else { return }
                self.controller.isLoading = loading
                if loading { self.controller.loadedFarmID = nil }
                if let error { self.controller.errorMessage = error }
                else if loading { self.controller.errorMessage = nil }
            }
        }

        private func openClickedExternalLink(_ action: WKNavigationAction) -> Bool {
            guard action.navigationType == .linkActivated,
                  let url = action.request.url,
                  ["http", "https"].contains(url.scheme?.lowercased() ?? "") else { return false }
            NSWorkspace.shared.open(url)
            return true
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { decisionHandler(.cancel); return }
            if action.targetFrame?.isMainFrame == false {
                // This does not intercept fetch, images, scripts, WASM, or SWFs.
                decisionHandler(.allow)
            } else if permitsMainFrame(url) {
                if onReturnToFarm != nil && action.shouldPerformDownload && GodBarnDownloadDelegate.permits(url) {
                    decisionHandler(.download)
                } else if action.targetFrame == nil {
                    decisionHandler(.cancel)
                    webView.load(action.request)
                } else { decisionHandler(.allow) }
            } else {
                decisionHandler(.cancel)
                if !openClickedExternalLink(action) {
                    publish(loading: false, error: "The game tried to leave its local server. External links can be opened by clicking them; the farm stays in this window.")
                }
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                     decisionHandler: @escaping @MainActor (WKNavigationResponsePolicy) -> Void) {
            guard response.isForMainFrame else { decisionHandler(.allow); return }
            guard let url = response.response.url, permitsMainFrame(url) else {
                decisionHandler(.cancel)
                publish(loading: false, error: "The local server returned a page that WebKit cannot display. View Activity for details.")
                return
            }
            if let http = response.response as? HTTPURLResponse, http.statusCode >= 400 {
                decisionHandler(.cancel)
                publish(loading: false, error: "The local server returned HTTP \(http.statusCode). Reload the page or view Activity for details.")
                return
            }
            if onReturnToFarm != nil, GodBarnDownloadDelegate.permits(url),
               let http = response.response as? HTTPURLResponse,
               http.value(forHTTPHeaderField: "Content-Disposition")?
                .trimmingCharacters(in: .whitespacesAndNewlines).lowercased().hasPrefix("attachment") == true {
                decisionHandler(.download)
                publish(loading: false)
                return
            }
            guard response.canShowMIMEType else {
                decisionHandler(.cancel)
                publish(loading: false, error: "The local server returned a page that WebKit cannot display. View Activity for details.")
                return
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            beginDownload(download, from: webView)
        }

        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            beginDownload(download, from: webView)
        }

        private func beginDownload(_ download: WKDownload, from webView: WKWebView) {
            guard !invalidated, onReturnToFarm != nil,
                  let url = download.originalRequest?.url, GodBarnDownloadDelegate.permits(url) else {
                download.cancel { _ in }
                return
            }
            let handler = GodBarnDownloadDelegate(download: download, owner: controller, window: webView.window)
            controller.downloads[handler.identifier] = handler
            download.delegate = handler
            publish(loading: false)
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url, permitsMainFrame(url) { webView.load(action.request) }
            else { _ = openClickedExternalLink(action) }
            return nil
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            navigationGeneration = UUID()
            publish(loading: true)
        }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            guard !invalidated else { return }
            controller.hasCommittedPage = true
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            publish(loading: false)
            guard !invalidated, onFarmLoaded != nil, webView.url?.path == "/ruffle.html" else { return }
            let generation = navigationGeneration
            webView.evaluateJavaScript("typeof getUserInfo === 'function' ? String(getUserInfo().uid) : null") { [weak self, weak webView] value, _ in
                guard let self, !self.invalidated, let webView, self.controller.webView === webView,
                      self.navigationGeneration == generation,
                      webView.url?.path == "/ruffle.html", let uid = value as? String else { return }
                self.controller.loadedFarmID = uid
                self.onFarmLoaded?(uid)
            }
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            navigationFailed(error)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            navigationFailed(error)
        }

        private func navigationFailed(_ error: Error) {
            let nsError = error as NSError
            if nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled { return }
            publish(loading: false, error: "The game page could not load: \(error.localizedDescription)")
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            publish(loading: false, error: "The game view stopped responding. Reload the page to reconnect to your local farm.")
        }

        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor () -> Void) {
            let alert = NSAlert()
            alert.messageText = "FarmVillage"
            alert.informativeText = message
            alert.addButton(withTitle: "OK")
            guard let window = webView.window else { completionHandler(); return }
            alert.beginSheetModal(for: window) { _ in completionHandler() }
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping @MainActor (Bool) -> Void) {
            let alert = NSAlert()
            alert.messageText = "FarmVillage"
            alert.informativeText = message
            alert.addButton(withTitle: "Continue")
            alert.addButton(withTitle: "Cancel")
            guard let window = webView.window else { completionHandler(false); return }
            alert.beginSheetModal(for: window) { result in completionHandler(result == .alertFirstButtonReturn) }
        }

        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                     defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                     completionHandler: @escaping @MainActor (String?) -> Void) {
            let alert = NSAlert()
            alert.messageText = "FarmVillage"
            alert.informativeText = prompt
            alert.addButton(withTitle: "OK")
            alert.addButton(withTitle: "Cancel")
            let field = NSTextField(string: defaultText ?? "")
            field.frame = NSRect(x: 0, y: 0, width: 320, height: 24)
            alert.accessoryView = field
            guard let window = webView.window else { completionHandler(nil); return }
            alert.beginSheetModal(for: window) { result in
                completionHandler(result == .alertFirstButtonReturn ? field.stringValue : nil)
            }
        }
    }
}
