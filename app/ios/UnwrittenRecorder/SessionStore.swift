import AVFoundation
import UIKit

/// One row in the sessions list. Mirrors the Android session rows and
/// the web recorder's clipHTML: left status icon, middle date + length,
/// right share/download action.
struct SessionRow: Identifiable {
    enum RightKind: Equatable {
        case download
        case share
        case progress(Int)
        case processing
        case failed
    }

    let name: String
    let url: URL
    let leftIcon: String
    let middleText: String
    let rightKind: RightKind

    var id: String { name }
}

/// Lessons on this device + their Cloud copies. Lessons live in the
/// app's clips folder (Documents/clips — visible in the Files app, no
/// permission needed) and export through the share sheet. Cloud is
/// strictly additive: the on-device save always happens first and never
/// depends on the upload. Mirrors MainActivity's clips + Cloud sections
/// and the web recorder's saveBlob/Cloud flow.
@MainActor
final class SessionStore: ObservableObject {
    @Published var rows: [SessionRow] = []
    @Published var status: String = "Point the camera at the mentor's hands and the work. Press Record, let the lesson happen, press Stop at the end."
    @Published var cloudOn: Bool = true

    let clipsDir: URL
    let cloud = CloudStore()
    private var durationCache: [String: String] = [:]
    private var inFlight: Set<String> = []
    private var polling: Set<String> = []
    private var uploadTasks: [String: Task<Void, Never>] = [:]

