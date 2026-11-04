import Foundation

/// Cloud settings + per-lesson link state, backed by UserDefaults.
/// Mirrors Android's "unwritten_cloud" prefs and the web app's
/// localStorage keys: lessons are always saved on-device first, and a
/// copy uploads only when Cloud is on. Link states: uploading
/// (progress/videoId/uploadUrl), processing, ready (videoId +
/// libraryId), failed. Connection values load fresh from the stamped
/// build on every launch — nothing persists them — while the Cloud
/// switch and per-lesson link rows persist below.
///
/// Sendable by hand: every accessor only touches UserDefaults, which is
/// thread-safe, so the TUS progress callbacks can persist link state
/// from any thread.
final class CloudStore: @unchecked Sendable {
    static let CLOUD_SIGNER_DEFAULT = "https://unwritten-cloud-signer.heartmade.workers.dev"

    private let defaults: UserDefaults
    // Serializes the links blob's read-modify-write: TUS progress
    // callbacks persist from background executors while the main
    // thread writes too, and a late progress write must never clobber
    // a finished state back to uploading.
    private let linksLock = NSLock()
    private static let kEnabled = "uw_cloud_enabled"
    private static let kLinks = "uw_cloud_links"
    private static let kLastLink = "uw_cloud_lastLink"
    private static let kLastName = "uw_cloud_lastName"
    private static let kFetchAttempts = "uw_cloud_fetchAttempts"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        migrateLegacyPrefs()
    }

    private func str(_ key: String) -> String {
        defaults.string(forKey: key) ?? ""
    }

    // ---------- settings ----------

    var enabled: Bool {
        get {
            if defaults.object(forKey: Self.kEnabled) == nil { return true }
            return defaults.bool(forKey: Self.kEnabled)
        }
        set { defaults.set(newValue, forKey: Self.kEnabled) }
    }

    /// Build values, fresh on every launch: nothing persists or
    /// overrides them, so a stale saved URL can never break uploads.
    func effSignerUrl() -> String {
        Self.CLOUD_SIGNER_DEFAULT
    }

    func effSignerToken() -> String {
        CloudConfig.CLOUD_SIGNER_TOKEN_DEFAULT
    }

    /// True when an upload could possibly succeed: the build carries
    /// a stamped signer token. Without this, token-less builds fire
    /// doomed uploads that can only 401.
    /// Uses the effective token so build-stamped tokens count, exactly
    /// like hubAvailable.
    func canUpload() -> Bool {
        !effSignerToken().isEmpty
    }

    func uploader() -> CloudUploader? {
        let up = CloudUploader(signerUrl: effSignerUrl(), signerToken: effSignerToken())
        return up.configured() ? up : nil
    }

    /// Cloud saves a copy only when toggled on and credentials exist.
    /// With Cloud off the app makes no network calls at all.
    func cloudEnabledCfg() -> Bool {
        enabled && uploader() != nil
    }

    // ---------- per-lesson links ----------

    func links() -> [String: [String: Any]] {
        guard let raw = defaults.string(forKey: Self.kLinks),
              let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data),
              let dict = obj as? [String: [String: Any]] else { return [:] }
        return dict
    }

    private func saveLinks(_ links: [String: [String: Any]]) {
        if let data = try? JSONSerialization.data(withJSONObject: links),
           let raw = String(data: data, encoding: .utf8) {
            defaults.set(raw, forKey: Self.kLinks)
        }
    }

    func cloudLink(_ name: String) -> [String: Any]? {
        links()[name]
    }

    /// Patch (never replace) one lesson's link record. Mirrors
    /// Android's setCloudLink: nil arguments leave the field untouched;
    /// progress < 0 leaves the progress untouched.
    func setCloudLink(_ name: String, state: String?, videoId: String?,
                      libraryId: String?, uploadUrl: String?, progress: Int) {
        linksLock.lock()
        defer { linksLock.unlock() }
        var all = links()
        var cur = all[name] ?? [:]
        if let state { cur["state"] = state }
        if let videoId { cur["videoId"] = videoId }
        if let libraryId { cur["libraryId"] = libraryId }
        if let uploadUrl { cur["uploadUrl"] = uploadUrl }
        if progress >= 0 { cur["progress"] = progress }
        all[name] = cur
        saveLinks(all)
    }

    /// Patch arbitrary fields of one lesson's link record (session
    /// parts: joinTo, joinTitle, joined) — never replaces the record.
    func setLinkFields(_ name: String, _ fields: [String: Any]) {
        linksLock.lock()
        defer { linksLock.unlock() }
        var all = links()
        var cur = all[name] ?? [:]
        for (k, v) in fields { cur[k] = v }
        all[name] = cur
        saveLinks(all)
    }

    func delCloudLink(_ name: String) {
        linksLock.lock()
        defer { linksLock.unlock() }
        var all = links()
        if all.removeValue(forKey: name) != nil { saveLinks(all) }
    }

    var lastLink: String {
        get { str(Self.kLastLink) }
        set { defaults.set(newValue, forKey: Self.kLastLink) }
    }

    var lastName: String {
        get { str(Self.kLastName) }
        set { defaults.set(newValue, forKey: Self.kLastName) }
    }

    func clearLastLink() {
        defaults.removeObject(forKey: Self.kLastLink)
        defaults.removeObject(forKey: Self.kLastName)
    }

    /// Fetch attempts: links queued to the pipeline for fetching,
    /// logged locally (newest first, capped) so the upload screen can
    /// list them afterwards — the pipeline's outcome shows up in
    /// the hub.
    struct FetchAttempt: Codable {
        var url: String
        var date: Date
        var ok: Bool
    }

    func fetchAttempts() -> [FetchAttempt] {
        guard let raw = defaults.string(forKey: Self.kFetchAttempts),
              let data = raw.data(using: .utf8),
              let list = try? JSONDecoder().decode([FetchAttempt].self, from: data) else { return [] }
        return list
    }

    func logFetchAttempt(url: String, ok: Bool) {
        var list = [FetchAttempt(url: url, date: Date(), ok: ok)] + fetchAttempts()
        list = Array(list.prefix(20))
        if let data = try? JSONEncoder().encode(list),
           let raw = String(data: data, encoding: .utf8) {
            defaults.set(raw, forKey: Self.kFetchAttempts)
        }
    }

    func watchUrl(for name: String) -> String? {
        guard let link = cloudLink(name),
              let videoId = link["videoId"] as? String, !videoId.isEmpty else { return nil }
        let lib = (link["libraryId"] as? String) ?? ""
        if lib.isEmpty { return nil }
        return "https://player.mediadelivery.net/embed/" + lib + "/" + videoId
    }

    // ---------- legacy migration ----------

    private func migrateLegacyPrefs() {
        // One-time move from the pre-rename store: only the Cloud
        // switch and per-lesson link rows are adopted (connection
        // values load fresh from the stamped build — user-ordered
        // Nov 4). Then the legacy store is cleared. Mirrors Android's
        // migrateCloudPrefs and the web app's uw_bunny_* legacy fallback.
        guard let legacy = defaults.dictionary(forKey: "unwritten_bunny"),
              !legacy.isEmpty else { return }
        for (key, value) in legacy {
            switch key {
            case "enabled":
                if let b = value as? Bool { defaults.set(b, forKey: Self.kEnabled) }
            case "links": defaults.set("\(value)", forKey: Self.kLinks)
            case "lastLink": defaults.set("\(value)", forKey: Self.kLastLink)
            case "lastName": defaults.set("\(value)", forKey: Self.kLastName)
            default: break
            }
        }
        defaults.removeObject(forKey: "unwritten_bunny") // legacy key dropped
    }
}
