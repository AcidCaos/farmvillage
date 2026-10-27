import AppKit
import Darwin
import Foundation

@main
struct NativeLaunchSmoke {
    @MainActor
    static func main() async {
        let operation = Task { @MainActor in try await run() }
        var signalSources: [DispatchSourceSignal] = []
        for number in [SIGINT, SIGTERM] {
            signal(number, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
            source.setEventHandler { operation.cancel() }
            source.resume()
            signalSources.append(source)
        }
        defer { signalSources.forEach { $0.cancel() } }
        do { try await operation.value }
        catch {
            print("FAIL: \(error.localizedDescription)")
            exit(error is CleanupFailure ? 75 : EXIT_FAILURE)
        }
    }

    @MainActor
    static func run() async throws {
        let arguments = CommandLine.arguments
        let paired = arguments.count == 4 && arguments[3] == "--paired"
        guard (arguments.count == 3 || paired), arguments[1].hasPrefix("/"), arguments[2].hasPrefix("/") else {
            throw SmokeFailure("usage: NativeLaunchSmoke /absolute/FarmVillage.app /absolute/isolated-data [--paired]")
        }
        let applicationURL = URL(fileURLWithPath: arguments[1], isDirectory: true).standardizedFileURL
        var owned: [NSRunningApplication] = []
        do {
            for index in 0..<(paired ? 2 : 1) {
                try Task.checkCancellation()
                let previousPIDs = Set(NSWorkspace.shared.runningApplications.map(\.processIdentifier))
                let configuration = NSWorkspace.OpenConfiguration()
                let dataDirectory = index == 0 ? arguments[2] : URL(fileURLWithPath: arguments[2], isDirectory: true).appendingPathComponent("SecondInstance").path
                configuration.arguments = ["--farmvillage-data-dir", dataDirectory]
                configuration.activates = false
                configuration.hides = true
                configuration.createsNewApplicationInstance = true
                let application = try await NSWorkspace.shared.openApplication(at: applicationURL, configuration: configuration)
                guard application.bundleURL?.standardizedFileURL == applicationURL,
                      !previousPIDs.contains(application.processIdentifier) else {
                    throw SmokeFailure("Launch Services returned an existing or unexpected application; it was left alone.")
                }
                owned.append(application)
                try Task.checkCancellation()
                let launchDeadline = Date().addingTimeInterval(10)
                while !application.isFinishedLaunching && !application.isTerminated && Date() < launchDeadline {
                    try await Task.sleep(nanoseconds: 100_000_000)
                }
                guard application.isFinishedLaunching, !application.isTerminated else {
                    throw SmokeFailure("The application exited or did not finish launching within 10 seconds.")
                }
                print("PASS: native application \(index + 1) finished launching, PID \(application.processIdentifier)")
            }
            guard !paired || (owned.count == 2 && owned[0].processIdentifier != owned[1].processIdentifier && owned.allSatisfy { !$0.isTerminated }) else {
                throw SmokeFailure("The same application bundle did not remain open as two separate idle processes.")
            }
            if paired { print("PASS: the same bundle launched two distinct idle instances with explicit isolated data directories") }
            for application in owned {
                guard application.terminate() else { throw SmokeFailure("The application refused its normal Quit request.") }
                let quitDeadline = Date().addingTimeInterval(10)
                while !application.isTerminated && Date() < quitDeadline {
                    try await Task.sleep(nanoseconds: 100_000_000)
                }
                guard application.isTerminated else { throw SmokeFailure("Normal Quit did not finish within 10 seconds.") }
                print("PASS: native application PID \(application.processIdentifier) accepted normal Quit and exited")
            }
        } catch {
            let originalError = error
            // Cleanup must continue even when SIGINT/SIGTERM cancelled the test.
            let remaining = await Task { @MainActor in
                var unresolved: [pid_t] = []
                for application in owned where !application.isTerminated {
                    _ = application.forceTerminate()
                    let deadline = Date().addingTimeInterval(10)
                    while !application.isTerminated && Date() < deadline {
                        try? await Task.sleep(nanoseconds: 100_000_000)
                    }
                    if !application.isTerminated { unresolved.append(application.processIdentifier) }
                }
                return unresolved
            }.value
            guard remaining.isEmpty else {
                throw CleanupFailure(message: "\(originalError.localizedDescription) Owned application cleanup did not finish for PIDs \(remaining); preserve the isolated data directory.")
            }
            throw originalError
        }
    }

    struct SmokeFailure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }

    struct CleanupFailure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }
}
