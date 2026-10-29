import Foundation

/// The filename contract (single source of truth): one lesson, one file.
/// Mirrors `Names.java` on Android and `stamp()` in the web recorder.
/// The pipeline takes the largest media file in the lesson folder as the
/// lesson, so takes need no step names or session codes — only a
/// timestamp that can never collide.
enum Names {
    static func stamp(from date: Date = Date()) -> String {
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.dateFormat = "yyyyMMdd-HHmmss"
        let base = fmt.string(from: date)
        var millis = Int64(date.timeIntervalSince1970 * 1000) % 1000
        if millis < 0 { millis += 1000 }
        return String(format: "%@-%03d", base, millis)
    }

    static func lessonName(_ ext: String) -> String {
        var e = ext
        if e.hasPrefix(".") { e = String(e.dropFirst()) }
        return "unwritten_lesson_" + stamp() + "." + e
    }
}
