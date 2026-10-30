import CryptoKit
import Foundation

/// Optional Cloud upload: presigned TUS (resumable) upload of a
/// finished lesson, then status polling until Cloud finishes encoding.
/// Two credential modes, mirroring the Android and web recorders:
///  - signer mode: POST {title[, videoId]} to the signer URL (see
///    app/cloud-signer) -> {videoId, libraryId, signature, expire};
///    the library API key never lives on this device.
///  - direct mode: the library API key is configured on-device; this
///    type creates the video and signs locally (SHA-256 of
///    libraryId + apiKey + expire + videoId, per the vendor's TUS docs).
/// Framework APIs only, no third-party libraries. All methods are
/// async; callers hop to the main actor for UI updates.
struct CloudUploader {
    private static let TUS_URL = "https://video.bunnycdn.com/tusupload"
    private static let API = "https://video.bunnycdn.com"
    private static let CHUNK = 5 * 1024 * 1024

    let libraryId: String
    let apiKey: String
    let signerUrl: String
    let signerToken: String

    /// Library that credentials() most recently resolved (signer mode
    /// learns it from the signer response). Mirrors Android's
    /// lastLibraryId; the store persists it per lesson once known.
    private(set) var lastLibraryId: String = ""

    init(libraryId: String, apiKey: String, signerUrl: String, signerToken: String) {
        self.libraryId = libraryId.trimmingCharacters(in: .whitespacesAndNewlines)
        self.apiKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        self.signerUrl = signerUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        self.signerToken = signerToken.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func configured() -> Bool {
        if !signerUrl.isEmpty { return true }
        return !libraryId.isEmpty && !apiKey.isEmpty
    }

    func useDirect() -> Bool {
        !libraryId.isEmpty && !apiKey.isEmpty
    }

    func embedUrl(libId: String, videoId: String) -> String {
        "https://player.mediadelivery.net/embed/" + libId + "/" + videoId
    }

    // ---------- credentials ----------

    struct Creds: Sendable {
        var videoId: String
        var signature: String
        var libraryId: String
        var expire: Int64
    }

    mutating func credentials(title: String, reuseVideoId: String?) async throws -> Creds {
        if !useDirect() {
            var payload: [String: String] = ["title": title]
            if let reuseVideoId, !reuseVideoId.isEmpty { payload["videoId"] = reuseVideoId }
            var req = URLRequest(url: URL(string: signerUrl)!)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            if !signerToken.isEmpty { req.setValue(signerToken, forHTTPHeaderField: "X-Signer-Token") }
            req.httpBody = try JSONSerialization.data(withJSONObject: payload)
            let (data, resp) = try await URLSession.shared.data(for: req)
            let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard status >= 200 && status < 300 else {
                throw CloudError.message("signer refused (\(status)): \(String(data: data, encoding: .utf8) ?? "")")
            }
            guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                throw CloudError.message("signer returned invalid JSON")
            }
            let videoId = (obj["videoId"] as? String) ?? ""
            let signature = (obj["signature"] as? String) ?? ""
            let expire = (obj["expire"] as? Int64) ?? Int64((obj["expire"] as? Int) ?? 0)
            let lib = (obj["libraryId"] as? String) ?? libraryId
            guard !videoId.isEmpty, !signature.isEmpty, expire != 0 else {
                throw CloudError.message("signer returned incomplete credentials: \(String(data: data, encoding: .utf8) ?? "")")
            }
            lastLibraryId = lib
            return Creds(videoId: videoId, signature: signature, libraryId: lib, expire: expire)
        }
        var videoId = reuseVideoId ?? ""
        if videoId.isEmpty {
            var req = URLRequest(url: URL(string: Self.API + "/library/" + libraryId + "/videos")!)
            req.httpMethod = "POST"
            req.setValue(apiKey, forHTTPHeaderField: "AccessKey")
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["title": title])
            let (data, resp) = try await URLSession.shared.data(for: req)
            let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard status >= 200 && status < 300 else {
                throw CloudError.message("Cloud create failed (\(status)) — check library ID and API key")
            }
            let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
            videoId = (obj["guid"] as? String) ?? ""
            if videoId.isEmpty { videoId = (obj["videoId"] as? String) ?? "" }
            guard !videoId.isEmpty else {
                throw CloudError.message("Cloud create returned no video id")
            }
        }
        lastLibraryId = libraryId
        let expire = Int64(Date().timeIntervalSince1970) + 86400
        let signature = Self.sha256Hex(libraryId + apiKey + String(expire) + videoId)
        return Creds(videoId: videoId, signature: signature, libraryId: libraryId, expire: expire)
    }

    // ---------- delete + status ----------

    /// Deletes a hub record. 404 counts as gone. Signer only — the
    /// hub lives on the signer, so direct mode has no hub at all.
    func deleteHubRecord(_ videoId: String) async throws {
        guard !useDirect() else { return }
        let encoded = videoId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? videoId
        var req = URLRequest(url: URL(string: signerUrl + "/hub/sessions/" + encoded)!)
        req.httpMethod = "DELETE"
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if !signerToken.isEmpty { req.setValue(signerToken, forHTTPHeaderField: "X-Signer-Token") }
        let (_, resp) = try await URLSession.shared.data(for: req)
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if status != 200 && status != 204 && status != 404 {
            throw CloudError.message("Hub delete failed (\(status))")
        }
    }

    /// Deletes the cloud copy. Throws on failure.
    func deleteVideo(_ videoId: String) async throws {
        let status: Int
        if !useDirect() {
            let sep = signerUrl.contains("?") ? "&" : "?"
            var req = URLRequest(url: URL(string: signerUrl + sep + "videoId=" + videoId)!)
            req.httpMethod = "DELETE"
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            if !signerToken.isEmpty { req.setValue(signerToken, forHTTPHeaderField: "X-Signer-Token") }
            let (_, resp) = try await URLSession.shared.data(for: req)
            status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        } else {
            var req = URLRequest(url: URL(string: Self.API + "/library/" + libraryId + "/videos/" + videoId)!)
            req.httpMethod = "DELETE"
            req.setValue(apiKey, forHTTPHeaderField: "AccessKey")
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            let (_, resp) = try await URLSession.shared.data(for: req)
            status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        }
        if status != 200 && status != 204 && status != 404 {
            throw CloudError.message("Cloud delete failed (\(status))")
        }
    }

    /// Video status: 0 created, 1 uploaded, 2 processing, 3 transcoding,
    /// 4 finished/playable, 5 error, 6 upload failed. -1 on HTTP error.
    func videoStatus(_ videoId: String) async -> Int {
        do {
            let data: Data
            let status: Int
            if !useDirect() {
                let sep = signerUrl.contains("?") ? "&" : "?"
                var req = URLRequest(url: URL(string: signerUrl + sep + "videoId=" + videoId)!)
                req.setValue("application/json", forHTTPHeaderField: "Accept")
                if !signerToken.isEmpty { req.setValue(signerToken, forHTTPHeaderField: "X-Signer-Token") }
                let (d, resp) = try await URLSession.shared.data(for: req)
                data = d
                status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            } else {
                var req = URLRequest(url: URL(string: Self.API + "/library/" + libraryId + "/videos/" + videoId)!)
                req.setValue(apiKey, forHTTPHeaderField: "AccessKey")
                req.setValue("application/json", forHTTPHeaderField: "Accept")
                let (d, resp) = try await URLSession.shared.data(for: req)
                data = d
                status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            }
            guard status >= 200 && status < 300 else { return -1 }
            let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
            if let i = obj["status"] as? Int { return i }
            return -1
        } catch {
            return -1
        }
    }

    // ---------- full flow ----------

    /// Full flow for one file: (resume or create) TUS upload, then poll
    /// encoding. savedUploadUrl/savedVideoId come from a previous attempt
    /// (pass nils for a fresh upload). Returns the videoId once Cloud
    /// reports status 4 (playable). onSession fires as soon as the TUS
    /// resource is known (persist it for resume); onProgress reports
    /// sent/total bytes. Mirrors Android's Listener callbacks.
    mutating func upload(fileURL: URL, savedUploadUrl: String?, savedVideoId: String?,
                         onSession: @escaping @Sendable (Creds, String) -> Void,
                         onProgress: @escaping @Sendable (Int64, Int64) -> Void) async throws -> String {
        let creds = try await credentials(title: fileURL.lastPathComponent, reuseVideoId: savedVideoId)
        var uploadUrl = savedUploadUrl
        var offset: Int64 = -1
        if let u = uploadUrl, !u.isEmpty {
            offset = (try? await tusHead(uploadUrl: u, creds: creds)) ?? -1
            let total = Self.fileSize(fileURL)
            if offset < 0 || offset > total { uploadUrl = nil; offset = -1 }
        }
        if uploadUrl == nil {
            uploadUrl = try await tusCreate(creds: creds, fileURL: fileURL)
            offset = 0
        }
        // Persist the session for resume before the first byte moves.
        onSession(creds, uploadUrl!)
        onProgress(offset, Self.fileSize(fileURL))
        try await tusSend(fileURL: fileURL, uploadUrl: uploadUrl!, creds: creds,
                          offset: offset, onProgress: onProgress)
        for _ in 0 ..< 120 {
            try await Task.sleep(nanoseconds: 5_000_000_000)
            let st = await videoStatus(creds.videoId)
            if st == 4 { return creds.videoId }
            if st == 5 || st == 6 {
                throw CloudError.message("Cloud encoding failed (status \(st))")
            }
        }
        throw CloudError.message("Still processing on Cloud — check the dashboard; the upload itself finished.")
    }

    // ---------- TUS ----------

    private func authHeaders(_ c: Creds) -> [String: String] {
        [
            "AuthorizationSignature": c.signature,
            "AuthorizationExpire": String(c.expire),
            "LibraryId": c.libraryId,
            "VideoId": c.videoId,
            "Tus-Resumable": "1.0.0",
        ]
    }

    private func tusCreate(creds: Creds, fileURL: URL) async throws -> String {
        let total = Self.fileSize(fileURL)
        var req = URLRequest(url: URL(string: Self.TUS_URL)!)
        req.httpMethod = "POST"
        for (k, v) in authHeaders(creds) { req.setValue(v, forHTTPHeaderField: k) }
        req.setValue(String(total), forHTTPHeaderField: "Upload-Length")
        let meta = "filetype " + Self.b64("video/mp4") + ",title " + Self.b64(fileURL.lastPathComponent)
        req.setValue(meta, forHTTPHeaderField: "Upload-Metadata")
        let (data, resp) = try await URLSession.shared.data(for: req)
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 201 else {
            throw CloudError.message("Cloud upload start failed (\(status)): \(String(data: data, encoding: .utf8) ?? "")")
        }
        guard let headers = (resp as? HTTPURLResponse)?.allHeaderFields as? [String: Any] else {
            throw CloudError.message("Cloud upload start returned no headers")
        }
        var loc: String?
        for (k, v) in headers where (k as String).lowercased() == "location" {
            loc = v as? String
            break
        }
        guard let loc, !loc.isEmpty else {
            throw CloudError.message("Cloud upload start returned no URL")
        }
        return loc.hasPrefix("/") ? Self.API + loc : loc
    }

    private func tusHead(uploadUrl: String, creds: Creds) async throws -> Int64 {
        var req = URLRequest(url: URL(string: uploadUrl)!)
        req.httpMethod = "HEAD"
        for (k, v) in authHeaders(creds) { req.setValue(v, forHTTPHeaderField: k) }
        let (_, resp) = try await URLSession.shared.data(for: req)
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if status == 404 || status == 410 { return -1 }
        guard status >= 200 && status < 300 else {
            throw CloudError.message("resume check \(status)")
        }
        return Self.headerInt(resp, name: "Upload-Offset") ?? -1
    }

    private func tusSend(fileURL: URL, uploadUrl: String, creds: Creds, offset startOffset: Int64,
                         onProgress: @escaping @Sendable (Int64, Int64) -> Void) async throws {
        let total = Self.fileSize(fileURL)
        guard total > 0 else { throw CloudError.message("lesson file is empty") }
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }
        var offset = startOffset
        var attempt = 0
        while offset < total {
            try Task.checkCancellation()
            let want = Int(min(Int64(Self.CHUNK), total - offset))
            try handle.seek(toOffset: UInt64(offset))
            guard let chunk = try handle.read(upToCount: want), !chunk.isEmpty else {
                throw CloudError.message("could not read lesson file at offset \(offset)")
            }
            var req = URLRequest(url: URL(string: uploadUrl)!)
            req.httpMethod = "PATCH"
            for (k, v) in authHeaders(creds) { req.setValue(v, forHTTPHeaderField: k) }
            req.setValue(String(offset), forHTTPHeaderField: "Upload-Offset")
            req.setValue("application/offset+octet-stream", forHTTPHeaderField: "Content-Type")
            req.httpBody = chunk
            req.timeoutInterval = 120
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
                if status >= 400 && status < 500 && status != 409 && status != 423 {
                    throw CloudError.message("Cloud refused the upload (\(status)): \(String(data: data, encoding: .utf8) ?? "")")
                }
                guard status >= 200 && status < 300 else {
                    throw CloudError.retryable("Cloud upload failed (\(status))")
                }
                attempt = 0
                if let server = Self.headerInt(resp, name: "Upload-Offset"), server >= 0 {
                    offset = server
                } else {
                    offset += Int64(chunk.count)
                }
                onProgress(offset, total)
            } catch let e as CloudError {
                switch e {
                case .message: throw e
                case .retryable: break // fall through to retry below
                }
                attempt += 1
                if attempt > 8 { throw CloudError.message("Cloud upload kept failing — connection too unstable.") }
                if let so = try? await tusHead(uploadUrl: uploadUrl, creds: creds), so >= 0 { offset = so }
                try await Task.sleep(nanoseconds: UInt64(min(Int64(3 * attempt), 15)) * 1_000_000_000)
            } catch is CancellationError {
                throw CloudError.message("upload cancelled")
            } catch {
                attempt += 1
                if attempt > 8 { throw error }
                if let so = try? await tusHead(uploadUrl: uploadUrl, creds: creds), so >= 0 { offset = so }
                try await Task.sleep(nanoseconds: UInt64(min(Int64(3 * attempt), 15)) * 1_000_000_000)
            }
        }
    }

    // ---------- helpers ----------

    private static func fileSize(_ url: URL) -> Int64 {
        (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int64) ?? 0
    }

    private static func headerInt(_ resp: URLResponse?, name: String) -> Int64? {
        guard let fields = (resp as? HTTPURLResponse)?.allHeaderFields else { return nil }
        for (k, v) in fields where (k as? String)?.lowercased() == name.lowercased() {
            if let s = v as? String { return Int64(s.trimmingCharacters(in: .whitespaces)) }
            if let n = v as? Int { return Int64(n) }
        }
        return nil
    }

    static func sha256Hex(_ text: String) -> String {
        let digest = SHA256.hash(data: Data(text.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private static func b64(_ s: String) -> String {
        Data(s.utf8).base64EncodedString()
    }
}

enum CloudError: Error {
    /// Fatal: report to the user, keep the local lesson.
    case message(String)
    /// Transient HTTP failure: re-check the server offset and retry.
    case retryable(String)
}
