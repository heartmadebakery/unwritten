import AVFoundation
import UIKit

/// One published lesson from the hub store (see pipeline/publish.py
/// and app/cloud-signer). Video bytes stay in Stream; the write-up,
/// corrections, chapters and playback URLs travel here.
struct HubCorrection: Decodable {
    var start: String?
    var quote: String?
    var correcting: String?
    var segment: String?
}

struct HubChapter: Decodable {
    var start: String?
    var label: String?
}

/// One operator set-aside from the hub store: a video the hub never
/// shows. The Record screen badges matching takes instead.
struct IgnoredMark: Decodable {
    var videoId: String
    var title: String?
    var reason: String?
}

struct HubSession: Decodable, Identifiable {
    var videoId: String
    var libraryId: String?
    var title: String?
    var lessonDate: String?
    var durationSeconds: Int?
    var publishedAt: Int64?
    var hlsUrl: String?
    var mp4Url: String?
    var writeupMd: String?
    var corrections: [HubCorrection]?
    var chapters: [HubChapter]?
    var glossary: [String: String]?

    var id: String { videoId }
}

/// One row in the sessions list. Mirrors the Android session rows and
/// the web app's clipHTML: left status icon, middle date + length,
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
    /// Set when the pipeline operator set this take aside: the row
    /// shows an "ignored" badge instead of hub content.
    var ignoredReason: String? = nil

    var id: String { name }
}

/// Lessons on this device + their Cloud copies. Lessons live in the
/// app's clips folder (Documents/clips — visible in the Files app, no
/// permission needed) and export through the share sheet. Cloud is
/// strictly additive: the on-device save always happens first and never
/// depends on the upload. Mirrors MainActivity's clips + Cloud sections
/// and the web app's saveBlob/Cloud flow.
@MainActor
final class SessionStore: ObservableObject {
    @Published var rows: [SessionRow] = []
    @Published var status: String = ""
    @Published var cloudOn: Bool = true

    let clipsDir: URL
    let cloud = CloudStore()
    private var durationCache: [String: String] = [:]
    private var ignoredById: [String: String] = [:]
    private var ignoredByTitle: [String: String] = [:]
    private var inFlight: Set<String> = []
    private var polling: Set<String> = []
    private var uploadTasks: [String: Task<Void, Never>] = [:]
    private var pollTasks: [String: Task<Void, Never>] = [:]
    private var cloudProgressObserver: NSObjectProtocol?

