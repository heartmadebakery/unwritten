import Foundation

/// Cloud settings + per-lesson link state, backed by UserDefaults.
/// Mirrors Android's "unwritten_cloud" prefs and the web app's
/// localStorage keys: lessons are always saved on-device first, and a
/// copy uploads only when Cloud is on. Link states: uploading
/// (progress/videoId/uploadUrl), processing, ready (videoId +
/// libraryId), failed.
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
    private static let kSignerUrl = "uw_cloud_signerUrl"
    private static let kSignerToken = "uw_cloud_signerToken"
    private static let kLibraryId = "uw_cloud_libraryId"
    private static let kApiKey = "uw_cloud_apiKey"
    private static let kLinks = "uw_cloud_links"
    private static let kLastLink = "uw_cloud_lastLink"
    private static let kLastName = "uw_cloud_lastName"

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

    var signerUrl: String {
        get { str(Self.kSignerUrl) }
        set { defaults.set(newValue, forKey: Self.kSignerUrl) }
    }

    var signerToken: String {
        get { str(Self.kSignerToken) }
        set { defaults.set(newValue, forKey: Self.kSignerToken) }
    }

    var libraryId: String {
        get { str(Self.kLibraryId) }
        set { defaults.set(newValue, forKey: Self.kLibraryId) }
    }

    var apiKey: String {
        get { str(Self.kApiKey) }
        set { defaults.set(newValue, forKey: Self.kApiKey) }
    }

    func effSignerUrl() -> String {
        let s = signerUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.isEmpty ? Self.CLOUD_SIGNER_DEFAULT : s
    }

    func effSignerToken() -> String {
        let t = signerToken.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? CloudConfig.CLOUD_SIGNER_TOKEN_DEFAULT : t
    }

    /// True when an upload could possibly succeed. Signer mode needs
    /// its token — the URL always has a compiled default, so URL-alone
    /// must not count — and direct mode needs library ID + API key.
    /// Without this, fresh installs (Cloud on by default, no
    /// credentials yet) fire doomed uploads that can only 401.
    /// Uses the effective token so build-stamped tokens count, exactly
    /// like hubAvailable.
    func canUpload() -> Bool {
        !effSignerToken().isEmpty
            || (!libraryId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }

    func uploader() -> CloudUploader? {
        let up = CloudUploader(libraryId: libraryId, apiKey: apiKey,
                               signerUrl: effSignerUrl(), signerToken: effSignerToken())
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

    func watchUrl(for name: String) -> String? {
        guard let link = cloudLink(name),
              let videoId = link["videoId"] as? String, !videoId.isEmpty else { return nil }
        var lib = (link["libraryId"] as? String) ?? ""
        if lib.isEmpty { lib = libraryId }
        if lib.isEmpty { return nil }
        return "https://player.mediadelivery.net/embed/" + lib + "/" + videoId
    }

    // ---------- legacy migration ----------

    private func migrateLegacyPrefs() {
        // One-time move from the pre-rename store: the legacy keys are
        // adopted, then the legacy store is cleared. Mirrors Android's
        // migrateCloudPrefs and the web app's uw_bunny_* legacy fallback.
        guard let legacy = defaults.dictionary(forKey: "unwritten_bunny"),
              !legacy.isEmpty else { return }
        for (key, value) in legacy {
            switch key {
            case "enabled":
                if let b = value as? Bool { defaults.set(b, forKey: Self.kEnabled) }
            case "signerUrl": defaults.set("\(value)", forKey: Self.kSignerUrl)
            case "signerToken": defaults.set("\(value)", forKey: Self.kSignerToken)
            case "libraryId": defaults.set("\(value)", forKey: Self.kLibraryId)
            case "apiKey": defaults.set("\(value)", forKey: Self.kApiKey)
            case "links": defaults.set("\(value)", forKey: Self.kLinks)
            case "lastLink": defaults.set("\(value)", forKey: Self.kLastLink)
            case "lastName": defaults.set("\(value)", forKey: Self.kLastName)
            default: break
            }
        }
        defaults.removeObject(forKey: "unwritten_bunny") // legacy key dropped
    }
}
