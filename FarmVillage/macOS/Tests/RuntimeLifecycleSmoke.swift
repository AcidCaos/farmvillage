import Foundation

/// Run from the temporary .app bundle assembled by run-runtime-lifecycle-smoke.sh.
/// Its Resources come from a real native build; farm data must be an isolated,
/// already prepared fixture containing the desired small or complete asset set.
@main
struct RuntimeLifecycleSmoke {
    @MainActor
    static func main() async {
        do { try await run() }
        catch {
            print("FAIL: \(error.localizedDescription)")
            exit(EXIT_FAILURE)
        }
    }

    @MainActor
    static func run() async throws {
        guard CommandLine.arguments.count == 2, CommandLine.arguments[1].hasPrefix("/") else {
            throw SmokeFailure("usage: RuntimeLifecycleSmoke /absolute/isolated-prepared-data")
        }
        let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let controller = RuntimeController(dataDirectory: directory)
        guard controller.isPrepared, controller.canStart else {
            throw SmokeFailure("The isolated runtime must already be prepared; this check never runs setup.")
        }
        guard await health(at: controller.gameURL) == nil else {
            throw SmokeFailure("Port 5501 already serves an application; stop the owned fixture before running this check.")
        }

        do {
            controller.start()
            try await waitForRunning(controller)
            guard let firstToken = await health(at: controller.gameURL), UUID(uuidString: firstToken) != nil else {
                throw SmokeFailure("The first server was not ready with its generated ownership token.")
            }
            print("PASS: RuntimeController started the bundled server and verified its ownership token")

            controller.stop()
            try await waitForStopped(controller)
            guard await health(at: controller.gameURL) == nil else {
                throw SmokeFailure("The stopped runtime still responds on its health endpoint.")
            }
            print("PASS: Stop reaped the runtime and released its port")

            controller.start()
            try await waitForRunning(controller)
            guard let secondToken = await health(at: controller.gameURL), secondToken != firstToken else {
                throw SmokeFailure("Restart did not produce a new ownership token.")
            }
            print("PASS: restart reached ready with a new ownership token")

            var shutdownCompleted = false
            controller.shutdown { shutdownCompleted = true }
            try await waitForStopped(controller)
            guard shutdownCompleted else { throw SmokeFailure("Shutdown did not invoke its completion callback.") }
            guard await health(at: controller.gameURL) == nil else {
                throw SmokeFailure("The shutdown runtime still responds on its health endpoint.")
            }
            print("PASS: Shutdown reaped the runtime and invoked its completion callback")
        } catch {
            print("Runtime diagnostics:\n\(controller.logs.suffix(12_000))")
            if controller.canStop { controller.stop() }
            try? await waitForStopped(controller)
            throw error
        }
    }

    @MainActor
    static func waitForRunning(_ controller: RuntimeController) async throws {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if controller.phase == .running { return }
            if controller.phase == .failed { throw SmokeFailure(controller.message) }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw SmokeFailure("Runtime startup did not become ready within 90 seconds.")
    }

    @MainActor
    static func waitForStopped(_ controller: RuntimeController) async throws {
        let deadline = Date().addingTimeInterval(20)
        while Date() < deadline {
            if !controller.hasOwnedProcess && controller.phase == .idle { return }
            if !controller.hasOwnedProcess && controller.phase == .failed { throw SmokeFailure(controller.message) }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw SmokeFailure("Runtime shutdown did not finish within 20 seconds.")
    }

    static func health(at baseURL: URL) async -> String? {
        do {
            let request = URLRequest(url: baseURL.appendingPathComponent("health"),
                                     cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 2)
            let (data, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200,
                  let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  result["status"] as? String == "ok" else { return nil }
            return result["wrapper_token"] as? String
        } catch { return nil }
    }

    struct SmokeFailure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}
