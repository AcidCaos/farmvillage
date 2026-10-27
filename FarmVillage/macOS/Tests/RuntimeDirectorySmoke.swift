import Foundation

@main
struct RuntimeDirectorySmoke {
    @MainActor
    static func main() throws {
        let mode = CommandLine.arguments[1]
        let expectedPath = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : ""
        let controller = mode == "injected"
            ? RuntimeController(dataDirectory: URL(fileURLWithPath: expectedPath, isDirectory: true))
            : RuntimeController()
        if mode == "valid" || mode == "valid_equals" {
            precondition(controller.dataDirectory.path == URL(fileURLWithPath: expectedPath).standardizedFileURL.path)
            precondition(controller.phase == .idle && controller.canPrepare && !controller.canStart)
        } else if mode == "injected" {
            precondition(controller.dataDirectory.path == URL(fileURLWithPath: expectedPath).standardizedFileURL.path)
            precondition(controller.phase == .idle && controller.canPrepare && !controller.canStart)
        } else {
            precondition(controller.phase == .failed)
            precondition(controller.errorMessage != nil)
            precondition(!controller.canPrepare && !controller.canStart)
        }
        print("PASS: \(mode) data-directory configuration")
    }
}
