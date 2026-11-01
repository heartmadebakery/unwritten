import AVFoundation
import AVKit
import PhotosUI
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

// Same dark palette as the Android app and the web app.
private let BG = Color(hex: "17130E")
private let PANEL = Color(hex: "241C12")
private let INK = Color(hex: "F5EAD6")
private let DIM = Color(hex: "B8A888")
private let UWB_RED = Color(hex: "C0392B")
private let BRIGHT = Color(hex: "E74C3C")
private let LINE = Color(hex: "2E2213")

/// Screens pushed over home. Record owns the camera; a hub session
/// opens its own detail screen with its own player.
enum Route: Hashable {
    case record
    case hub(String)
}

/// Unwritten Craft. Home lands on the hub sessions with Record and
/// Upload above them; recording is one screen of the app, not a
/// separate app. The pipeline (transcribe -> write-up -> corrections)
/// works afterwards on each session — a take or an upload alike.
///
/// Same design and behavior as the web and Android apps, in iOS
/// idioms: a NavigationStack (system back + edge swipe), grouped
/// lists, context menus and swipe actions on rows, pull to refresh,
/// a settings sheet, and the Photos picker for uploads.
struct ContentView: View {
    @StateObject private var engine = CameraEngine()
    @StateObject private var store = SessionStore()
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.openURL) private var openURL

    @State private var path: [Route] = []

    @State private var recordStart = Date()
    @State private var elapsedText = "0:00"
    @State private var timer: Timer?

    @State private var player: AVPlayer?
    @State private var playingName: String?
    @State private var endObserver: NSObjectProtocol?
    @State private var hubPlayer: AVPlayer?

    @State private var showCloudPanel = false
    @State private var pendingDelete: String?
    @State private var pendingHubDelete: HubSession?
    @State private var zoomProgress: Double = 0

    @State private var signerUrl = ""
    @State private var signerToken = ""
    @State private var libraryId = ""
    @State private var apiKey = ""

    @State private var cameraConfigured = false
    @State private var showUploadPicker = false
    @State private var showPhotosPicker = false
    @State private var photoItem: PhotosPickerItem?
    @State private var fetchUrl = ""

    /// Record is the top screen: the camera may run.
    private var onRecordScreen: Bool { path.last == .record }

    var body: some View {
        NavigationStack(path: $path) {
            homeView
                .navigationTitle("Unwritten Craft")
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .record:
                        recordView
                    case let .hub(videoId):
                        hubScreen(videoId)
                    }
                }
        }
        .tint(INK)
        .preferredColorScheme(.dark)
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
        .onChange(of: path) { old, new in
            // Every way on or off the record screen (button, row tap,
            // back button, edge swipe) changes the path; the camera
            // follows it.
            let was = old.last == .record
            let now = new.last == .record
            if now && !was { showScreen("record") }
            if was && !now { showScreen("home") }
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
                hubPlayer?.pause()
            } else {
                // A grant in Settings takes effect without a relaunch.
                // The record screen owns the camera: returning to home
                // must not restart it behind the hub.
                engine.refreshPermissions()
                if onRecordScreen { engine.resumeSession() }
            }
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
                    stopHubPlayer()
                    store.deleteHubSession(session)
                    if case .hub? = path.last { path.removeLast() }
                }
                pendingHubDelete = nil
            }
            Button("Keep", role: .cancel) { pendingHubDelete = nil }
        } message: {
            Text("Delete '\(pendingHubDelete?.title ?? "")' from the cloud and the hub?")
        }
        .sheet(isPresented: $showCloudPanel) {
            cloudSettingsSheet
        }
        .sheet(isPresented: $showUploadPicker) {
            UploadPicker(onPick: { url in
                showUploadPicker = false
                store.registerUpload(sourceURL: url)
            }, onCancel: { showUploadPicker = false })
        }
        .photosPicker(isPresented: $showPhotosPicker, selection: $photoItem,
                      matching: .videos, preferredItemEncoding: .current)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            photoItem = nil
            importFromPhotos(item)
        }
    }

    // One app, two screens. Home (record/upload actions with the hub
    // last) is the landing; record owns the viewfinder and the camera
    // behind it, with cloud and device sessions below.
    private var homeView: some View {
        List {
            Section {
                Button {
                    path.append(.record)
                } label: {
                    Label { Text("Record").foregroundColor(INK) } icon: {
                        Image(systemName: "record.circle").foregroundColor(BRIGHT)
                    }
                    .font(.system(size: 18))
                }
                Menu {
                    Button {
                        showPhotosPicker = true
                    } label: {
                        Label("Photo Library", systemImage: "photo.on.rectangle")
                    }
                    Button {
                        showUploadPicker = true
                    } label: {
                        Label("Files", systemImage: "folder")
                    }
                } label: {
                    Label("Upload video", systemImage: "square.and.arrow.up.on.square")
                        .font(.system(size: 18))
                        .foregroundColor(INK)
                }
                // Or paste a link: watch pages queue to the pipeline
                // fetcher, which downloads and processes them.
                TextField("Paste a video link…", text: $fetchUrl)
                    .font(.system(size: 16))
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                Button {
                    store.queueFetchUrl(fetchUrl)
                    fetchUrl = ""
                } label: {
                    Label("Fetch from link", systemImage: "arrow.down.circle")
                        .font(.system(size: 18))
                        .foregroundColor(INK)
                }
            } header: {
                Text("Record, upload, and revisit craft lessons.")
                    .textCase(nil)
                    .font(.system(size: 15))
                    .foregroundColor(DIM)
            } footer: {
                Text(store.status)
                    .font(.system(size: 14))
                    .foregroundColor(DIM)
            }
            .listRowBackground(PANEL)

            Section {
                if store.hubRows.isEmpty {
                    Text(store.hubStatusText())
                        .font(.system(size: 15))
                        .foregroundColor(DIM)
                } else {
                    ForEach(store.hubRows) { row in
                        NavigationLink(value: Route.hub(row.videoId)) {
                            Label {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(row.title ?? row.videoId)
                                        .font(.system(size: 16))
                                        .foregroundColor(INK)
                                        .lineLimit(1)
                                    if let date = row.lessonDate, !date.isEmpty {
                                        Text(date)
                                            .font(.system(size: 13))
                                            .foregroundColor(DIM)
                                    }
                                }
                            } icon: {
                                Image(systemName: "play.rectangle").foregroundColor(DIM)
                            }
                        }
                    }
                }
            } header: {
                Text("Hub").sectionHeader()
            }
            .listRowBackground(PANEL)
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(BG)
        .refreshable {
            store.refresh()
            store.loadHub()
        }
    }

    private var recordView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Viewfinder with in-player overlay (playback appears
                // inside the viewfinder, like Android and the web).
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
                                    .font(.system(size: 16).monospacedDigit())
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
                            playerButton("play.fill", "Play") { player?.play() }
                            playerButton("pause.fill", "Pause") { player?.pause() }
                            playerButton("xmark", "Close") { stopLocalPlayback() }
                        }
                        .padding(8)
                        .background(Color.black.opacity(0.66))
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 10))

                // A video-only stream must never be silent about being
                // silent: the lesson IS the mentor's words.
                if engine.micWarning {
                    Text("🎤 No microphone. The mentor's words won't be recorded — and the mentor's words are the whole point. Check Settings > Privacy > Microphone.")
                        .font(.system(size: 15))
                        .foregroundColor(.white)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(UWB_RED)
                        .cornerRadius(8)
                        .padding(.top, 8)
                }

                // Quiet-minute check, mirroring the web app: a full
                // quiet minute raises this banner; speech clears it.
                if engine.speechWarning {
                    Text("🔇 Quiet for a while. No speech in the last minute — and the mentor's words are the whole point. Check the mic is close enough.")
                        .font(.system(size: 15))
                        .foregroundColor(INK)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(PANEL)
                        .cornerRadius(8)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(BRIGHT, lineWidth: 1))
                        .padding(.top, 8)
                }

                // Zoom directly below the viewfinder. Hidden when the
                // camera reports no zoom range, so it is never dead UI.
                if engine.maxZoom > 1.01 {
                    HStack(spacing: 8) {
                        zoomButton("minus", "Zoom out") { engine.nudgeZoom(-0.2) }
                        Slider(value: $zoomProgress, in: 0 ... 100)
                            .tint(DIM)
                            .onChange(of: zoomProgress) { _, new in
                                let max = engine.maxZoom
                                let ratio = 1.0 + Float(new / 100) * (max - 1.0)
                                if abs(ratio - engine.zoom) > 0.02 {
                                    engine.setZoom(ratio)
                                }
                            }
                        zoomButton("plus", "Zoom in") { engine.nudgeZoom(0.2) }
                        Text(String(format: "%.1f×", engine.zoom))
                            .font(.system(size: 14).monospacedDigit())
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

                Button(action: toggleRecord) {
                    Text(engine.isRecording ? "■ Stop  \(elapsedText)" : "● Record")
                        .font(.system(size: 19, weight: .semibold).monospacedDigit())
                        .foregroundColor(engine.isRecording ? .white : INK)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 15)
                        .background(engine.isRecording ? UWB_RED : PANEL)
                        .cornerRadius(12)
                }
                .sensoryFeedback(.impact, trigger: engine.isRecording)

                // Cloud + device sessions live on the record screen now.
                HStack {
                    Label("Cloud", systemImage: store.cloudOn ? "icloud" : "icloud.slash")
                        .foregroundColor(INK)
                    Spacer()
                    Toggle(isOn: Binding(get: { store.cloudOn },
                                         set: { _ in store.toggleCloud() })) {
                    }
                    .labelsHidden()
                    .tint(DIM)
                }
                .padding(.vertical, 8)
                // Export is the offline fallback: only with Cloud off.
                if !store.cloudOn {
                    Button {
                        store.exportSessions()
                    } label: {
                        Label("Export sessions to Downloads", systemImage: "square.and.arrow.up")
                            .foregroundColor(INK)
                    }
                    .padding(.bottom, 8)
                }

                // This device: left status icon, middle date + duration,
                // right share/download. Rows keep their context menu
                // (swipe actions only fire inside a List, so Delete
                // here means the context menu, not a swipe).
                Text("This device")
                    .font(.system(size: 17))
                    .foregroundColor(DIM)
                    .padding(.top, 14)
                    .padding(.bottom, 4)
                if store.rows.isEmpty {
                    Text("Nothing yet.")
                        .font(.system(size: 15))
                        .foregroundColor(DIM)
                } else {
                    ForEach(store.rows) { row in
                        sessionRow(row)
                    }
                }
                Text("Every session is saved on this device, and with Cloud on a copy is uploaded for streamed playback. Tap a session to play it; touch and hold to share or delete it from the device and the cloud.")
                    .font(.system(size: 13))
                    .foregroundColor(DIM)
                    .padding(.top, 8)

                // Debug overrides hide behind a small link at the bottom.
                Button {
                    if !showCloudPanel { loadCloudFields() }
                    showCloudPanel = true
                } label: {
                    Text("Advanced settings")
                        .font(.system(size: 14))
                        .foregroundColor(DIM)
                }
                .padding(.vertical, 8)
            }
            .padding(14)
        }
        .background(BG)
        .navigationTitle("Record")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    if !engine.isRecording { engine.switchCamera() }
                } label: {
                    Image(systemName: "arrow.triangle.2.circlepath.camera")
                }
                .disabled(engine.isRecording)
                .accessibilityLabel(engine.isFront ? "Front camera — switch to back" : "Back camera — switch to front")
            }
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

    // ---------- upload ----------

    /// A Photos pick is copied out of the library, then rides the same
    /// path as a Files pick (and a take): clips folder, then Cloud.
    private func importFromPhotos(_ item: PhotosPickerItem) {
        store.status = "Copying upload…"
        Task {
            do {
                guard let movie = try await item.loadTransferable(type: PickedMovie.self) else {
                    store.status = "That item isn't a video — pick a video."
                    return
                }
                store.registerUpload(sourceURL: movie.url)
                try? FileManager.default.removeItem(at: movie.url)
            } catch {
                store.status = "Upload failed: \(error.localizedDescription)"
            }
        }
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

    /// Tapping a session plays it inside the viewfinder with play /
    /// pause / close over it, like Android and the web. Recording
    /// stops it.
    private func playInViewfinder(_ name: String) {
        guard let url = store.url(for: name) else {
            store.status = "That session file is missing from this device."
            return
        }
        if engine.isRecording { return }
        // Sessions live on home; playback happens on the record screen.
        if !onRecordScreen { path.append(.record) }
        startPlayer(url: url, label: name)
    }

    /// Hub sessions stream in the hub screen's own player — watching a
    /// published lesson never opens the camera. With no stream URL the
    /// Cloud embed page opens instead (Android's openInBrowser), so
    /// Play is never a dead button.
    private func playHubSession(_ session: HubSession) {
        let str = (session.hlsUrl?.isEmpty == false) ? session.hlsUrl : session.mp4Url
        guard let str, !str.isEmpty, let url = URL(string: str) else {
            if let embed = store.hubEmbedUrl(session), let url = URL(string: embed) {
                store.status = "Opening the Cloud player for this session."
                openURL(url)
            } else {
                store.status = "No playable stream on this hub session yet."
            }
            return
        }
        stopHubPlayer()
        let p = AVPlayer(url: url)
        hubPlayer = p
        p.play()
    }

    private func stopHubPlayer() {
        hubPlayer?.pause()
        hubPlayer = nil
    }

    private func stopLocalPlayback() {
        player?.pause()
        if let o = endObserver {
            NotificationCenter.default.removeObserver(o)
            endObserver = nil
        }
        player = nil
        playingName = nil
    }

    // ---------- sessions ----------

    /// SF Symbol for the row's link state (the store's text icons stay
    /// the shared contract with Android and the web).
    private func symbolFor(_ leftIcon: String) -> String {
        switch leftIcon {
        case "📱": return "iphone"
        case "☁↑": return "icloud.and.arrow.up"
        case "☁…": return "icloud"
        case "☁!": return "exclamationmark.icloud"
        default: return "checkmark.icloud"
        }
    }

    private func sessionRow(_ row: SessionRow) -> some View {
        HStack(spacing: 10) {
            Image(systemName: symbolFor(row.leftIcon))
                .foregroundColor(row.leftIcon == "☁!" ? BRIGHT : DIM)
                .frame(width: 26)
            Text(row.middleText)
                .font(.system(size: 15).monospacedDigit())
                .foregroundColor(INK)
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
            // Cloud-linking never removes the on-device download:
            // linked rows keep ↓ next to their cloud action.
            if row.rightKind != .download {
                rowIconButton("arrow.down.circle", "Save a copy") { store.downloadSingle(row.name) }
            }
            rightAction(row)
        }
        .contentShape(Rectangle())
        .onTapGesture { playInViewfinder(row.name) }
        .contextMenu {
            Button {
                playInViewfinder(row.name)
            } label: {
                Label("Play", systemImage: "play")
            }
            if row.rightKind == .share {
                Button {
                    shareCloudLinkFor(row.name)
                } label: {
                    Label("Share Cloud link", systemImage: "link")
                }
            }
            if row.rightKind == .failed {
                Button {
                    store.retryCloud(row.name)
                } label: {
                    Label("Retry upload", systemImage: "arrow.clockwise.icloud")
                }
            }
            Button {
                store.downloadSingle(row.name)
            } label: {
                Label("Save a copy", systemImage: "square.and.arrow.down")
            }
            Button(role: .destructive) {
                confirmDeleteLesson(row.name)
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            Button {
                confirmDeleteLesson(row.name)
            } label: {
                Label("Delete", systemImage: "trash")
            }
            .tint(UWB_RED)
        }
    }

    @ViewBuilder
    private func rightAction(_ row: SessionRow) -> some View {
        switch row.rightKind {
        case .download:
            rowIconButton("arrow.down.circle", "Save a copy") { store.downloadSingle(row.name) }
        case .share:
            rowIconButton("square.and.arrow.up", "Share Cloud link") { shareCloudLinkFor(row.name) }
        case let .progress(pct):
            Text("\(pct)%")
                .font(.system(size: 13).monospacedDigit())
                .foregroundColor(DIM)
                .frame(width: 40, height: 32)
        case .processing:
            ProgressView()
                .frame(width: 40, height: 32)
        case .failed:
            rowIconButton("arrow.clockwise", "Retry upload") { store.retryCloud(row.name) }
        }
    }

    // ---------- widgets ----------

    private func rowIconButton(_ symbol: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 18))
                .foregroundColor(INK)
                .frame(width: 40, height: 32)
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(label)
    }

    private func zoomButton(_ symbol: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(INK)
                .frame(width: 44, height: 34)
                .background(PANEL)
                .cornerRadius(8)
        }
        .accessibilityLabel(label)
    }

    private func playerButton(_ symbol: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 15))
                .foregroundColor(INK)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                .background(PANEL)
                .cornerRadius(6)
        }
        .accessibilityLabel(label)
    }

    // ---------- cloud settings ----------

    private var cloudSettingsSheet: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(CloudStore.CLOUD_SIGNER_DEFAULT, text: $signerUrl, prompt: Text(CloudStore.CLOUD_SIGNER_DEFAULT))
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Signer token", text: $signerToken, prompt: Text("baked into this build"))
                } header: {
                    Text("Signer")
                } footer: {
                    Text("Prefilled by the build — override the URL only to point elsewhere, the token only if it was rotated.")
                }
                Section {
                    TextField("Stream library ID", text: $libraryId, prompt: Text("e.g. 402315"))
                        .keyboardType(.numberPad)
                    SecureField("Library API key", text: $apiKey, prompt: Text("AccessKey from the library's API page"))
                } header: {
                    Text("Or, without a signer")
                } footer: {
                    Text("On by default and purely additive: every session is still saved on this device first, then a copy is uploaded for streamed playback, and the share action on the session offers its link when ready. A library key talks to the library directly instead of the signer (it can manage this one library, so keep it on the mentor's device only); it lives on this device.")
                }
            }
            .scrollContentBackground(.hidden)
            .background(BG)
            .navigationTitle("Cloud settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { showCloudPanel = false }
                }
            }
            .onChange(of: signerUrl) { _, v in store.cloud.signerUrl = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
            .onChange(of: signerToken) { _, v in store.cloud.signerToken = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
            .onChange(of: libraryId) { _, v in store.cloud.libraryId = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
            .onChange(of: apiKey) { _, v in store.cloud.apiKey = v.trimmingCharacters(in: .whitespacesAndNewlines); store.paintCloudToggle() }
        }
        .tint(INK)
        .preferredColorScheme(.dark)
    }

    private func loadCloudFields() {
        // Stored overrides only: loading effective values would
        // persist the compiled defaults as overrides on open and
        // shadow later stamp rotations. The placeholders (prompt)
        // name the build defaults instead.
        signerUrl = store.cloud.signerUrl
        signerToken = store.cloud.signerToken
        libraryId = store.cloud.libraryId
        apiKey = store.cloud.apiKey
    }

    private static func fmt(_ s: Int) -> String {
        "\(s / 60):\(String(format: "%02d", s % 60))"
    }

    /// Long-press (context menu) or swipe a session to delete it — the
    /// alert above confirms, then the store deletes cloud-first.
    /// Mirrors Android's confirmDeleteLesson / the web's
    /// confirmDeleteLesson.
    private func confirmDeleteLesson(_ name: String) {
        pendingDelete = name
    }

    /// Per-session Cloud link share entry point, mirroring Android's
    /// shareCloudLinkFor / the web's shareCloudLinkFor.
    private func shareCloudLinkFor(_ name: String) {
        store.shareCloudLinkFor(name)
    }

    // ---------- hub detail ----------

    /// One hub session, pushed from home: its own player (never the
    /// camera), the write-up, corrections and chapters, with Share and
    /// Delete in the toolbar.
    private func hubScreen(_ videoId: String) -> some View {
        Group {
            if let detail = store.hubDetail, detail.videoId == videoId {
                ScrollView { hubDetailCard(detail).padding(14) }
            } else {
                VStack(spacing: 12) {
                    ProgressView()
                    Text(store.status)
                        .font(.system(size: 14))
                        .foregroundColor(DIM)
                        .multilineTextAlignment(.center)
                }
                .padding(24)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(BG)
        .navigationTitle(store.hubRows.first(where: { $0.videoId == videoId })?.title ?? "Session")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let detail = store.hubDetail, detail.videoId == videoId {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button {
                        store.shareHubSession(detail)
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel("Share session link")
                    Button(role: .destructive) {
                        pendingHubDelete = detail
                    } label: {
                        Image(systemName: "trash")
                    }
                    .accessibilityLabel("Delete from the hub and the cloud")
                }
            }
        }
        .task(id: videoId) {
            store.status = "" // this screen's line reports only its own actions
            store.openHubSession(HubSession(videoId: videoId))
        }
        .onDisappear {
            stopHubPlayer()
            if store.hubDetail?.videoId == videoId { store.closeHubSession() }
        }
    }

    private func hubDetailCard(_ detail: HubSession) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if let hubPlayer {
                VideoPlayer(player: hubPlayer)
                    .frame(height: 220)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .padding(.bottom, 10)
            } else {
                Button {
                    playHubSession(detail)
                } label: {
                    Label("Play", systemImage: "play.fill")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(INK)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                        .background(PANEL)
                        .cornerRadius(10)
                }
                .padding(.bottom, 10)
            }
            Text(detail.title ?? detail.videoId)
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(INK)
            if let date = detail.lessonDate, !date.isEmpty {
                Text(date)
                    .font(.system(size: 14))
                    .foregroundColor(DIM)
                    .padding(.top, 2)
            }
            // Share/delete/play outcomes report here, so no action on
            // this screen ever fails silently.
            Text(store.status)
                .font(.system(size: 14))
                .foregroundColor(DIM)
                .padding(.top, 8)
            if let writeup = detail.writeupMd, !writeup.isEmpty {
                Text(ContentView.markdown(writeup))
                    .font(.system(size: 16))
                    .foregroundColor(INK)
                    .lineSpacing(4)
                    .textSelection(.enabled)
                    .padding(.top, 12)
            }
            if let corrections = detail.corrections, !corrections.isEmpty {
                Text("Corrections").sectionHeader().padding(.top, 18).padding(.bottom, 6)
                ForEach(Array(corrections.enumerated()), id: \.offset) { _, c in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("• \(c.start ?? "")  \(c.quote ?? "")")
                            .font(.system(size: 15))
                            .foregroundColor(INK)
                        if let fix = c.correcting, !fix.isEmpty {
                            Text("  → \(fix)")
                                .font(.system(size: 14))
                                .foregroundColor(DIM)
                        }
                    }
                    .padding(.bottom, 6)
                }
            }
            if let chapters = detail.chapters, !chapters.isEmpty {
                Text("Chapters").sectionHeader().padding(.top, 12).padding(.bottom, 6)
                ForEach(Array(chapters.enumerated()), id: \.offset) { _, ch in
                    Text("§ \(ch.start ?? "")  \(ch.label ?? "")")
                        .font(.system(size: 14))
                        .foregroundColor(DIM)
                        .padding(.bottom, 3)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Write-ups are Markdown; inline styling renders, line breaks stay.
    private static func markdown(_ text: String) -> AttributedString {
        let opts = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: text, options: opts)) ?? AttributedString(text)
    }
}

private extension Text {
    func sectionHeader() -> some View {
        self.font(.system(size: 13, weight: .semibold))
            .foregroundColor(DIM)
            .textCase(.uppercase)
    }
}

/// A Photos video copied to a temp file the app owns (the received
/// file is only valid inside the import closure).
struct PickedMovie: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .movie) { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent("pick_\(UUID().uuidString).\(ext)")
            try FileManager.default.copyItem(at: received.file, to: dest)
            return PickedMovie(url: dest)
        }
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
