import Foundation
import Speech

let files = [
    "/Users/samuel/MC/成品视频/1.1.mp4",
    "/Users/samuel/MC/成品视频/1.2.mp4",
    "/Users/samuel/MC/成品视频/1.3.mp4"
]

let locale = Locale(identifier: "zh_CN")
guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
    fatalError("Speech recognizer is unavailable")
}

let group = DispatchGroup()
var authorized = false
group.enter()
SFSpeechRecognizer.requestAuthorization { status in
    authorized = status == .authorized
    group.leave()
}
group.wait()

guard authorized else {
    fatalError("Speech recognition is not authorized")
}

for file in files {
    let url = URL(fileURLWithPath: file)
    let request = SFSpeechURLRecognitionRequest(url: url)
    request.shouldReportPartialResults = false
    if #available(macOS 13.0, *) {
        request.addsPunctuation = true
    }

    let sem = DispatchSemaphore(value: 0)
    var printed = false
    recognizer.recognitionTask(with: request) { result, error in
        if let result, result.isFinal {
            print("FILE\t\(file)")
            for segment in result.bestTranscription.segments {
                print(String(format: "SEG\t%.3f\t%.3f\t%@", segment.timestamp, segment.duration, segment.substring))
            }
            printed = true
            sem.signal()
        } else if let error {
            print("ERROR\t\(file)\t\(error.localizedDescription)")
            sem.signal()
        }
    }
    _ = sem.wait(timeout: .now() + 120)
    if !printed {
        print("NO_RESULT\t\(file)")
    }
}