    @MainActor
    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        clipsDir = docs.appendingPathComponent("clips", isDirectory: true)
        try? FileManager.default.createDirectory(at: clipsDir, withIntermediateDirectories: true)
        cloudOn = cloud.cloudEnabledCfg()
        cloudProgressObserver = NotificationCenter.default.addObserver(forName: .uwCloudProgress, object: nil, queue: .main) { [weak self] _ in
            // Delivered on the main queue by construction.
            MainActor.assumeIsolated { self?.refresh() }
        }
        refresh()
    }

    deinit {
        if let observer = cloudProgressObserver {
            NotificationCenter.default.removeObserver(observer)
        }
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

    func hubDurationText(_ sec: Int) -> String {
        let h = sec / 3600, m = (sec / 60) % 60, s = sec % 60
        if h > 0 { return String(format: "%d:%02d:%02d", h, m, s) }
        return String(format: "%d:%02d", m, s)
    }
    func hubSubtitle(for row: HubSession) -> String {
        let dur = row.durationSeconds ?? 0
        let durStr = dur > 0 ? hubDurationText(dur) : ""
        let date = row.lessonDate ?? ""
        if !date.isEmpty && !durStr.isEmpty { return date + " \u2022 " + durStr }
        if !date.isEmpty { return date }
        return durStr
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

    /// The ignore reason for a take, or nil when not ignored.
    /// Match rule, same as Android and the web: the take's
    /// cloud-link videoId, else its filename against the marker
    /// title (upload titles are filenames).
    private func ignoredReason(for name: String) -> String? {
        if let vid = cloud.cloudLink(name)?["videoId"] as? String, !vid.isEmpty,
           let reason = ignoredById[vid] {
            return reason
        }
        return ignoredByTitle[name]
    }

    func refresh() {
        rows = clipFiles().map { file in
            let name = file.lastPathComponent
            let dur = durationCache[name] ?? ""
            let middle = dur.isEmpty ? displayDateFor(name) : displayDateFor(name) + "  •  " + dur
            return SessionRow(name: name, url: file, leftIcon: leftIconFor(name),
                              middleText: middle, rightKind: rightKindFor(name),
                              ignoredReason: ignoredReason(for: name))
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
                // The temp file survives until its case is decided:
                // deleting it up front would lose the lesson on the
                // failure path and register a phantom row.
                switch status {
                case .completed:
                    try? FileManager.default.removeItem(at: tempURL)
                    self.registerLesson(url: mp4URL)
                case .cancelled:
                    try? FileManager.default.removeItem(at: tempURL)
                    self.status = "⚠️ That take was interrupted before it finished. Record the lesson again."
                default:
                    // Passthrough failed (unexpected codec mix) — keep the
                    // .mov rather than lose the lesson; the pipeline takes
                    // the largest media file whatever its extension.
                    try? FileManager.default.removeItem(at: mp4URL)
                    let movURL = self.clipsDir.appendingPathComponent("unwritten_lesson_" + stamp + ".mov")
                    do {
                        try FileManager.default.moveItem(at: tempURL, to: movURL)
                        self.registerLesson(url: movURL)
                        self.status = "⚠️ MP4 remux failed (\(message ?? "unknown")) — kept the original recording."
                    } catch {
                        self.status = "⚠️ MP4 remux failed (\(message ?? "unknown")) — and the original could not be kept: \(error.localizedDescription)"
                    }
                }
            }
        }
    }

    private func keepMovFallback(tempURL: URL, stamp: String) {
        let movURL = clipsDir.appendingPathComponent("unwritten_lesson_" + stamp + ".mov")
        do {
            try FileManager.default.moveItem(at: tempURL, to: movURL)
            registerLesson(url: movURL)
            // After registerLesson: it reports "saved", which would
            // bury the remux warning.
            status = "⚠️ MP4 remux unavailable — kept the original recording."
        } catch {
            status = "⚠️ Could not keep that take: \(error.localizedDescription)"
        }
    }

    private func registerLesson(url: URL) {
        status = "✅ Session saved — on this device. Hand the file to whoever runs the pipeline."
        refresh()
        maybeCloudUpload(url.lastPathComponent)
    }

    /// An upload rides the exact session path of a take: copied into
    /// the clips folder under an upload_ name, then registered (listed
    /// and cloud-uploaded), so the pipeline picks it up the same way a
    /// recording is picked up.
    func registerUpload(sourceURL: URL) {
        let ext = sourceURL.pathExtension.lowercased()
        guard ["mov", "mp4", "m4v"].contains(ext) else {
            status = "That file isn't a video — pick a video file."
            return
        }
        let dest = clipsDir.appendingPathComponent(Names.uploadName(ext))
        do {
            if FileManager.default.fileExists(atPath: dest.path) {
                try FileManager.default.removeItem(at: dest)
            }
            try FileManager.default.copyItem(at: sourceURL, to: dest)
        } catch {
            status = "Upload failed: \(error.localizedDescription)"
            return
        }
        registerLesson(url: dest)
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
        loadHub()
        if cloud.cloudEnabledCfg() {
            status = "☁️ Cloud on. New video sessions will also upload for streamed playback; the ↗ action on each session offers its link when ready."
            sweepBacklog()
        } else {
            status = "☁️ Cloud off. Sessions stay on this device only. Export sessions below to move them."
        }
    }

    /// Sessions recorded while Cloud was off (or failed) still need
    /// their copy when Cloud comes back on — without this sweep they
    /// would stay local-only forever, silently.
    private func sweepBacklog() {
        guard cloud.canUpload() else { return }
        for file in clipFiles() {
            maybeCloudUpload(file.lastPathComponent)
        }
    }

    func paintCloudToggle() {
        cloudOn = cloud.cloudEnabledCfg()
    }

    func cloudWatchUrl(_ name: String) -> String? {
        if let direct = cloud.watchUrl(for: name) { return direct }
        // Same lesson only: a stale lastLink from another lesson must
        // never be shared under this lesson's name.
        if cloud.lastName == name, !cloud.lastLink.isEmpty { return cloud.lastLink }
        return nil
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
        guard cloud.canUpload() else {
            cloudFailed(name, videoId: nil,
                        message: "Cloud credentials missing — add the signer token in Cloud settings.")
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
        guard url(for: name) != nil else { return }  // deleted mid-flight: no zombie row
        var lib = (cloud.cloudLink(name)?["libraryId"] as? String) ?? ""
        if lib.isEmpty { lib = cloud.libraryId }
        cloud.setCloudLink(name, state: "ready", videoId: videoId,
                           libraryId: lib, uploadUrl: nil, progress: 100)
        // A link is only published when the library id is known — an
        // embed//videoId URL helps nobody and poisons the fallback.
        if !lib.isEmpty {
            let url = "https://player.mediadelivery.net/embed/" + lib + "/" + videoId
            cloud.lastLink = url
            cloud.lastName = name
            UIPasteboard.general.string = url
        }
        status = "☁️ Uploaded. Cloud is preparing the streaming version — the ↗ share action on the session offers its link when ready."
        refresh()
    }

    private func cloudFailed(_ name: String, videoId: String?, message: String) {
        guard url(for: name) != nil else { return }  // deleted mid-flight: no zombie row
        cloud.setCloudLink(name, state: "failed", videoId: videoId,
                           libraryId: nil, uploadUrl: nil, progress: -1)
        if message.contains("(401)") || message.contains("(403)")
            || message.contains("credentials missing") {
            status = "☁️ Signer refused the upload — check the token in Cloud settings. The session is safe on this device; tap ! on the session to retry."
        } else {
            status = "☁️ Cloud upload didn't finish (\(message)) The session is safe on this device — tap ! on the session when the connection is better."
        }
        refresh()
    }

    private func pollCloud(_ name: String, videoId: String) {
        if videoId.isEmpty || polling.contains(name) { return }
        polling.insert(name)
        pollTasks[name]?.cancel()
        pollTasks[name] = Task { [weak self] in
            guard let self else { return }
            defer {
                self.polling.remove(name)
                self.pollTasks.removeValue(forKey: name)
            }
            guard let uploader = self.cloud.uploader() else { return }
            var errors = 0
            for _ in 0 ..< 120 {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if Task.isCancelled { return }
                let st = await uploader.videoStatus(videoId)
                if st < 0 {
                    errors += 1
                    if errors > 6 {
                        self.cloudFailed(name, videoId: videoId, message: "Cloud status checks kept failing — tap ! on the session to try again.")
                        return
                    }
                    continue
                }
                errors = 0
                if st == 4 {
                    self.cloudFinished(name, videoId: videoId)
                    return
                }
                if st == 5 || st == 6 {
                    self.cloudFailed(name, videoId: videoId, message: "Cloud encoding failed.")
                    return
                }
            }
            // Ten minutes with no finished stream: offer a retry
            // instead of leaving the session on "…" forever.
            self.cloudFailed(name, videoId: videoId, message: "Cloud is taking too long to prepare the stream — tap ! on the session to try again.")
        }
    }

    /// Resume interrupted uploads after the app restarts, like Android's
    /// cloudResumePending and the web app's cloudResumePending.
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

    /// Set when a cloud delete fails: the view offers deleting this
    /// phone's copy anyway (the cloud copy stays where it is) instead
    /// of trapping local storage behind a dead delete.
    @Published var pendingForceDelete: String?

    /// Long-press a session to delete it, like Android and the web —
    /// cloud copy first, and the local session is kept if that fails
    /// (with a second confirm to delete the device copy anyway).
    func deleteLesson(_ name: String) {
        uploadTasks[name]?.cancel()
        pollTasks[name]?.cancel()
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
                    self.pendingForceDelete = name
                    return
                }
            }
            self.removeLocalSession(name)
            self.status = "🗑 Session deleted from this device" + (videoId.isEmpty ? "." : " and the cloud.")
        }
    }

    /// Deletes this phone's copy after the user confirms past a dead
    /// cloud delete. The cloud copy stays where it is.
    func forceDeleteLocal(_ name: String) {
        pendingForceDelete = nil
        removeLocalSession(name)
        status = "🗑 Session deleted from this phone. The cloud copy stays where it is."
    }

    private func removeLocalSession(_ name: String) {
        try? FileManager.default.removeItem(at: clipsDir.appendingPathComponent(name))
        cloud.delCloudLink(name)
        inFlight.remove(name)
        polling.remove(name)
        durationCache.removeValue(forKey: name)
        if name == cloud.lastName { cloud.clearLastLink() }
        refresh()
    }

    func retryCloud(_ name: String) {
        guard url(for: name) != nil else {
            status = "☁️ That session is no longer stored on this device, so it can't be re-uploaded from here."
            return
        }
        startCloudUpload(name)
    }

    // ---------- hub ----------

    @Published var hubRows: [HubSession] = []
    @Published var hubDetail: HubSession?
    @Published var hubNotice: String = ""
    @Published var hubLoading: Bool = false

    /// The hub lives on the signer, so it needs a signer URL and token.
    /// Direct (library-key) mode has no hub at all.
    func hubAvailable() -> Bool {
        !cloud.effSignerUrl().trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !cloud.effSignerToken().isEmpty
    }

    private func hubRequest(_ path: String) -> URLRequest? {
        guard hubAvailable() else { return nil }
        guard let url = URL(string: cloud.effSignerUrl() + path) else { return nil }
        var req = URLRequest(url: url)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(cloud.effSignerToken(), forHTTPHeaderField: "X-Signer-Token")
        return req
    }

    /// Always-visible Hub section text: the reason when the hub cannot
    /// show rows, "" when rows are showing. The section header renders
    /// regardless; this keeps a missing token or a dead server visible
    /// instead of looking like a missing feature.
    func hubStatusText() -> String {
        if !cloud.enabled {
            return "Hub lives on the signer — turn Cloud on to see published lessons."
        }
        if !hubAvailable() {
            return "Hub lives on the signer — add the signer URL and token in Cloud settings."
        }
        if hubLoading {
            return "Loading hub sessions…"
        }
        return hubNotice.isEmpty
            ? "No published sessions yet — run the pipeline's publish step."
            : hubNotice
    }

    /// Operator set-asides, newest first: videos the hub never
    /// shows. Matching takes get an "ignored" badge in the Record
    /// list instead. A failed fetch just leaves badges off.
    func loadIgnored() {
        guard hubAvailable(), let req = hubRequest("/hub/ignored") else {
            ignoredById = [:]
            ignoredByTitle = [:]
            refresh()
            return
        }
        Task { [weak self] in
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                guard (resp as? HTTPURLResponse)?.statusCode == 200 else { return }
                let marks = try JSONDecoder().decode([IgnoredMark].self, from: data)
                var byId: [String: String] = [:]
                var byTitle: [String: String] = [:]
                for mark in marks {
                    if !mark.videoId.isEmpty { byId[mark.videoId] = mark.reason ?? "" }
                    if let title = mark.title, !title.isEmpty { byTitle[title] = mark.reason ?? "" }
                }
                self?.ignoredById = byId
                self?.ignoredByTitle = byTitle
                self?.refresh()
            } catch {
                return
            }
        }
    }

    /// Published lessons, newest first. Unconfigured hubs clear the
    /// rows while the status text explains why nothing new loads.
    func loadHub() {
        guard hubAvailable(), let req = hubRequest("/hub/sessions") else {
            hubRows = []
            hubDetail = nil
            hubNotice = ""
            hubLoading = false
            loadIgnored()
            return
        }
        loadIgnored()
        hubLoading = true
        Task { [weak self] in
            defer { self?.hubLoading = false }
            var failedStatus = 0
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                failedStatus = (resp as? HTTPURLResponse)?.statusCode ?? 0
                guard failedStatus == 200 else {
                    throw CloudError.message("hub unavailable")
                }
                let rows = try JSONDecoder().decode([HubSession].self, from: data)
                self?.hubRows = rows
                self?.hubNotice = ""
                if let detail = self?.hubDetail,
                   !rows.contains(where: { $0.videoId == detail.videoId }) {
                    self?.hubDetail = nil
                }
            } catch {
                if failedStatus == 401 || failedStatus == 403 {
                    self?.hubNotice = "Signer refused the token — check it in Cloud settings."
                } else if failedStatus == 503 {
                    self?.hubNotice = "Hub isn't switched on at the server yet."
                } else {
                    // Surface cause for debugging — keep generic prefix.
                    let cause = String(error.localizedDescription.prefix(180))
                    self?.hubNotice = "Hub couldn't load — check the connection and Cloud settings. (\(cause))"
                }
            }
        }
    }

    /// Queues a video URL for the pipeline fetcher (YouTube/watch
    /// links the app cannot download itself).
    func queueFetchUrl(_ url: String) {
        let trimmed = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { status = "Paste a link first."; return }
        guard hubAvailable(), let endpoint = URL(string: cloud.effSignerUrl() + "/fetch/jobs"),
              endpoint.scheme != nil, endpoint.host != nil else {
            status = "Queuing needs the signer token — add it in Cloud settings."
            return
        }
        var req = URLRequest(url: endpoint)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(cloud.effSignerToken(), forHTTPHeaderField: "X-Signer-Token")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["url": trimmed])
        status = "⬇ Queuing…"
        Task { [weak self] in
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                if code == 401 {
                    self?.status = "Signer refused the token — check it in Cloud settings."
                    return
                }
                guard code >= 200 && code < 300 else {
                    throw CloudError.message("queue refused (\(code)): \(String(data: data, encoding: .utf8) ?? "")")
                }
                self?.status = "✅ Queued — the pipeline will fetch the video."
            } catch {
                let cause = String(error.localizedDescription.prefix(180))
                self?.status = "Couldn't queue that link (\(cause)) — check the connection and Cloud settings."
            }
        }
    }

    func openHubSession(_ row: HubSession) {
        let encoded = row.videoId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? row.videoId
        guard let req = hubRequest("/hub/sessions/" + encoded) else { return }
        Task { [weak self] in
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                    throw CloudError.message("hub unavailable")
                }
                self?.hubDetail = try JSONDecoder().decode(HubSession.self, from: data)
            } catch {
                self?.status = "Couldn't open that hub session — check the connection."
            }
        }
    }

    func closeHubSession() {
        hubDetail = nil
    }

    func hubEmbedUrl(_ session: HubSession) -> String? {
        var lib = session.libraryId ?? ""
        if lib.isEmpty { lib = cloud.libraryId }
        if lib.isEmpty || session.videoId.isEmpty { return nil }
        return "https://player.mediadelivery.net/embed/" + lib + "/" + session.videoId
    }

    /// Per-session hub share: the link is copied, then offered through
    /// the share sheet — same as device sessions.
    func shareHubSession(_ session: HubSession) {
        guard let url = hubEmbedUrl(session) else {
            status = "No Cloud link yet for this session."
            return
        }
        UIPasteboard.general.string = url
        presentShare(items: [url])
    }

    /// Hub delete removes the hub record first, then the Stream copy:
    /// a failure between the two leaves the bytes orphaned in Stream
    /// (still playable, still re-publishable) instead of a hub row
    /// pointing at a dead video. The partial outcome is reported as
    /// partial, never as "nothing was lost".
    func deleteHubSession(_ session: HubSession) {
        let videoId = session.videoId
        guard !videoId.isEmpty else { return }
        Task { [weak self] in
            guard let self else { return }
            do {
                guard let uploader = self.cloud.uploader() else {
                    throw CloudError.message("Cloud settings incomplete.")
                }
                try await uploader.deleteHubRecord(videoId)
                do {
                    try await uploader.deleteVideo(videoId)
                } catch {
                    let message: String
                    if case let CloudError.message(m) = error { message = m } else {
                        message = error.localizedDescription
                    }
                    if self.hubDetail?.videoId == videoId { self.hubDetail = nil }
                    self.loadHub()
                    self.status = "☁️ Hub entry removed, but the cloud copy remains (\(message)) Delete it from the Stream dashboard."
                    return
                }
            } catch {
                let message: String
                if case let CloudError.message(m) = error { message = m } else {
                    message = error.localizedDescription
                }
                self.status = "☁️ Couldn't delete the hub entry (\(message)) Keeping everything so nothing is lost."
                return
            }
            if self.hubDetail?.videoId == videoId { self.hubDetail = nil }
            self.loadHub()
            self.status = "🗑 Session deleted from the hub and the cloud."
        }
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
