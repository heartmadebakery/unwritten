import AVFoundation
import SwiftUI
import UniformTypeIdentifiers

extension Color {
    init(hex: String) {
        let v = UInt32(hex, radix: 16) ?? 0
        self.init(red: Double((v >> 16) & 0xFF) / 255.0,
                  green: Double((v >> 8) & 0xFF) / 255.0,
                  blue: Double(v & 0xFF) / 255.0)
    }
}

// Same dark palette as the Android recorder and the web recorder.
private let BG = Color(hex: "17130E")
private let PANEL = Color(hex: "241C12")
private let INK = Color(hex: "F5EAD6")
private let DIM = Color(hex: "B8A888")
private let UWB_RED = Color(hex: "C0392B")
private let BRIGHT = Color(hex: "E74C3C")
private let LINE = Color(hex: "2E2213")

/// Unwritten Craft. Home lands on the hub sessions with Record and
/// Upload above them; recording is one screen of the app, not a
/// separate app. The pipeline (transcribe -> write-up -> corrections)
/// works afterwards on each session — a take or an upload alike.
struct ContentView: View {
    @StateObject private var engine = CameraEngine()
    @StateObject private var store = SessionStore()
    @Environment(\.scenePhase) private var scenePhase

    @State private var recordStart = Date()
    @State private var elapsedText = "0:00"
    @State private var timer: Timer?

    @State private var player: AVPlayer?
    @State private var playingName: String?
    @State private var endObserver: NSObjectProtocol?

    @State private var showCloudPanel = false
    @State private var pendingDelete: String?
    @State private var pendingHubDelete: HubSession?
    @State private var playingHubId: String?
    @State private var zoomProgress: Double = 0

    @State private var signerUrl = ""
    @State private var signerToken = ""
    @State private var libraryId = ""
    @State private var apiKey = ""

