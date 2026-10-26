import AppKit
import Combine
import Darwin
import Foundation

/// Owns only the supervised process launched by this application.
@MainActor
final class RuntimeController: ObservableObject {
    enum Phase: String {
        case idle, preparing, starting, running, stopping, failed

        var title: String {
            switch self {
            case .idle: return "Ready when you are"
            case .preparing: return "Preparing the runtime"
            case .starting: return "Opening your farm"
            case .running: return "Your farm is running"
            case .stopping: return "Finishing up"
            case .failed: return "Your attention is needed"
            }
        }

        var symbol: String {
            switch self {
            case .idle: return "leaf"
            case .preparing: return "shippingbox"
            case .starting: return "arrow.down.circle"
            case .running: return "checkmark.circle.fill"
            case .stopping: return "stop.circle"
            case .failed: return "exclamationmark.triangle"
            }
        }
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var message = "Prepare the runtime, then start your farm. Downloads begin only when you choose an action."
    @Published private(set) var logs = ""
    @Published private(set) var isPrepared = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var serverToken: String?
    @Published var pythonPath: String {
        didSet { UserDefaults.standard.set(pythonPath, forKey: "FarmVillage.PythonPath") }
    }

    let dataDirectory: URL
    let gameURL = URL(string: "http://127.0.0.1:5501/")!
    var godBarnURL: URL { gameURL.appendingPathComponent("god-barn", isDirectory: true) }
    var godBarnResumeURL: URL { godBarnURL.appendingPathComponent("resume") }
    var logURL: URL { dataDirectory.appendingPathComponent("Logs/wrapper.log") }
    var isBusy: Bool { [.preparing, .starting, .stopping].contains(phase) }
    var canPrepare: Bool { configurationError == nil && activeProcess == nil && !isBusy }
    var canStart: Bool { configurationError == nil && isPrepared && activeProcess == nil && !isBusy }
    var canStop: Bool { activeProcess != nil && phase != .stopping }
    var hasOwnedProcess: Bool { activeProcess != nil }
    var isConfigured: Bool { configurationError == nil }

    private var activeProcess: Process?
    private var activeAction: String?
    private var operationID: UUID?
    private var healthTask: Task<Void, Never>?
    private var logTask: Task<Void, Never>?
    private var logHandle: FileHandle?
    private var logReader: FileHandle?
    private var requestedStop = false
    private var failureAfterStop: String?
    private var terminationCompletions: [() -> Void] = []
    private let maximumLogLength = 180_000
    private let healthSession: URLSession
    private let configurationError: String?
    private var preparedMarker: URL { dataDirectory.appendingPathComponent("prepared.json") }

    init(dataDirectory requestedDirectory: URL? = nil) {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support", isDirectory: true)
        let defaultDirectory = support.appendingPathComponent("FarmVillage", isDirectory: true)
        let selection = Self.selectDataDirectory(defaultDirectory: defaultDirectory, requestedDirectory: requestedDirectory)
        dataDirectory = selection.directory
        configurationError = selection.error
        pythonPath = UserDefaults.standard.string(forKey: "FarmVillage.PythonPath") ?? ""
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 3
        configuration.timeoutIntervalForResource = 4
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.urlCache = nil
        healthSession = URLSession(configuration: configuration)
        if let configurationError {
            phase = .failed
            message = configurationError
            errorMessage = configurationError
            return
        }
        refreshPreparedState()
        if isPrepared { message = "The runtime has been prepared. Start your farm whenever you are ready." }
    }

    /// An explicit launch override keeps validation runs away from the user's farms.
    /// A malformed override disables file actions instead of falling back to user data.
    private static func selectDataDirectory(defaultDirectory: URL, requestedDirectory: URL?) -> (directory: URL, error: String?) {
        if let requestedDirectory {
            guard requestedDirectory.isFileURL, requestedDirectory.path.hasPrefix("/") else {
                return (defaultDirectory, "The farm data directory must be an absolute file path.")
            }
            return (requestedDirectory.standardizedFileURL, nil)
        }
        let arguments = ProcessInfo.processInfo.arguments
        let flag = "--farmvillage-data-dir"
        let matches = arguments.indices.filter { arguments[$0].hasPrefix(flag) }
        guard !matches.isEmpty else { return (defaultDirectory, nil) }
        let error = "Use exactly one --farmvillage-data-dir /absolute/folder or --farmvillage-data-dir=/absolute/folder."
        guard matches.count == 1, let index = matches.first else { return (defaultDirectory, error) }
        let argument = arguments[index]
        let path: String
        if argument == flag {
            guard index + 1 < arguments.count else { return (defaultDirectory, error) }
            path = arguments[index + 1]
        } else if argument.hasPrefix(flag + "=") {
            path = String(argument.dropFirst(flag.count + 1))
        } else {
            return (defaultDirectory, error)
        }
        guard path.hasPrefix("/") else { return (defaultDirectory, error) }
        return (URL(fileURLWithPath: path, isDirectory: true).standardizedFileURL, nil)
    }

