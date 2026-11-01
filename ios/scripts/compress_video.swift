// Сжимает запись демо до 720p — чтобы переслать (исходник с симулятора весит сотни МБ).
// Запуск: swift ios/scripts/compress_video.swift <вход.mp4> <выход.mp4>
import AVFoundation
import Foundation

let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let done = DispatchSemaphore(value: 0)
Task {
    do {
        guard let export = AVAssetExportSession(asset: AVURLAsset(url: input), presetName: AVAssetExportPreset1280x720)
        else { throw CocoaError(.fileWriteUnknown) }
        try? FileManager.default.removeItem(at: output)
        try await export.export(to: output, as: .mp4)
        print("720p → \(output.path)")
    } catch {
        print("ошибка: \(error)")
    }
    done.signal()
}
done.wait()