    @State private var screen = "home"
    @State private var cameraConfigured = false
    @State private var showUploadPicker = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("Unwritten Craft")
                    .font(.system(size: 24))
                    .foregroundColor(INK)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 2)
                Text("Record, upload, and revisit craft lessons.")
                    .font(.system(size: 16))
                    .foregroundColor(DIM)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.bottom, 10)
                if screen == "home" {
                    homeView
                } else {
                    recordView
                }
            }
            .padding(14)
        }
        .background(BG)
        .scrollContentBackground(.hidden)
        .onAppear {
            let engine = self.engine
            let store = self.store
            engine.statusHandler = { store.status = $0 }
            engine.recordingFinishedHandler = { store.finishRecording(tempURL: $0) }
            store.cloudResumePending()
            store.loadHub()
        }
        .onChange(of: showCloudPanel) { _, shown in
            if !shown { store.loadHub() }
        }
        .onChange(of: engine.isRecording) { _, recording in
            if recording {
                recordStart = Date()
                elapsedText = "0:00"
                timer?.invalidate()
                timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in
                    elapsedText = ContentView.fmt(Int(Date().timeIntervalSince(recordStart)))
                }
            } else {
                timer?.invalidate()
                timer = nil
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                // Leaving mid-recording stops and keeps the take;
                // the session itself pauses so the camera never runs
                // behind the app's back.
                if engine.isRecording { engine.stopVideo() }
                engine.pauseSession()
            } else {
                // A grant in Settings takes effect without a relaunch.
                // The record screen owns the camera: returning to home
                // must not restart it behind the hub.
                engine.refreshPermissions()
                if screen == "record" { engine.resumeSession() }
            }
        }
        .sheet(isPresented: $showUploadPicker) {
            UploadPicker(onPick: { url in
                showUploadPicker = false
                store.registerUpload(sourceURL: url)
            }, onCancel: { showUploadPicker = false })
        }
        .alert("Delete session?", isPresented: Binding(
            get: { pendingDelete != nil },
            set: { if !$0 { pendingDelete = nil } }
        )) {
            Button("Delete", role: .destructive) {
                if let name = pendingDelete {
                    if playingName == name { stopLocalPlayback() }
                    store.deleteLesson(name)
                }
                pendingDelete = nil
            }
            Button("Keep", role: .cancel) { pendingDelete = nil }
        } message: {
            Text("Delete '\(pendingDelete ?? "")' from this phone and the cloud?")
        }
        .alert("Cloud copy couldn't be deleted", isPresented: Binding(
            get: { store.pendingForceDelete != nil },
            set: { if !$0 { store.pendingForceDelete = nil } }
        )) {
            Button("Delete from this phone", role: .destructive) {
                if let name = store.pendingForceDelete {
                    if playingName == name { stopLocalPlayback() }
                    store.forceDeleteLocal(name)
                }
            }
            Button("Keep", role: .cancel) { store.pendingForceDelete = nil }
        } message: {
            Text("Delete '\(store.pendingForceDelete ?? "")' from this phone anyway? The cloud copy stays where it is.")
        }
        .alert("Delete hub session?", isPresented: Binding(
            get: { pendingHubDelete != nil },
            set: { if !$0 { pendingHubDelete = nil } }
        )) {
            Button("Delete", role: .destructive) {
                if let session = pendingHubDelete {
                    if playingHubId == session.videoId { stopLocalPlayback() }
                    store.deleteHubSession(session)
                }
                pendingHubDelete = nil
            }
            Button("Keep", role: .cancel) { pendingHubDelete = nil }
        } message: {
            Text("Delete '\(pendingHubDelete?.title ?? "")' from the cloud and the hub?")
        }
    }

    // One app, two screens. Home (record/upload actions over the hub,
    // then cloud and device sessions) is the landing; record owns the
    // viewfinder and the camera behind it.
    private var homeView: some View {
        VStack(alignment: .leading, spacing: 0) {
            bigButton("● Record") {
                showScreen("record")
            }
            bigButton("⬆ Upload video") {
                showUploadPicker = true
            }

            Text(store.status)
                .font(.system(size: 15))
                .foregroundColor(DIM)
                .lineSpacing(4)
                .padding(.vertical, 10)

            Text("Hub")
                .font(.system(size: 17))
                .foregroundColor(DIM)
                .padding(.top, 14)
                .padding(.bottom, 4)
            if store.hubRows.isEmpty {
                Text(store.hubStatusText())
                    .font(.system(size: 15))
                    .foregroundColor(DIM)
                    .padding(.vertical, 7)
            } else {
                VStack(spacing: 0) {
                    ForEach(store.hubRows) { row in
                        HStack(spacing: 0) {
                            Text("☁")
                                .font(.system(size: 16))
                                .foregroundColor(INK)
                                .frame(minWidth: 32)
                            Text((row.title ?? row.videoId) + (row.lessonDate.map { "  •  " + $0 } ?? ""))
                                .font(.system(size: 15))
                                .foregroundColor(INK)
                                .lineLimit(1)
                                .padding(.horizontal, 8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text("›")
                                .font(.system(size: 20))
                                .foregroundColor(DIM)
                                .frame(width: 40, height: 36)
                        }
                        .padding(.vertical, 8)
                        .padding(.horizontal, 6)
                        .contentShape(Rectangle())
                        .onTapGesture { store.openHubSession(row) }
                        Divider().background(LINE)
                    }
                }
            }
            if let detail = store.hubDetail {
                hubDetailCard(detail)
            }

            // Cloud toggle below the hub.
            bigButton(store.cloudOn ? "☁ Cloud: on" : "☁ Cloud: off") {
                store.toggleCloud()
            }

            // Export is the offline fallback: only with Cloud off.
            if !store.cloudOn {
                bigButton("Export sessions to Downloads") {
                    store.exportSessions()
                }
            }

            smallButton("⚙ Cloud settings") {
                if !showCloudPanel { loadCloudFields() }
                showCloudPanel.toggle()
            }
            .padding(.top, 6)

            if showCloudPanel {
                VStack(alignment: .leading, spacing: 0) {
                    cloudField(label: "Signer URL (prefilled by the build; override only to point elsewhere)",
                               text: $signerUrl, secure: false,
                               prompt: CloudStore.CLOUD_SIGNER_DEFAULT)
                    cloudField(label: "Signer token (prefilled by the build; override only if rotated)",
                               text: $signerToken, secure: true,
                               prompt: "baked into this build")
                    cloudField(label: "— or, without a signer: Stream library ID",
                               text: $libraryId, secure: false)
                    cloudField(label: "Library API key (then lives on this device)",
                               text: $apiKey, secure: true)
                    Text("On by default and purely additive: every session is still saved on this device first, then a copy is uploaded for streamed playback, and the ↗ share action on the session offers its link when ready. As a fallback, a library key pasted above talks to the library directly instead of the signer (it can manage this one library, so keep it on the mentor's device only).")
                        .font(.system(size: 13.5))
                        .foregroundColor(DIM)
                        .lineSpacing(3)
                        .padding(.top, 10)
                }
                .padding(14)
                .background(PANEL)
                .cornerRadius(4)
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(LINE, lineWidth: 1))
                .padding(.top, 10)
                .onChange(of: signerUrl) { _, v in store.cloud.signerUrl = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
                .onChange(of: signerToken) { _, v in store.cloud.signerToken = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
                .onChange(of: libraryId) { _, v in store.cloud.libraryId = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
                .onChange(of: apiKey) { _, v in store.cloud.apiKey = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
            }

            // This device: left icon, middle date + duration, right
            // share/download.
            Text("This device")
                .font(.system(size: 17))
                .foregroundColor(DIM)
                .padding(.top, 14)
                .padding(.bottom, 4)
            if store.rows.isEmpty {
                Text("Nothing yet.")
                    .font(.system(size: 15))
                    .foregroundColor(DIM)
                    .padding(.vertical, 7)
            } else {
                VStack(spacing: 0) {
                    ForEach(store.rows) { row in
                        sessionRow(row)
                        Divider().background(LINE)
                    }
                }
            }

            Text("Every session is saved on this device, and with Cloud on a copy is uploaded for streamed playback. Tap a session to play it; long-press it to delete it from the device and the cloud.")
                .font(.system(size: 14))
                .foregroundColor(DIM)
                .lineSpacing(3)
                .padding(.top, 14)
        }
    }

    private var recordView: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button("‹ Home") {
                showScreen("home")
            }
            .font(.system(size: 16))
            .foregroundColor(DIM)
            .padding(.bottom, 8)

            // Viewfinder with in-player overlay (playback appears
            // inside the viewfinder, like Android).
            ZStack(alignment: .bottom) {
                CameraPreview(engine: engine)
                    .frame(height: 280)
                    .background(Color.black)
                if player != nil, let player {
                    PlayerView(player: player)
                        .frame(height: 280)
                        .background(Color.black)
                }
                if engine.isRecording {
                    HStack {
                        HStack(spacing: 8) {
                            Circle().fill(BRIGHT).frame(width: 12, height: 12)
                            Text("REC\u{00A0}\u{00A0}\(elapsedText)")
                                .font(.system(size: 16))
                                .foregroundColor(.white)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.black.opacity(0.55))
                        .cornerRadius(20)
                        Spacer()
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                if player != nil {
                    HStack(spacing: 8) {
                        playerButton("▶") { player?.play() }
                        playerButton("⏸") { player?.pause() }
                        playerButton("✕") { stopLocalPlayback() }
                    }
                    .padding(8)
                    .background(Color.black.opacity(0.66))
                }
            }

            // A video-only stream must never be silent about being
            // silent: the lesson IS the mentor's words.
            if engine.micWarning {
                Text("🎤 No microphone. The mentor's words won't be recorded — and the mentor's words are the whole point. Check Settings > Privacy > Microphone.")
                    .font(.system(size: 15))
                    .foregroundColor(.white)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(UWB_RED)
            }

            // Quiet-minute check, mirroring the web recorder: a full
            // quiet minute raises this banner; speech clears it.
            if engine.speechWarning {
                Text("🔇 Quiet for a while. No speech in the last minute — and the mentor's words are the whole point. Check the mic is close enough.")
                    .font(.system(size: 15))
                    .foregroundColor(INK)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(PANEL)
                    .cornerRadius(4)
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(BRIGHT, lineWidth: 1))
            }

            // Zoom directly below the viewfinder. Hidden when the
            // camera reports no zoom range, so it is never dead UI.
            if engine.maxZoom > 1.01 {
                HStack(spacing: 8) {
                    zoomButton("−") { engine.nudgeZoom(-0.2) }
                    Slider(value: $zoomProgress, in: 0 ... 100)
                        .tint(DIM)
                        .onChange(of: zoomProgress) { _, new in
                            let max = engine.maxZoom
                            let ratio = 1.0 + Float(new / 100) * (max - 1.0)
                            if abs(ratio - engine.zoom) > 0.02 {
                                engine.setZoom(ratio)
                            }
                        }
                    zoomButton("+") { engine.nudgeZoom(0.2) }
                    Text(String(format: "%.1f×", engine.zoom))
                        .font(.system(size: 14))
                        .foregroundColor(DIM)
                        .frame(minWidth: 48)
                }
                .padding(.vertical, 8)
                .onChange(of: engine.zoom) { _, new in
                    let max = engine.maxZoom
                    if max > 1.0 {
                        let p = Double((new - 1.0) / (max - 1.0) * 100)
                        if abs(p - zoomProgress) > 1 { zoomProgress = p }
                    }
                }
            }

            Text(store.status)
                .font(.system(size: 15))
                .foregroundColor(DIM)
                .lineSpacing(4)
                .padding(.vertical, 10)

            bigButton(engine.isRecording ? "■ Stop  \(elapsedText)" : "● Record") {
                toggleRecord()
            }

            smallButton(engine.isFront ? "🤳 Front camera" : "📷 Back camera") {
                if !engine.isRecording { engine.switchCamera() }
            }
            .padding(.top, 6)
        }
    }

    // ---------- screens ----------

    private func showScreen(_ name: String) {
        if name == "record" {
            if !cameraConfigured {
                cameraConfigured = true
                engine.requestAccessAndConfigure()
            } else {
                engine.resumeSession()
            }
        } else {
            // Leaving the record screen stops a live take (kept, like
            // backgrounding) and parks the camera; home refreshes both
            // lists so a just-finished take shows immediately.
            if engine.isRecording { engine.stopVideo() }
            stopLocalPlayback()
            engine.pauseSession()
            store.refresh()
            store.loadHub()
        }
        screen = name
    }

    // ---------- recording ----------

    private func toggleRecord() {
        if engine.cameraDenied {
            store.status = "Camera access is off — enable it in Settings to record."
            return
        }
        if engine.isRecording {
            engine.stopVideo()
            return
        }
        if playingName != nil { stopLocalPlayback() }
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("capture_\(UUID().uuidString).mov")
        engine.startVideo(to: tempURL)
    }

    // ---------- in-viewfinder playback ----------

    private func startPlayer(url: URL, label: String) {
        if engine.isRecording { return }
        stopLocalPlayback()
        playingName = label
        let p = AVPlayer(url: url)
        player = p
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: p.currentItem,
            queue: .main) { [self] _ in stopLocalPlayback() }
        p.play()
    }

    /// Tapping a session plays it inside the viewfinder with ▶ / ⏸ / ✕
    /// below it, like Android. Recording stops it.
    private func playInViewfinder(_ name: String) {
        guard let url = store.url(for: name) else {
            store.status = "That session file is missing from this device."
            return
        }
        if engine.isRecording { return }
        // Sessions live on home; playback happens on the record screen.
        showScreen("record")
        playingHubId = nil
        startPlayer(url: url, label: name)
    }

    /// Hub sessions stream their Cloud copy through the same overlay.
    private func playHubSession(_ session: HubSession) {
        let str = (session.hlsUrl?.isEmpty == false) ? session.hlsUrl : session.mp4Url
        guard let str, let url = URL(string: str) else {
            store.status = "No playable stream on this hub session yet."
            return
        }
        if engine.isRecording { return }
        showScreen("record")
        playingHubId = session.videoId
        startPlayer(url: url, label: "hub:" + session.videoId)
    }

    private func stopLocalPlayback() {
        player?.pause()
        if let o = endObserver {
            NotificationCenter.default.removeObserver(o)
            endObserver = nil
        }
        player = nil
        playingName = nil
        playingHubId = nil
    }

    // ---------- sessions ----------

    private func sessionRow(_ row: SessionRow) -> some View {
        HStack(spacing: 0) {
            Text(row.leftIcon)
                .font(.system(size: 16))
                .foregroundColor(INK)
                .frame(minWidth: 32)
            Text(row.middleText)
                .font(.system(size: 15))
                .foregroundColor(INK)
                .lineLimit(1)
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
            // Cloud-linking never removes the on-device download:
            // linked rows keep ↓ next to their cloud action.
            if row.rightKind != .download {
                Button("↓") { store.downloadSingle(row.name) }
                    .font(.system(size: 20))
                    .foregroundColor(DIM)
                    .frame(width: 40, height: 36)
            }
            rightAction(row)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 6)
        .contentShape(Rectangle())
        .onTapGesture { playInViewfinder(row.name) }
        .onLongPressGesture(minimumDuration: 0.6) {
            confirmDeleteLesson(row.name)
        }
    }

    @ViewBuilder
    private func rightAction(_ row: SessionRow) -> some View {
        switch row.rightKind {
        case .download:
            Button("↓") { store.downloadSingle(row.name) }
                .font(.system(size: 20))
                .foregroundColor(DIM)
                .frame(width: 40, height: 36)
        case .share:
            Button("↗") { shareCloudLinkFor(row.name) }
                .font(.system(size: 20))
                .foregroundColor(INK)
                .frame(width: 40, height: 36)
                .background(PANEL)
                .cornerRadius(4)
        case let .progress(pct):
            Text("\(pct)%")
                .font(.system(size: 13))
                .foregroundColor(DIM)
                .frame(width: 40, height: 36)
        case .processing:
            Text("…")
                .font(.system(size: 13))
                .foregroundColor(DIM)
                .frame(width: 40, height: 36)
        case .failed:
            Button("!") { store.retryCloud(row.name) }
                .font(.system(size: 15))
                .foregroundColor(DIM)
                .frame(width: 40, height: 36)
        }
    }

    // ---------- widgets ----------

    private func bigButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 18))
                .foregroundColor(INK)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 13)
                .background(PANEL)
                .cornerRadius(4)
        }
        .padding(.vertical, 4)
    }

    private func smallButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 14))
                .foregroundColor(DIM)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 9)
                .background(Color.clear)
                .cornerRadius(4)
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(LINE, lineWidth: 1))
        }
    }

    private func zoomButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 18))
                .foregroundColor(INK)
                .frame(width: 48)
                .padding(.vertical, 7)
                .background(PANEL)
                .cornerRadius(4)
        }
    }

    private func playerButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 15))
                .foregroundColor(INK)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                .background(PANEL)
                .cornerRadius(4)
        }
    }

    private func cloudField(label: String, text: Binding<String>, secure: Bool, prompt: String = "") -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.system(size: 14))
                .foregroundColor(DIM)
                .padding(.top, 10)
            Group {
                if secure {
                    SecureField(prompt, text: text)
                } else {
                    TextField(prompt, text: text)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }
            .font(.system(size: 16))
            .foregroundColor(INK)
            .padding(9)
            .background(BG)
            .cornerRadius(4)
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(LINE, lineWidth: 1))
        }
    }

    private func loadCloudFields() {
        // Stored overrides only: loading effective values would
        // persist the compiled defaults as overrides on open and
        // shadow later stamp rotations. The placeholders name the
        // build defaults instead.
        signerUrl = store.cloud.signerUrl
        signerToken = store.cloud.signerToken
        libraryId = store.cloud.libraryId
        apiKey = store.cloud.apiKey
    }

    private static func fmt(_ s: Int) -> String {
        "\(s / 60):\(String(format: "%02d", s % 60))"
    }

    /// Long-press a session to delete it — the alert above confirms,
    /// then the store deletes cloud-first. Mirrors Android's
    /// confirmDeleteLesson / the web's confirmDeleteLesson.
    private func confirmDeleteLesson(_ name: String) {
        pendingDelete = name
    }

    /// Per-session Cloud link share entry point, mirroring Android's
    /// shareCloudLinkFor / the web's shareCloudLinkFor.
    private func shareCloudLinkFor(_ name: String) {
        store.shareCloudLinkFor(name)
    }

    // ---------- hub detail ----------

    private func hubDetailCard(_ detail: HubSession) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(detail.title ?? detail.videoId)
                    .font(.system(size: 17))
                    .foregroundColor(INK)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button("✕") {
                    if playingHubId == detail.videoId { stopLocalPlayback() }
                    store.closeHubSession()
                }
                .font(.system(size: 15))
                .foregroundColor(DIM)
                .frame(width: 36, height: 32)
            }
            Text(detail.lessonDate ?? "")
                .font(.system(size: 14))
                .foregroundColor(DIM)
                .padding(.bottom, 6)
            HStack(spacing: 8) {
                playerButton("▶ Play") { playHubSession(detail) }
                playerButton("↗") { store.shareHubSession(detail) }
                playerButton("🗑") { pendingHubDelete = detail }
            }
            .padding(.bottom, 8)
            if let writeup = detail.writeupMd, !writeup.isEmpty {
                Text(writeup)
                    .font(.system(size: 15))
                    .foregroundColor(INK)
                    .lineSpacing(3)
                    .padding(.bottom, 8)
            }
            ForEach(Array((detail.corrections ?? []).enumerated()), id: \.offset) { _, c in
                Text("• \(c.start ?? "")  \(c.quote ?? "")")
                    .font(.system(size: 15))
                    .foregroundColor(INK)
                    .lineSpacing(3)
                if let fix = c.correcting, !fix.isEmpty {
                    Text("  → \(fix)")
                        .font(.system(size: 14))
                        .foregroundColor(DIM)
                        .lineSpacing(3)
                }
            }
            .padding(.bottom, 4)
            ForEach(Array((detail.chapters ?? []).enumerated()), id: \.offset) { _, ch in
                Text("§ \(ch.start ?? "")  \(ch.label ?? "")")
                    .font(.system(size: 14))
                    .foregroundColor(DIM)
                    .lineSpacing(3)
            }
        }
        .padding(14)
        .background(PANEL)
        .cornerRadius(4)
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(LINE, lineWidth: 1))
        .padding(.top, 8)
    }
}

