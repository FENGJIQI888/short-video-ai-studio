import AVFoundation
import Foundation

let inputs = [
    "/Users/samuel/MC/成品视频/1.1.mp4",
    "/Users/samuel/MC/成品视频/1.2.mp4",
    "/Users/samuel/MC/成品视频/1.3.mp4"
]

let output = "/Users/samuel/MC/成品视频/123_合成.mp4"
let outputURL = URL(fileURLWithPath: output)
try? FileManager.default.removeItem(at: outputURL)

let composition = AVMutableComposition()
guard let videoTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
    fatalError("Could not create video track")
}
let audioTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)

var cursor = CMTime.zero
var preferredTransform = CGAffineTransform.identity

for (index, path) in inputs.enumerated() {
    let asset = AVURLAsset(url: URL(fileURLWithPath: path))
    let duration = asset.duration
    let range = CMTimeRange(start: .zero, duration: duration)

    guard let sourceVideo = asset.tracks(withMediaType: .video).first else {
        fatalError("Missing video track: \(path)")
    }

    if index == 0 {
        preferredTransform = sourceVideo.preferredTransform
        videoTrack.preferredTransform = preferredTransform
    }

    try videoTrack.insertTimeRange(range, of: sourceVideo, at: cursor)

    if let sourceAudio = asset.tracks(withMediaType: .audio).first, let audioTrack {
        try audioTrack.insertTimeRange(range, of: sourceAudio, at: cursor)
    }

    cursor = CMTimeAdd(cursor, duration)
}

guard let exporter = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else {
    fatalError("Could not create exporter")
}

exporter.outputURL = outputURL
exporter.outputFileType = .mp4
exporter.shouldOptimizeForNetworkUse = true

let semaphore = DispatchSemaphore(value: 0)
exporter.exportAsynchronously {
    semaphore.signal()
}
semaphore.wait()

switch exporter.status {
case .completed:
    print(output)
case .failed:
    fatalError(exporter.error?.localizedDescription ?? "Export failed")
case .cancelled:
    fatalError("Export cancelled")
default:
    fatalError("Export ended with status \(exporter.status.rawValue)")
}