    func prepare() {
        guard canPrepare else { return }
        launch(action: "prepare", phase: .preparing,
               message: "Installing the local Python environment and Ruffle. This needs an internet connection; progress appears in Activity.")
    }

    func start() {
        guard canStart else { return }
        launch(action: "start", phase: .starting,
               message: "Starting the preserved server. The first start downloads and extracts about 18 GiB of game archives; this may take a long time. Follow Activity for progress.")
    }

    func stop() {
        guard canStop else { return }
        beginStop()
    }

    /// App termination is deferred until the runtime supervisor has reaped its children.
    func shutdown(completion: @escaping () -> Void) {
        guard activeProcess != nil else { completion(); return }
        terminationCompletions.append(completion)
        if phase != .stopping { beginStop() }
    }

    func clearVisibleLogs() { logs = "" }
    func dismissError() { errorMessage = nil }

    func revealData() {
        guard configurationError == nil else { return }
        do {
            try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            NSWorkspace.shared.open(dataDirectory)
        } catch { reportHelperError("Could not open the farm data folder: \(error.localizedDescription)") }
    }

    func revealLog() {
        guard configurationError == nil else { return }
        do {
            try openLogIfNeeded()
            NSWorkspace.shared.activateFileViewerSelecting([logURL])
        } catch { reportHelperError("Could not open the log file: \(error.localizedDescription)") }
    }