// MARK: - UIKit bridges

final class PreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}

struct CameraPreview: UIViewRepresentable {
    let engine: CameraEngine

    func makeUIView(context: Context) -> PreviewUIView {
        let view = PreviewUIView()
        view.backgroundColor = .black
        engine.attachPreview(view.previewLayer)
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {}
}

struct PlayerView: UIViewRepresentable {
    let player: AVPlayer

    func makeUIView(context: Context) -> PlayerUIView {
        let view = PlayerUIView()
        view.backgroundColor = .black
        view.playerLayer.player = player
        return view
    }

    func updateUIView(_ uiView: PlayerUIView, context: Context) {
        // SwiftUI reuses the UIView: without this, tapping session B
        // keeps showing session A's player.
        uiView.playerLayer.player = player
    }
}

final class PlayerUIView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }
    var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
}

/// System video picker for uploads. The picked video is copied into
/// the clips folder by the store, so it rides the exact session path
/// of a take from there on.
struct UploadPicker: UIViewControllerRepresentable {
    var onPick: (URL) -> Void
    var onCancel: () -> Void

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.movie], asCopy: true)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onPick: onPick, onCancel: onCancel)
    }

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: (URL) -> Void
        let onCancel: () -> Void

        init(onPick: @escaping (URL) -> Void, onCancel: @escaping () -> Void) {
            self.onPick = onPick
            self.onCancel = onCancel
        }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            if let url = urls.first { onPick(url) }
        }

        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            onCancel()
        }
    }
}