    @MainActor
    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        clipsDir = docs.appendingPathComponent("clips", isDirectory: true)
        try? FileManager.default.createDirectory(at: clipsDir, withIntermediateDirectories: true)
        cloudOn = cloud.cloudEnabledCfg()
        NotificationCenter.default.addObserver(forName: .uwCloudProgress, object: nil, queue: .main) { [weak self] _ in
            // Delivered on the main queue by construction.
            MainActor.assumeIsolated { self?.refresh() }
        }
        refresh()
    }

    // ---------- lessons ----------

    private func clipFiles() -> [URL] {
        let files = (try? FileManager.default.contentsOfDirectory(
            at: clipsDir, includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles])) ?? []
        return files
            .filter { mimeFor($0.lastPathComponent) != nil }
            .sorted {
                let da = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                let db = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                return da > db
            }
    }

    private func mimeFor(_ name: String) -> String? {
        let n = name.lowercased()
        if n.hasSuffix(".mp4") { return "video/mp4" }
        if n.hasSuffix(".mov") { return "video/quicktime" }
        if n.hasSuffix(".m4v") { return "video/x-m4v" }
        if n.hasSuffix(".webm") { return "video/webm" }
        if n.hasSuffix(".m4a") { return "audio/mp4" }
        if n.hasSuffix(".wav") { return "audio/x-wav" }
        if n.hasSuffix(".jpg") || n.hasSuffix(".jpeg") { return "image/jpeg" }
        return nil
    }

    // left icon: ☁ if cloud-backed, otherwise the phone 📱
    func leftIconFor(_ name: String) -> String {
        guard let link = cloud.cloudLink(name) else { return "📱" }
        switch link["state"] as? String ?? "" {
        case "uploading": return "☁↑"
        case "processing": return "☁…"
        case "failed": return "☁!"
        default: return "☁"
        }
    }

    func displayDateFor(_ name: String) -> String {
        // unwritten_lesson_20261029-064439-473.mp4 -> Oct 29, 2026 06:44
        var base = name
        if let us = base.lastIndex(of: "_") { base = String(base[base.index(after: us)...]) }
        if let dot = base.lastIndex(of: ".") { base = String(base[..<dot]) }
        if base.count >= 15 { base = String(base.prefix(15)) } // yyyyMMdd-HHmmss
        let src = DateFormatter()
        src.locale = Locale(identifier: "en_US_POSIX")
        src.dateFormat = "yyyyMMdd-HHmmss"
        guard let date = src.date(from: base) else { return name }
        let dst = DateFormatter()
        dst.locale = Locale(identifier: "en_US")
        dst.dateFormat = "MMM d, yyyy HH:mm"
        return dst.string(from: date)
    }

    private func durationText(_ ms: Int64) -> String {
        let s = ms / 1000
        let m = (s / 60) % 60
        let h = s / 3600
        if h > 0 { return String(format: "%d:%02d:%02d", h, m, s % 60) }
        return String(format: "%d:%02d", m, s % 60)
    }

    private func rightKindFor(_ name: String) -> SessionRow.RightKind {
        guard let link = cloud.cloudLink(name) else { return .download }
        switch link["state"] as? String ?? "" {
        case "uploading": return .progress((link["progress"] as? Int) ?? 0)
        case "processing":
            if let vid = link["videoId"] as? String, !vid.isEmpty { return .share }
            return .processing
        case "failed": return .failed
        default: return .share
        }
    }

    func refresh() {
        rows = clipFiles().map { file in
            let name = file.lastPathComponent
            let dur = durationCache[name] ?? ""
            let middle = dur.isEmpty ? displayDateFor(name) : displayDateFor(name) + "  •  " + dur
            return SessionRow(name: name, url: file, leftIcon: leftIconFor(name),
                              middleText: middle, rightKind: rightKindFor(name))
        }
        for file in clipFiles() where durationCache[file.lastPathComponent] == nil {
            loadDuration(for: file)
        }
    }

    private func loadDuration(for file: URL) {
        let name = file.lastPathComponent
        durationCache[name] = ""
        Task {
            let asset = AVURLAsset(url: file)
            if let duration = try? await asset.load(.duration), duration.isValid, !duration.isIndefinite {
                let ms = Int64(CMTimeGetSeconds(duration) * 1000)
                durationCache[name] = durationText(ms)
            } else {
                durationCache[name] = ""
            }
            refresh()
        }
    }

    func url(for name: String) -> URL? {
        let url = clipsDir.appendingPathComponent(name)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    // ---------- record handoff ----------

    /// Remuxes the finished temp .mov to the final .mp4 lesson (H.264/AAC
    /// passthrough — no re-encode) and registers it. Mirrors Android's
    /// stopRecording: refresh the list, then maybe upload. An empty or
    /// failed take is reported on screen, never swallowed.
    func finishRecording(tempURL: URL?) {
        guard let tempURL else { return } // message already shown
        let size = (try? FileManager.default.attributesOfItem(atPath: tempURL.path)[.size] as? Int64) ?? 0
        guard size > 0 else {
            try? FileManager.default.removeItem(at: tempURL)
            status = "⚠️ That take was empty — nothing was captured. Record the lesson again."
            return
        }
        let stamp = Names.stamp()
        let mp4URL = clipsDir.appendingPathComponent("unwritten_lesson_" + stamp + ".mp4")
        let asset = AVURLAsset(url: tempURL)
        guard let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetPassthrough) else {
            keepMovFallback(tempURL: tempURL, stamp: stamp)
            return
        }
        session.outputURL = mp4URL
        session.outputFileType = .mp4
        // The export handler is @Sendable and fires on an arbitrary queue;
        // status/error reads after completion are the API's contract, so
        // the session crosses threads in an unchecked box.
        let box = ExportBox(session)
        session.exportAsynchronously { [weak self] in
            let status = box.session.status
            let message = box.session.error?.localizedDescription
            guard let self else { return }
            Task { @MainActor in
                try? FileManager.default.removeItem(at: tempURL)
                switch status {
                case .completed:
                    self.registerLesson(url: mp4URL)
                case .cancelled:
                    self.status = "⚠️ That take was interrupted before it finished. Record the lesson again."
                default:
                    // Passthrough failed (unexpected codec mix) — keep the
                    // .mov rather than lose the lesson; the pipeline takes
                    // the largest media file whatever its extension.
                    try? FileManager.default.removeItem(at: mp4URL)
                    self.status = "⚠️ MP4 remux failed (\(message ?? "unknown")) — kept the original recording."
                    let movURL = self.clipsDir.appendingPathComponent("unwritten_lesson_" + stamp + ".mov")
                    try? FileManager.default.moveItem(at: tempURL, to: movURL)
                    self.registerLesson(url: movURL)
                }
            }
        }
    }

    private func keepMovFallback(tempURL: URL, stamp: String) {
        let movURL = clipsDir.appendingPathComponent("unwritten_lesson_" + stamp + ".mov")
        do {
            try FileManager.default.moveItem(at: tempURL, to: movURL)
            status = "⚠️ MP4 remux unavailable — kept the original recording."
            registerLesson(url: movURL)
        } catch {
            status = "⚠️ Could not keep that take: \(error.localizedDescription)"
        }
    }

    private func registerLesson(url: URL) {
        status = "✅ Session saved — on this device (sessions below). Hand the file to whoever runs the pipeline."
        refresh()
        maybeCloudUpload(url.lastPathComponent)
    }

    // ---------- export / download ----------

    /// Bulk export, like Android's Export button: an explicit tap shares
    /// every session (Save to Files, AirDrop, …). Shown only with Cloud
    /// off, as the offline fallback.
    func exportSessions() {
        let files = clipFiles()
        if files.isEmpty {
            status = "Exported 0 sessions — nothing recorded yet."
            return
        }
        presentShare(items: files)
        status = "Exported \(files.count) sessions — pick a destination to save them."
    }

    func downloadSingle(_ name: String) {
        guard let url = url(for: name) else {
            status = "That session file is missing from this device."
            return
        }
        presentShare(items: [url])
    }

    // ---------- Cloud ----------

    func toggleCloud() {
        cloud.enabled.toggle()
        cloudOn = cloud.cloudEnabledCfg()
        refresh()
        status = cloud.cloudEnabledCfg()
            ? "☁️ Cloud on. New video sessions will also upload for streamed playback; the ↗ action on each session offers its link when ready."
            : "☁️ Cloud off. Sessions stay on this device only. Export sessions below to move them."
    }

    func paintCloudToggle() {
        cloudOn = cloud.cloudEnabledCfg()
    }

    func cloudWatchUrl(_ name: String) -> String? {
        cloud.watchUrl(for: name)
            ?? (cloud.lastLink.isEmpty ? nil : cloud.lastLink)
    }

    /// Per-session share, like Android: the link is copied, then offered
    /// through the share sheet.
    func shareCloudLinkFor(_ name: String) {
        guard let url = cloudWatchUrl(name) else {
            status = "No Cloud link yet for this session."
            return
        }
        UIPasteboard.general.string = url
        presentShare(items: [url])
    }

    func maybeCloudUpload(_ name: String) {
        guard url(for: name) != nil, cloud.cloudEnabledCfg() else { return }
        let link = cloud.cloudLink(name)
        let st = (link?["state"] as? String) ?? ""
        if st == "ready" { return }
        if st == "processing" {
            pollCloud(name, videoId: (link?["videoId"] as? String) ?? "")
            return
        }
        if st == "uploading", inFlight.contains(name) { return }
        startCloudUpload(name)
    }

    func startCloudUpload(_ name: String) {
        guard cloud.cloudEnabledCfg() else {
            status = "Turn Cloud on first."
            return
        }
        guard !inFlight.contains(name) else { return }
        guard let fileURL = url(for: name) else {
            status = "That session file is missing from this device."
            return
        }
        inFlight.insert(name)
        let link = cloud.cloudLink(name)
        let savedUrl = link?["uploadUrl"] as? String
        let savedVid = link?["videoId"] as? String
        cloud.setCloudLink(name, state: "uploading", videoId: savedVid,
                           libraryId: nil, uploadUrl: savedUrl, progress: 0)
        refresh()
        status = "☁️ Uploading to Cloud… The session is already saved on this device."
        // The uploader's callbacks fire on background executors: they
        // persist link state straight into the (thread-safe) CloudStore
        // and ping the main queue for a row refresh. Mirrors Android's
        // onSession/onProgress/onUploaded listener methods.
        let cloud = self.cloud
        uploadTasks[name]?.cancel()
        uploadTasks[name] = Task { [weak self] in
            guard let self else { return }
            defer {
                self.inFlight.remove(name)
                self.uploadTasks.removeValue(forKey: name)
            }
            guard var uploader = self.cloud.uploader() else {
                self.cloudFailed(name, videoId: savedVid, message: "Cloud settings incomplete.")
                return
            }
            do {
                let videoId = try await uploader.upload(
                    fileURL: fileURL, savedUploadUrl: savedUrl, savedVideoId: savedVid,
                    onSession: { creds, uploadUrl in
                        cloud.setCloudLink(name, state: "uploading", videoId: creds.videoId,
                                           libraryId: creds.libraryId, uploadUrl: uploadUrl, progress: -1)
                        NotificationCenter.default.post(name: .uwCloudProgress, object: name)
                    },
                    onProgress: { sent, total in
                        let pct = total > 0 ? Int(sent * 100 / total) : 0
                        cloud.setCloudLink(name, state: "uploading", videoId: nil,
                                           libraryId: nil, uploadUrl: nil, progress: pct)
                        NotificationCenter.default.post(name: .uwCloudProgress, object: name)
                    })
                self.cloud.setCloudLink(name, state: "processing", videoId: videoId,
                                        libraryId: nil, uploadUrl: nil, progress: 100)
                self.refresh()
                self.cloudFinished(name, videoId: videoId)
            } catch is CancellationError {
                self.cloudFailed(name, videoId: savedVid, message: "upload cancelled")
            } catch let CloudError.message(message) {
                self.cloudFailed(name, videoId: savedVid, message: message)
            } catch {
                self.cloudFailed(name, videoId: savedVid, message: error.localizedDescription)
            }
        }
    }

    private func cloudFinished(_ name: String, videoId: String) {
        var lib = (cloud.cloudLink(name)?["libraryId"] as? String) ?? ""
        if lib.isEmpty { lib = cloud.libraryId }
        let url = "https://player.mediadelivery.net/embed/" + lib + "/" + videoId
        cloud.setCloudLink(name, state: "ready", videoId: videoId,
                           libraryId: lib, uploadUrl: nil, progress: 100)
        cloud.lastLink = url
        cloud.lastName = name
        UIPasteboard.general.string = url
        status = "☁️ Uploaded. Cloud is preparing the streaming version — the ↗ share action on the session offers its link when ready."
        refresh()
    }

    private func cloudFailed(_ name: String, videoId: String?, message: String) {
        cloud.setCloudLink(name, state: "failed", videoId: videoId,
                           libraryId: nil, uploadUrl: nil, progress: -1)
        status = "☁️ Cloud upload didn't finish (\(message)) The session is safe on this device — tap ! on the session when the connection is better."
        refresh()
    }

    private func pollCloud(_ name: String, videoId: String) {
        if videoId.isEmpty || polling.contains(name) { return }
        polling.insert(name)
        Task { [weak self] in
            guard let self else { return }
            defer { self.polling.remove(name) }
            guard let uploader = self.cloud.uploader() else { return }
            for _ in 0 ..< 120 {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if Task.isCancelled { return }
                let st = await uploader.videoStatus(videoId)
                if st == 4 {
                    self.cloudFinished(name, videoId: videoId)
                    return
                }
                if st == 5 || st == 6 {
                    self.cloudFailed(name, videoId: videoId, message: "Cloud encoding failed.")
                    return
                }
            }
        }
    }

    /// Resume interrupted uploads after the app restarts, like Android's
    /// cloudResumePending and the web recorder's cloudResumePending.
    func cloudResumePending() {
        if !cloud.cloudEnabledCfg() { return }
        for (name, link) in cloud.links() {
            guard url(for: name) != nil else { continue }
            switch (link["state"] as? String) ?? "" {
            case "processing":
                pollCloud(name, videoId: (link["videoId"] as? String) ?? "")
            case "uploading":
                startCloudUpload(name)
            default:
                break
            }
        }
    }

    /// Long-press a session to delete it, like Android and the web —
    /// cloud copy first, and the local session is kept if that fails.
    func deleteLesson(_ name: String) {
        uploadTasks[name]?.cancel()
        Task { [weak self] in
            guard let self else { return }
            let link = self.cloud.cloudLink(name)
            let videoId = (link?["videoId"] as? String) ?? ""
            if !videoId.isEmpty {
                do {
                    guard let uploader = self.cloud.uploader() else {
                        throw CloudError.message("Cloud settings incomplete.")
                    }
                    try await uploader.deleteVideo(videoId)
                } catch {
                    let message: String
                    if case let CloudError.message(m) = error { message = m } else {
                        message = error.localizedDescription
                    }
                    self.status = "☁️ Couldn't delete the cloud copy (\(message)) Keeping the local session so nothing is lost."
                    return
                }
            }
            try? FileManager.default.removeItem(at: self.clipsDir.appendingPathComponent(name))
            self.cloud.delCloudLink(name)
            self.inFlight.remove(name)
            self.polling.remove(name)
            self.durationCache.removeValue(forKey: name)
            if name == self.cloud.lastName { self.cloud.clearLastLink() }
            self.refresh()
            self.status = "🗑 Session deleted from this device" + (videoId.isEmpty ? "." : " and the cloud.")
        }
    }

    func retryCloud(_ name: String) {
        guard url(for: name) != nil else {
            status = "☁️ That session is no longer stored on this device, so it can't be re-uploaded from here."
            return
        }
        startCloudUpload(name)
    }

    // ---------- share sheet ----------

    private func presentShare(items: [Any]) {
        guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let root = scene.windows.first(where: { $0.isKeyWindow })?.rootViewController else { return }
        var top = root
        while let presented = top.presentedViewController { top = presented }
        let sheet = UIActivityViewController(activityItems: items, applicationActivities: nil)
        sheet.popoverPresentationController?.sourceView = top.view
        sheet.popoverPresentationController?.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.midY, width: 0, height: 0)
        top.present(sheet, animated: true)
    }
}

/// Posted (from any thread) when a TUS callback persists new upload
/// progress; the store observes it on the main queue and refreshes rows.
extension Notification.Name {
    static let uwCloudProgress = Notification.Name("org.tinio.unwritten.cloudProgress")
}

/// Carries an AVAssetExportSession across to its @Sendable completion
/// handler. Only status/error are read there, after completion — the
/// API's own contract — so the unchecked crossing is sound.
final class ExportBox: @unchecked Sendable {
    let session: AVAssetExportSession

    init(_ session: AVAssetExportSession) {
        self.session = session
    }
}