    private func launch(action: String, phase nextPhase: Phase, message nextMessage: String) {
        guard activeProcess == nil else { return }
        errorMessage = nil
        requestedStop = false
        failureAfterStop = nil
        do {
            guard let resourceRoot = Bundle.main.resourceURL else {
                throw RuntimeError("The application bundle has no Resources folder. Rebuild the app using the included macOS project.")
            }
            let script = resourceRoot.appendingPathComponent("Scripts/runtime.sh")
            let runtime = resourceRoot.appendingPathComponent("Runtime", isDirectory: true)
            guard FileManager.default.fileExists(atPath: script.path),
                  FileManager.default.fileExists(atPath: runtime.appendingPathComponent("server.py").path) else {
                throw RuntimeError("The bundled runtime is missing. Rebuild the app using the included macOS project.")
            }
            try openLogIfNeeded()
            let token = UUID().uuidString
            let identifier = UUID()
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = [script.path, action, "--data-dir", dataDirectory.path,
                                 "--runtime", runtime.path, "--port", "5501", "--token", token,
                                 "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
            let chosenPython = pythonPath.trimmingCharacters(in: .whitespacesAndNewlines)
            if !chosenPython.isEmpty { process.arguments?.append(contentsOf: ["--python", chosenPython]) }
            process.currentDirectoryURL = dataDirectory
            process.standardInput = FileHandle.nullDevice
            // Direct file output preserves the final error even if the runtime
            // exits before the UI gets a chance to refresh its log view.
            process.standardOutput = logHandle
            process.standardError = logHandle
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONUNBUFFERED"] = "1"
            environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            process.environment = environment
            process.terminationHandler = { [weak self] finished in
                let exitCode = finished.terminationStatus
                Task { @MainActor [weak self] in
                    self?.processDidExit(identifier: identifier, exitCode: exitCode)
                }
            }
            activeProcess = process
            activeAction = action
            operationID = identifier
            phase = nextPhase
            message = nextMessage
            appendLog("\n[\(Date().formatted(date: .abbreviated, time: .standard))] \(action == "prepare" ? "Prepare runtime" : "Start farm")\n")
            do { try process.run() }
            catch {
                activeProcess = nil
                activeAction = nil
                operationID = nil
                throw error
            }
            followLog(identifier: identifier)
            if action == "start" { waitForServer(identifier: identifier, token: token) }
        } catch { report(error.localizedDescription) }
    }

    private func waitForServer(identifier: UUID, token: String) {
        healthTask?.cancel()
        healthTask = Task { [weak self] in
            guard let self else { return }
            let healthURL = self.gameURL.appendingPathComponent("health")
            while !Task.isCancelled {
                guard self.operationID == identifier, self.phase == .starting,
                      let process = self.activeProcess, process.isRunning else { return }
                do {
                    let request = URLRequest(url: healthURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 3)
                    let (data, response) = try await self.healthSession.data(for: request)
                    guard !Task.isCancelled, self.operationID == identifier,
                          self.activeProcess === process, process.isRunning,
                          self.phase == .starting else { return }
                    if let http = response as? HTTPURLResponse, http.statusCode == 200,
                       let result = try? JSONDecoder().decode(HealthResponse.self, from: data), result.status == "ok" {
                        guard result.wrapperToken == token else {
                            self.failureAfterStop = "Port 5501 is already serving another application. Stop that server, then start your farm again."
                            self.beginStop()
                            return
                        }
                        self.serverToken = token
                        self.phase = .running
                        self.message = "Your local farm is open. Game progress stays in your FarmVillage data folder."
                        self.appendLog("[wrapper] The owned server is ready at \(self.gameURL.absoluteString)\n")
                        return
                    }
                } catch {
                    // Startup includes the upstream asset download and deliberately has no short deadline.
                    if Task.isCancelled { return }
                }
                do { try await Task.sleep(nanoseconds: 1_000_000_000) }
                catch { return }
            }
        }
    }

    private func beginStop() {
        guard let process = activeProcess else { return }
        requestedStop = true
        healthTask?.cancel()
        healthTask = nil
        phase = .stopping
        message = "Stopping the runtime and its download processes. Your farm data will be kept."
        appendLog("\n[wrapper] Stop requested; waiting for the runtime supervisor to finish.\n")
        // runtime.sh execs the bundled supervisor. Its SIGTERM handler stops and
        // reaps the complete worker process group before the supervisor exits.
        if process.isRunning { process.terminate() }
    }

    private func processDidExit(identifier: UUID, exitCode: Int32) {
        guard operationID == identifier else { return }
        serverToken = nil
        healthTask?.cancel()
        healthTask = nil
        logTask?.cancel()
        logTask = nil
        readLogOutput()
        let finishedAction = activeAction
        activeProcess = nil
        activeAction = nil
        operationID = nil
        refreshPreparedState()
        appendLog("\n[wrapper] Runtime exited with status \(exitCode).\n")
        if let failure = failureAfterStop {
            failureAfterStop = nil
            report(failure)
        } else if requestedStop {
            phase = .idle
            message = finishedAction == "prepare" ? "Setup was cancelled. You can run Prepare Runtime again to continue." : "Your farm has stopped. Your saved data is ready for next time."
        } else if finishedAction == "prepare", exitCode == 0 {
            if isPrepared {
                phase = .idle
                message = "The runtime is ready. Start your farm to download any missing game assets and open the login page."
            } else { report("Setup exited successfully, but its runtime files are missing. View Activity, then prepare the runtime again.") }
        } else {
            report("The \(finishedAction == "prepare" ? "setup process" : "game server") stopped with status \(exitCode). Open Activity or the log file for details, then try again.")
        }
        requestedStop = false
        let completions = terminationCompletions
        terminationCompletions.removeAll()
        completions.forEach { $0() }
    }

    private func openLogIfNeeded() throws {
        guard logHandle == nil else { return }
        let files = try Self.openLogFiles(in: dataDirectory)
        logHandle = files.writer
        logReader = files.reader
    }

    /// All log descendants are opened relative to the canonical root descriptor,
    /// so a malformed Logs directory or leaf cannot redirect app output elsewhere.
    static func openLogFiles(in directory: URL) throws -> (writer: FileHandle, reader: FileHandle) {
        let root = directory.resolvingSymlinksInPath().standardizedFileURL
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let rootDescriptor = open(root.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard rootDescriptor >= 0 else { throw logOpenError("open the farm data directory") }
        defer { close(rootDescriptor) }
        if mkdirat(rootDescriptor, "Logs", 0o700) != 0, errno != EEXIST {
            throw logOpenError("create the Logs directory")
        }
        let logsDescriptor = openat(rootDescriptor, "Logs", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard logsDescriptor >= 0 else { throw logOpenError("open the Logs directory without following links") }
        defer { close(logsDescriptor) }

        let writerDescriptor = openat(logsDescriptor, "wrapper.log", O_WRONLY | O_CREAT | O_APPEND | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard writerDescriptor >= 0 else { throw logOpenError("open wrapper.log without following links") }
        var ownsWriter = true
        defer { if ownsWriter { close(writerDescriptor) } }
        var writerStatus = stat()
        guard fstat(writerDescriptor, &writerStatus) == 0 else { throw logOpenError("inspect wrapper.log") }
        guard writerStatus.st_mode & S_IFMT == S_IFREG, writerStatus.st_nlink == 1 else {
            throw RuntimeError("The wrapper log must be a regular file with no extra hard links.")
        }

        let readerDescriptor = openat(logsDescriptor, "wrapper.log", O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)
        guard readerDescriptor >= 0 else { throw logOpenError("open the wrapper log reader without following links") }
        var ownsReader = true
        defer { if ownsReader { close(readerDescriptor) } }
        var readerStatus = stat()
        guard fstat(readerDescriptor, &readerStatus) == 0 else { throw logOpenError("inspect the wrapper log reader") }
        guard readerStatus.st_mode & S_IFMT == S_IFREG, readerStatus.st_nlink == 1,
              readerStatus.st_dev == writerStatus.st_dev, readerStatus.st_ino == writerStatus.st_ino else {
            throw RuntimeError("The wrapper log changed while it was being opened. Restore a regular log file, then try again.")
        }

        let writer = FileHandle(fileDescriptor: writerDescriptor, closeOnDealloc: true)
        ownsWriter = false
        let reader = FileHandle(fileDescriptor: readerDescriptor, closeOnDealloc: true)
        ownsReader = false
        try reader.seekToEnd()
        return (writer, reader)
    }

    private static func logOpenError(_ action: String) -> RuntimeError {
        let code = errno
        return RuntimeError("Could not \(action): \(String(cString: strerror(code))).")
    }

    private func appendLog(_ text: String) {
        guard let logHandle else { appendVisibleLog(text); return }
        do {
            try logHandle.write(contentsOf: Data(text.utf8))
            readLogOutput()
        }
        catch {
            appendVisibleLog(text)
        }
    }

    private func followLog(identifier: UUID) {
        logTask?.cancel()
        logTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.operationID == identifier else { return }
                self.readLogOutput()
                do { try await Task.sleep(nanoseconds: 350_000_000) }
                catch { return }
            }
        }
    }

    private func readLogOutput() {
        guard let logReader else { return }
        // A regular file reaches EOF immediately; unlike a pipe, exit-time
        // draining cannot wait on an inherited descriptor in another process.
        do {
            let previousOffset = try logReader.offset()
            let endOffset = try logReader.seekToEnd()
            let earliestVisibleOffset = endOffset > UInt64(maximumLogLength)
                ? endOffset - UInt64(maximumLogLength) : 0
            let nextOffset = max(previousOffset, earliestVisibleOffset)
            try logReader.seek(toOffset: nextOffset)
            if nextOffset > previousOffset {
                appendVisibleLog("\n[wrapper] Earlier output is available in the complete log file.\n")
            }
            guard let data = try logReader.read(upToCount: maximumLogLength), !data.isEmpty else { return }
            appendVisibleLog(String(decoding: data, as: UTF8.self))
        } catch { /* The persistent log remains available through Finder. */ }
    }

    private func appendVisibleLog(_ text: String) {
        logs.append(text)
        if logs.count > maximumLogLength { logs = String(logs.suffix(maximumLogLength)) }
    }

    private func refreshPreparedState() {
        guard let data = try? Data(contentsOf: preparedMarker),
              let marker = try? JSONDecoder().decode(PreparedRuntime.self, from: data),
              marker.schema == 2 else {
            isPrepared = false
            return
        }
        isPrepared = FileManager.default.isExecutableFile(atPath: dataDirectory.appendingPathComponent("venv/bin/python").path)
    }

    private func reportHelperError(_ text: String) {
        errorMessage = text
        appendLog("[wrapper] \(text)\n")
    }

    private func report(_ text: String) {
        errorMessage = text
        phase = .failed
        message = text
        appendLog("[wrapper] \(text)\n")
    }

    private struct HealthResponse: Decodable {
        let status: String
        let wrapperToken: String?
        enum CodingKeys: String, CodingKey {
            case status
            case wrapperToken = "wrapper_token"
        }
    }

    private struct PreparedRuntime: Decodable {
        let schema: Int
    }

    private struct RuntimeError: LocalizedError {
        let description: String
        init(_ description: String) { self.description = description }
        var errorDescription: String? { description }
    }
}
