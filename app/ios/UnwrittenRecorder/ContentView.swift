import AVFoundation
import AVKit
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

extension UIColor {
    convenience init(hex: String) {
        let v = UInt32(hex, radix: 16) ?? 0
        self.init(red: CGFloat((v >> 16) & 0xFF) / 255.0,
                  green: CGFloat((v >> 8) & 0xFF) / 255.0,
                  blue: CGFloat(v & 0xFF) / 255.0, alpha: 1)
    }
}

extension Color {
    init(hex: String) { self.init(uiColor: UIColor(hex: hex)) }

    /// A colour that follows the system appearance: light hex, dark hex.
    init(light: String, dark: String) {
        self.init(uiColor: UIColor { traits in
            UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

// Hearth (docs/DESIGN.md): warm paper by default, a matching dark set
// that follows the system — the same tokens as the web and Android
// apps. Names kept from the old dark palette: BG canvas, PANEL
// surface, INK, DIM secondary ink, BRIGHT the ember accent, UWB_RED
// the danger fill.
private let BG = Color(light: "FAF6F1", dark: "171310")
private let PANEL = Color(light: "FFFFFF", dark: "221C18")
private let SUNKEN = Color(light: "F3ECE4", dark: "2D2621")
private let INK = Color(light: "2A211C", dark: "F7EFE6")
private let DIM = Color(light: "6F625A", dark: "B9AA9C")
private let LINE = Color(light: "EADFD3", dark: "3A312A")
private let RING = Color(light: "DCCFC2", dark: "5A4E44")
private let BRIGHT = Color(hex: "D2452A")
private let EMBER_INK = Color(light: "B83A20", dark: "FF8A6B")
private let EMBER_SOFT = Color(light: "FCE8E1", dark: "3A2420")
private let SAGE = Color(light: "2F7A4B", dark: "7FD39B")
private let SAGE_SOFT = Color(light: "E3F2E7", dark: "1F2E24")
private let HONEY = Color(light: "8A5A00", dark: "F2C46B")
private let HONEY_SOFT = Color(light: "FFF3D6", dark: "33281A")
private let UWB_RED = Color(hex: "C23B22")

// Cover washes, letter on wash, picked by washIndex(title).
private let WASH: [Color] = [
    Color(light: "FCE3D9", dark: "3A2420"), Color(light: "FBEFD2", dark: "33281A"),
    Color(light: "E2EFE1", dark: "1F2E24"), Color(light: "DDEBF4", dark: "1C2A33"),
    Color(light: "ECE3F3", dark: "2B2233"), Color(light: "F2E3D8", dark: "33251C"),
]
private let WASH_INK: [Color] = [
    Color(light: "B5432A", dark: "FF9C82"), Color(light: "8A5A00", dark: "F2C46B"),
    Color(light: "2F6B3F", dark: "7FD39B"), Color(light: "2B5F80", dark: "8CC4E6"),
    Color(light: "6A4486", dark: "C7A6E0"), Color(light: "8A4F2E", dark: "E0A884"),
]

/// A lesson wears the same warm wash on every platform: the sum of
/// the title's UTF-16 code units, modulo the six cover pairs.
private func washIndex(_ title: String) -> Int {
    title.utf16.reduce(0) { $0 + Int($1) } % 6
}

private func initialOf(_ title: String) -> String {
    if let ch = title.first(where: { $0.isLetter || $0.isNumber }) { return String(ch).uppercased() }
    return "•"
}

/// Tiles and the shutter dip a little while pressed, Path-style.
extension View {
    /// A centered column on wide screens (the iPad, either way up):
    /// tiles and rows stay readable instead of stretching edge to edge.
    /// On the iPhone it is the screen itself.
    func readableColumn(_ maxWidth: CGFloat = 760) -> some View {
        frame(maxWidth: maxWidth)
            .frame(maxWidth: .infinity)
            .background(BG.ignoresSafeArea())
    }
}

private struct SquishStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.easeOut(duration: 0.18), value: configuration.isPressed)
    }
}

/// Screens pushed over home. Record owns the camera; Upload offers a
/// file and a link field with previous attempts below; a hub session
/// opens its own detail screen with its own player.
enum Route: Hashable {
    case record
    case upload
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
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    /// Regular width: the iPad, full screen in either orientation.
    private var wide: Bool { horizontalSizeClass == .regular }

    @State private var path: [Route] = []

    @State private var recordStart = Date()
    @State private var elapsedText = "0:00"
    @State private var timer: Timer?

    @State private var player: AVPlayer?
    @State private var playingName: String?
    @State private var endObserver: NSObjectProtocol?
    @State private var hubPlayer: AVPlayer?
    @State private var hubItemObserver: NSKeyValueObservation?
    /// Session parts: the end of one part starts the next; the tie
    /// picker and the untie confirm for the open hub session.
    @State private var hubEndObserver: NSObjectProtocol?
    @State private var hubPlayingPart: Int = 0
    @State private var pendingTie: HubSession?
    @State private var pendingUntie: HubPart?

    @State private var showCloudPanel = false
    @State private var pendingDelete: String?
    @State private var pendingHubDelete: HubSession?
    @State private var zoomProgress: Double = 0

    /// Build values shown for debugging (read-only): the effective
    /// signer URL and whether this build carries a stamped token.

    @State private var cameraConfigured = false
    @State private var showUploadPicker = false
    @State private var showPhotosPicker = false
    @State private var photoItem: PhotosPickerItem?
    @State private var fetchUrl = ""

    /// Record is the top screen: the camera may run.
    private var onRecordScreen: Bool { path.last == .record }

    init() {
        // Hearth's headings are SF Pro Rounded — the navigation bar's
        // large and inline titles included.
        func rounded(_ size: CGFloat, _ weight: UIFont.Weight) -> UIFont {
            let base = UIFont.systemFont(ofSize: size, weight: weight)
            guard let d = base.fontDescriptor.withDesign(.rounded) else { return base }
            return UIFont(descriptor: d, size: size)
        }
        UINavigationBar.appearance().largeTitleTextAttributes = [.font: rounded(34, .heavy)]
        UINavigationBar.appearance().titleTextAttributes = [.font: rounded(17, .bold)]
    }

    /// A personal hello under the title, by the phone's own clock.
    private var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
    }

    var body: some View {
        NavigationStack(path: $path) {
            homeView
                .readableColumn()
                // The iPad (regular width) carries the large title
                // inside its column, so the bar stays quiet.
                .navigationTitle(wide ? "" : "Unwritten Craft")
                .navigationBarTitleDisplayMode(wide ? .inline : .large)
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .record:
                        recordView
                            .readableColumn()
                    case .upload:
                        uploadView
                            .readableColumn()
                    case let .hub(videoId):
                        hubScreen(videoId)
                            .readableColumn()
                    }
                }
        }
        // Links, the back button and system controls wear the ember
        // ink; light or dark follows the system (Hearth has both).
        .tint(EMBER_INK)
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
            //
            // A status line reports on the screen it was raised on, so
            // it never follows you to another one.
            store.status = ""
            // Home is the end of a continue: the choice never lingers.
            if new.isEmpty { store.joinTo = nil }
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
            if let d = pendingHubDelete, store.hubParts(d).count > 1 {
                // One overall session: every part is named before it goes.
                let parts = store.hubParts(d)
                Text("Delete all \(parts.count) parts?\n\n"
                     + parts.enumerated().map { "\($0.offset + 1). \($0.element.title ?? $0.element.videoId)" }.joined(separator: "\n")
                     + "\n\nEach is deleted from the cloud and the hub. To keep one, untie it first.")
            } else {
                Text("Delete '\(pendingHubDelete?.title ?? "")' from the cloud and the hub?")
            }
        }
        .confirmationDialog("Which session comes next?", isPresented: Binding(
            get: { pendingTie != nil },
            set: { if !$0 { pendingTie = nil } }
        ), titleVisibility: .visible) {
            if let d = pendingTie {
                let mine = Set(store.hubParts(d).map { $0.videoId })
                ForEach(store.hubRows.filter { !mine.contains($0.videoId) }) { r in
                    Button(r.title ?? r.videoId) { store.tieHubSessions(d, r.videoId) }
                }
            }
            Button("Cancel", role: .cancel) { pendingTie = nil }
        } message: {
            Text("It joins the end of this one, with any parts of its own.")
        }
        .alert("Untie this part?", isPresented: Binding(
            get: { pendingUntie != nil },
            set: { if !$0 { pendingUntie = nil } }
        )) {
            Button("Untie") {
                if let p = pendingUntie, let d = store.hubDetail {
                    stopHubPlayer()
                    store.untieHubPart(d, p.videoId)
                }
                pendingUntie = nil
            }
            Button("Keep", role: .cancel) { pendingUntie = nil }
        } message: {
            Text("'\(pendingUntie?.title ?? "")' becomes its own session again. Nothing is deleted.")
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

    /// Fetch waits for a link: the row is dimmed and inert until one
    /// is pasted, and the keyboard's Go does the same thing.
    private var canFetchLink: Bool {
        !fetchUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func fetchLink() {
        guard canFetchLink else { return }
        store.queueFetchUrl(fetchUrl)
        fetchUrl = ""
    }

    // One app, two screens. Home (record/upload actions with the hub
    // last) is the landing; record owns the viewfinder and the camera
    // behind it, with cloud and device sessions below.
    private var homeView: some View {
        List {
            // Two action tiles: Record (filled ember, the primary
            // action) and Upload video (Photos or Files).
            Section {
                HStack(spacing: 12) {
                    Button {
                        path.append(.record)
                    } label: {
                        actionTile(Text("Record"), Text("Film a lesson, the way you'd teach anyway"),
                                   symbol: "record.circle", primary: true)
                    }
                    .buttonStyle(SquishStyle())
                    .accessibilityLabel("Record")
                    Button {
                        path.append(.upload)
                    } label: {
                        actionTile(Text("Upload video"), Text("From your phone or a link"),
                                   symbol: "square.and.arrow.up", primary: false)
                    }
                    .buttonStyle(SquishStyle())
                    .accessibilityLabel("Upload video")
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            } header: {
                VStack(alignment: .leading, spacing: 2) {
                    if wide {
                        Text("Unwritten Craft")
                            .font(.system(size: 34, weight: .heavy, design: .rounded))
                            .foregroundStyle(INK)
                    }
                    Text(greeting)
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .foregroundStyle(DIM)
                    Text("Record, upload, and revisit craft lessons.")
                        .font(.system(size: 16))
                        .foregroundStyle(DIM)
                }
                .textCase(nil)
                .padding(.bottom, 8)
            }

            Section {
                if store.hubRows.isEmpty {
                    emptyState(symbol: "book.closed", title: nil, help: store.hubStatusText())
                        .listRowBackground(PANEL)
                } else {
                    ForEach(store.hubRows) { row in
                        NavigationLink(value: Route.hub(row.videoId)) {
                            HStack(spacing: 14) {
                                coverTile(row.title ?? row.videoId)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(row.title ?? row.videoId)
                                        .font(.system(size: 17, weight: .semibold))
                                        .foregroundStyle(INK)
                                        .lineLimit(1)
                                    let hubSub = store.hubSubtitle(for: row)
                                    if !hubSub.isEmpty {
                                        Text(hubSub)
                                            .font(.system(size: 14))
                                            .foregroundStyle(DIM)
                                    }
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                    .listRowBackground(PANEL)
                }
            } header: {
                sectionTitle(Text("Hub"), subtitle: "Lessons the pipeline has written up")
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(BG)
        .refreshable {
            store.refresh()
            store.loadHub()
        }
    }

    /// A home action tile: glyph on top, title and a line of help at
    /// the bottom; filled ember for the primary action, surface else.
    private func actionTile(_ title: Text, _ sub: Text, symbol: String, primary: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(systemName: symbol)
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(primary ? Color.white : EMBER_INK)
                .frame(width: 48, height: 48)
                .background(primary ? Color.white.opacity(0.2) : EMBER_SOFT,
                            in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            Spacer(minLength: 14)
            title
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundStyle(primary ? Color.white : INK)
            sub
                .font(.system(size: 14))
                .foregroundStyle(primary ? Color.white.opacity(0.88) : DIM)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 172, alignment: .topLeading)
        .background(primary ? BRIGHT : PANEL, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .shadow(color: Color.black.opacity(primary ? 0.14 : 0.06), radius: 14, y: 6)
        .contentShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
    }

    /// Section header: sentence case, bold rounded, a line of help.
    private func sectionTitle(_ title: Text, subtitle: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            title
                .font(.system(size: 21, weight: .bold, design: .rounded))
                .foregroundStyle(INK)
            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 14))
                    .foregroundStyle(DIM)
            }
        }
        .textCase(nil)
        .padding(.top, 8)
        .padding(.bottom, 4)
    }

    /// A cover tile: the lesson's initial on its warm wash.
    private func coverTile(_ title: String, size: CGFloat = 56, radius: CGFloat = 14, font: CGFloat = 24) -> some View {
        let w = washIndex(title)
        return Text(initialOf(title))
            .font(.system(size: font, weight: .heavy, design: .rounded))
            .foregroundStyle(WASH_INK[w])
            .frame(width: size, height: size)
            .background(WASH[w], in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .accessibilityHidden(true)
    }

    /// An empty state: a glyph in an ember wash, a title, a line of help.
    private func emptyState(symbol: String, title: String?, help: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: symbol)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(EMBER_INK)
                .frame(width: 56, height: 56)
                .background(EMBER_SOFT, in: Circle())
            if let title {
                Text(title).font(.system(size: 17, weight: .semibold)).foregroundStyle(INK)
            }
            Text(help)
                .font(.system(size: 14))
                .foregroundStyle(DIM)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 18)
    }

    /// Upload video: two ways in — choose a file (Photos or Files) or
    /// fetch from a link. Its status line reports only on the pick.
    private var uploadView: some View {
        List {
            joinBanner
            Section {
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
                    uploadOption("Choose a video", "From your Photos or Files",
                                 symbol: "square.and.arrow.up")
                }
                .accessibilityLabel("Choose a video")
            } header: {
                Text("Add a lesson video. It is saved as a session and uploaded to Cloud, and the pipeline picks it up like a recording.")
                    .font(.system(size: 15))
                    .foregroundStyle(DIM)
                    .textCase(nil)
                    .padding(.bottom, 6)
            } footer: {
                if !store.status.isEmpty {
                    Text(store.status)
                        .font(.system(size: 14))
                        .foregroundStyle(DIM)
                }
            }
            .listRowBackground(PANEL)
            Section {
                HStack(spacing: 12) {
                    Image(systemName: "link")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(EMBER_INK)
                        .frame(width: 36, height: 36)
                        .background(EMBER_SOFT, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    TextField("Paste a video link…", text: $fetchUrl)
                        .font(.system(size: 16))
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .onSubmit { fetchLink() }
                }
                Button {
                    fetchLink()
                } label: {
                    Label("Fetch from link", systemImage: "arrow.down.circle")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(canFetchLink ? EMBER_INK : DIM)
                }
                .disabled(!canFetchLink)
            } header: {
                Text("Fetch from link — a YouTube or video link, instead of a file")
            }
            Section {
                uploadHistory
            } header: {
                Text("Previous uploads")
            }
            Section {
                uploadFetchHistory
            } header: {
                Text("Previous fetches")
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(BG)
        .navigationTitle("Upload video")
        .navigationBarTitleDisplayMode(.inline)
    }

    /// Previous upload/fetch attempts, like the record screen lists
    /// sessions — an indicator that an upload or fetch occurred.
    private var uploadHistory: some View {
        let ups = store.rows.filter { $0.name.contains("upload_") }
        return Group {
            if ups.isEmpty {
                Text("No uploads yet.")
                    .font(.system(size: 15))
                    .foregroundStyle(DIM)
            } else {
                ForEach(ups) { row in sessionRow(row) }
            }
        }
    }

    private var uploadFetchHistory: some View {
        let attempts = store.cloud.fetchAttempts()
        return Group {
            if attempts.isEmpty {
                Text("No links queued yet.")
                    .font(.system(size: 15))
                    .foregroundStyle(DIM)
            } else {
                ForEach(attempts.indices, id: \.self) { i in
                    let a = attempts[i]
                    VStack(alignment: .leading, spacing: 5) {
                        Text(a.url)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(INK)
                            .lineLimit(1)
                        Text((a.ok ? "Queued ✓" : "Couldn't queue") + " · " + Self.fetchDate(a.date))
                            .font(.system(size: 14))
                            .foregroundStyle(DIM)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    private static let fetchDateFmt: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .short
        f.timeStyle = .short
        return f
    }()

    private static func fetchDate(_ d: Date) -> String { fetchDateFmt.string(from: d) }

    /// The capture screens' note: which session these takes join, with
    /// the way out on the note itself. Absent when nothing is joined.
    @ViewBuilder private var joinBanner: some View {
        if let join = store.joinTo {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Adds a part to **\(join.title ?? join.videoId)** — it joins that session in the hub once uploaded.")
                        .font(.system(size: 15))
                        .foregroundStyle(INK)
                    Button("Make it its own session") { store.joinTo = nil }
                        .buttonStyle(.bordered)
                        .buttonBorderShape(.capsule)
                }
                .padding(.vertical, 4)
            }
            .listRowBackground(SAGE_SOFT)
        }
    }

    /// One row of the Upload screen: ember glyph, title, a line of help.
    private func uploadOption(_ title: String, _ sub: String, symbol: String) -> some View {
        HStack(spacing: 14) {
            Image(systemName: symbol)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(EMBER_INK)
                .frame(width: 44, height: 44)
                .background(EMBER_SOFT, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(INK)
                Text(sub)
                    .font(.system(size: 14))
                    .foregroundStyle(DIM)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(DIM)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }

    private var recordView: some View {
        List {
            joinBanner
            // The viewfinder card: the live preview, the red/quiet
            // banners, and zoom — all in one group.
            Section {
                ZStack(alignment: .bottom) {
                    CameraPreview(engine: engine)
                        .frame(height: wide ? 428 : 300)
                        .background(Color.black)
                    if engine.isRecording {
                        HStack {
                            HStack(spacing: 8) {
                                Circle().fill(Color(hex: "FF5A3C")).frame(width: 11, height: 11)
                                Text("REC\u{00A0}\u{00A0}\(elapsedText)")
                                    .font(.system(size: 16, weight: .bold).monospacedDigit())
                                    .foregroundColor(.white)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(.black.opacity(0.55), in: Capsule())
                            Spacer()
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)

                // A video-only stream must never be silent about being
                // silent: the lesson IS the mentor's words.
                if engine.micWarning {
                    Label("No microphone. The mentor's words won't be recorded — and the mentor's words are the whole point. Check Settings > Privacy > Microphone.", systemImage: "mic.slash.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(.white)
                        .listRowBackground(UWB_RED)
                }

                // Quiet-minute check, mirroring the web app: a full
                // quiet minute raises this banner; speech clears it.
                if engine.speechWarning {
                    Label("Quiet for a while. No speech in the last minute — and the mentor's words are the whole point. Check the mic is close enough.", systemImage: "speaker.slash.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(HONEY)
                        .listRowBackground(HONEY_SOFT)
                }

                // Zoom directly below the viewfinder. Hidden when the
                // camera reports no zoom range, so it is never dead UI.
                if engine.maxZoom > 1.01 {
                    HStack(spacing: 8) {
                        zoomButton("minus", "Zoom out") { engine.nudgeZoom(-0.2) }
                        Slider(value: $zoomProgress, in: 0 ... 100)
                            .tint(BRIGHT)
                            .onChange(of: zoomProgress) { _, new in
                                let max = engine.maxZoom
                                let ratio = 1.0 + Float(new / 100) * (max - 1.0)
                                if abs(ratio - engine.zoom) > 0.02 {
                                    engine.setZoom(ratio)
                                }
                            }
                        zoomButton("plus", "Zoom in") { engine.nudgeZoom(0.2) }
                        Text(String(format: "%.1f×", engine.zoom))
                            .font(.system(size: 14, weight: .semibold).monospacedDigit())
                            .foregroundColor(DIM)
                            .frame(minWidth: 48)
                    }
                    .buttonStyle(.borderless)
                    .listRowBackground(PANEL)
                    .onChange(of: engine.zoom) { _, new in
                        let max = engine.maxZoom
                        if max > 1.0 {
                            let p = Double((new - 1.0) / (max - 1.0) * 100)
                            if abs(p - zoomProgress) > 1 { zoomProgress = p }
                        }
                    }
                }
            }

            // The shutter dock: the shutter centred in a card like a
            // camera app, the status line under it.
            Section {
                VStack(spacing: 10) {
                    shutterButton
                    Text(store.status.isEmpty
                         ? (engine.isRecording ? "Recording — teach the way you'd teach anyway. Tap to stop."
                                               : "Point the camera at the mentor's hands and the work. Press Record, let the lesson happen, press Stop at the end.")
                         : store.status)
                        .font(.system(size: 15))
                        .foregroundStyle(DIM)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                }
                .padding(.vertical, 10)
                .listRowBackground(PANEL)
            }

            // Cloud + device sessions live on the record screen.
            Section {
                // The setter acts only on a real change: toggleCloud()
                // flips persisted state, so a redundant set must never
                // flip it back.
                Toggle(isOn: Binding(get: { store.cloudOn },
                                     set: { on in if on != store.cloudOn { store.toggleCloud() } })) {
                    HStack(spacing: 12) {
                        Image(systemName: store.cloudOn ? "icloud.fill" : "icloud.slash")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(store.cloudOn ? SAGE : DIM)
                            .frame(width: 44, height: 44)
                            .background(store.cloudOn ? SAGE_SOFT : SUNKEN,
                                        in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .contentTransition(.symbolEffect(.replace))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Cloud")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundStyle(INK)
                            Text("Upload a copy for streamed playback")
                                .font(.system(size: 14))
                                .foregroundStyle(DIM)
                        }
                    }
                }
                .tint(SAGE)
                // Export is the offline fallback: only with Cloud off.
                if !store.cloudOn {
                    Button {
                        store.exportSessions()
                    } label: {
                        Label("Export sessions to Downloads", systemImage: "square.and.arrow.up")
                            .foregroundStyle(INK)
                    }
                }
            }
            .listRowBackground(PANEL)

            // This device: a frame of the video, the date and a status
            // chip, then save / share. A List, so the rows' trailing
            // swipe really deletes (and the context menu offers the rest).
            Section {
                if store.rows.isEmpty {
                    ContentUnavailableView {
                        Label("Nothing yet", systemImage: "video")
                    } description: {
                        Text("Sessions you record or upload appear here.")
                    }
                    .foregroundStyle(DIM)
                    .listRowBackground(PANEL)
                } else {
                    ForEach(store.rows) { row in
                        sessionRow(row)
                    }
                    .listRowBackground(PANEL)
                }
            } header: {
                sectionTitle(Text("This device"))
            } footer: {
                Text("Every session is saved on this device, and with Cloud on a copy is uploaded for streamed playback. Tap a session to play it; swipe it, or touch and hold, to share or delete it from the device and the cloud.")
                    .font(.system(size: 13))
                    .foregroundColor(DIM)
            }

            // Build values hide behind a small link at the bottom:
            // shown for debugging, read fresh from the build.
            Section {
                Button {
                    showCloudPanel = true
                } label: {
                    Text("Advanced settings")
                        .font(.system(size: 15))
                        .underline()
                        .foregroundColor(DIM)
                }
            }
            .listRowBackground(Color.clear)
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(BG)
        // A device session plays in a full-screen native player. (It
        // used to play in the viewfinder at the top of this list, which
        // sat off-screen whenever the tapped row was scrolled into view
        // — the video played where nobody could see it.)
        .fullScreenCover(isPresented: Binding(get: { player != nil },
                                              set: { if !$0 { stopLocalPlayback() } })) {
            devicePlayerCover
        }
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

    /// The camera-style shutter: a ring with an ember disc, which
    /// becomes a rounded square while recording. The label keeps the
    /// shared "● Record" / "■ Stop  m:ss" text (assistive tech reads
    /// it, and it is the same contract as the web and Android buttons).
    private var shutterButton: some View {
        Button(action: toggleRecord) {
            ZStack {
                Circle().stroke(RING, lineWidth: 5)
                    .frame(width: 80, height: 80)
                RoundedRectangle(cornerRadius: engine.isRecording ? 9 : 31, style: .continuous)
                    .fill(BRIGHT)
                    .frame(width: engine.isRecording ? 30 : 62,
                           height: engine.isRecording ? 30 : 62)
            }
            .frame(width: 88, height: 88)
            .contentShape(Circle())
            .animation(.spring(response: 0.28, dampingFraction: 0.7), value: engine.isRecording)
        }
        .buttonStyle(SquishStyle())
        .frame(maxWidth: .infinity)
        .accessibilityLabel(engine.isRecording ? "■ Stop  \(elapsedText)" : "● Record")
        .sensoryFeedback(.impact, trigger: engine.isRecording)
    }

    /// Full-screen native playback of a device session: system
    /// transport controls (scrub, AirPlay, picture in picture) and a
    /// close button. The end of the video closes it.
    private var devicePlayerCover: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            if let player {
                VideoPlayer(player: player)
                    .ignoresSafeArea(edges: .bottom)
            }
            Button {
                stopLocalPlayback()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 32))
                    .symbolRenderingMode(.palette)
                    .foregroundStyle(.white, .black.opacity(0.55))
            }
            .padding(16)
            .accessibilityLabel("Close player")
        }
        .preferredColorScheme(.dark)
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
        // A take always ensures a record-capable session (a video left
        // playing in the background would otherwise leave .playback).
        restoreRecordAudioSession()
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
        // The camera rests while a lesson plays, and the sound comes
        // out of the speaker like any video app (the capture session's
        // record-capable audio session would use the earpiece).
        engine.pauseSession()
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        try? AVAudioSession.sharedInstance().setActive(true)
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
    /// published lesson never opens the camera. The progressive MP4 is
    /// preferred (one resource, so the Referer below rides every range
    /// request), then HLS. The Cloud CDN's hotlink protection 403s any
    /// request without the player page as Referer — AVPlayer sends none
    /// by itself, so every stream failed until it was added (the
    /// pipeline fetcher works around it the same way). A stream that
    /// still fails, or no stream URL at all, opens the Cloud embed page
    /// instead (Android's openInBrowser): Play is never a dead button.
    ///
    /// Play runs every part in order: each one's end starts the next
    /// (an untied session is one part and plays as before).
    private func playHubSession(_ whole: HubSession, from: Int = 0) {
        let parts = store.hubParts(whole)
        guard from >= 0 && from < parts.count else { return }
        let p = parts[from]
        var session = HubSession(videoId: p.videoId)
        session.libraryId = p.libraryId ?? whole.libraryId
        session.title = p.title
        session.mp4Url = p.mp4Url
        session.hlsUrl = p.hlsUrl
        let str = (session.mp4Url?.isEmpty == false) ? session.mp4Url : session.hlsUrl
        guard let str, !str.isEmpty, let url = URL(string: str) else {
            openHubEmbed(session, note: "No stream on this hub session yet — opening the Cloud player.")
            return
        }
        stopHubPlayer()
        var headers: [String: String] = [:]
        if let embed = store.hubEmbedUrl(session) { headers["Referer"] = embed }
        let asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        let item = AVPlayerItem(asset: asset)
        hubItemObserver = item.observe(\.status, options: [.new]) { item, _ in
            guard item.status == .failed else { return }
            DispatchQueue.main.async {
                stopHubPlayer()
                openHubEmbed(session, note: "That stream couldn't play here — opening the Cloud player.")
            }
        }
        // A video screen plays through the speaker like any video app;
        // the camera engine's record-capable session would use the earpiece.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        try? AVAudioSession.sharedInstance().setActive(true)
        if from + 1 < parts.count {
            hubEndObserver = NotificationCenter.default.addObserver(
                forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [self] _ in
                playHubSession(whole, from: from + 1)
            }
        }
        hubPlayingPart = from
        if parts.count > 1 { store.status = "Playing part \(from + 1) of \(parts.count)." }
        let player = AVPlayer(playerItem: item)
        hubPlayer = player
        player.play()
    }

    private func openHubEmbed(_ session: HubSession, note: String) {
        if let embed = store.hubEmbedUrl(session), let url = URL(string: embed) {
            store.status = note
            openURL(url)
        } else {
            store.status = "No playable stream on this hub session yet."
        }
    }

    /// Playback leaves a record-capable session behind: both players
    /// set .playback and the capture engine never touches
    /// AVAudioSession, so without this the shared session stays
    /// output-only after any video. (Recording survives today only
    /// because a running AVCaptureSession auto-configures
    /// playAndRecord; any input outside it would find .playback.)
    private func restoreRecordAudioSession() {
        try? AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .videoRecording)
        try? AVAudioSession.sharedInstance().setActive(true)
    }

    private func stopHubPlayer() {
        hubItemObserver?.invalidate()
        hubItemObserver = nil
        if let o = hubEndObserver { NotificationCenter.default.removeObserver(o) }
        hubEndObserver = nil
        hubPlayer?.pause()
        hubPlayer = nil
        restoreRecordAudioSession()
    }

    private func stopLocalPlayback() {
        player?.pause()
        if let o = endObserver {
            NotificationCenter.default.removeObserver(o)
            endObserver = nil
        }
        player = nil
        playingName = nil
        restoreRecordAudioSession()
        // Back from the full-screen player: the camera wakes again (a
        // redundant resume is a no-op; leaving Record parks it itself).
        if onRecordScreen { engine.resumeSession() }
    }

    // ---------- sessions ----------

    /// The row's link state in words, as a chip (the store's text
    /// icons stay the shared contract with Android and the web).
    @ViewBuilder
    private func statusChip(_ row: SessionRow) -> some View {
        switch row.leftIcon {
        case "📱": chip("On this phone", SUNKEN, DIM)
        case "☁↑":
            if case let .progress(pct) = row.rightKind { chip("Uploading \(pct)%", EMBER_SOFT, EMBER_INK) }
            else { chip("Uploading", EMBER_SOFT, EMBER_INK) }
        case "☁…": chip("Preparing", HONEY_SOFT, HONEY)
        case "☁!": chip("Upload failed", EMBER_SOFT, EMBER_INK)
        default: chip("In the cloud", SAGE_SOFT, SAGE)
        }
    }

    private func chip(_ text: String, _ bg: Color, _ fg: Color) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(fg)
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 3)
            .background(bg, in: Capsule())
    }

    /// The store's middle text is "date  •  length"; the row shows the
    /// date as its title and the length on the thumbnail.
    private func dateAndLength(_ row: SessionRow) -> (String, String) {
        let parts = row.middleText.components(separatedBy: "  •  ")
        return (parts.first ?? row.middleText, parts.count > 1 ? parts[1] : "")
    }

    private func sessionRow(_ row: SessionRow) -> some View {
        let (date, length) = dateAndLength(row)
        return HStack(spacing: 12) {
            LessonThumb(url: row.url, length: length, wash: washIndex(row.name),
                        audio: ["m4a", "wav", "mp3"].contains(row.url.pathExtension.lowercased()))
            VStack(alignment: .leading, spacing: 5) {
                Text(date)
                    .font(.system(size: 16, weight: .semibold).monospacedDigit())
                    .foregroundStyle(INK)
                    .lineLimit(1)
                HStack(spacing: 6) {
                    statusChip(row)
                    if let partOf = row.partOf {
                        if row.joined { chip("Part of " + partOf, SAGE_SOFT, SAGE) }
                        else { chip("Joins " + partOf + " after upload", HONEY_SOFT, HONEY) }
                    }
                    // Ignored badge: takes the pipeline operator set
                    // aside never reach the hub.
                    if let reason = row.ignoredReason {
                        chip("Ignored", SUNKEN, DIM)
                            .accessibilityLabel(reason.isEmpty ? "Ignored by the operator" : "Ignored by the operator: \(reason)")
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            // Cloud-linking never removes the on-device download:
            // linked rows keep ↓ next to their cloud action.
            if row.rightKind != .download {
                rowIconButton("arrow.down", "Save a copy") { store.downloadSingle(row.name) }
            }
            rightAction(row)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .onTapGesture { playInViewfinder(row.name) }
        .accessibilityElement(children: .contain)
        .accessibilityHint("Plays the session")
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
            rowIconButton("arrow.down", "Save a copy") { store.downloadSingle(row.name) }
        case .share:
            rowIconButton("square.and.arrow.up", "Share Cloud link", filled: true) { shareCloudLinkFor(row.name) }
        case let .progress(pct):
            // Upload progress as a ring: a sunken track, an ember arc.
            ZStack {
                Circle().stroke(SUNKEN, lineWidth: 4)
                Circle().trim(from: 0, to: CGFloat(pct) / 100)
                    .stroke(BRIGHT, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text("\(pct)%")
                    .font(.system(size: 10, weight: .bold).monospacedDigit())
                    .foregroundStyle(EMBER_INK)
            }
            .frame(width: 36, height: 36)
            .padding(4)
            .accessibilityLabel("Uploading \(pct) percent")
        case .processing:
            ProgressView()
                .tint(HONEY)
                .frame(width: 44, height: 44)
        case .failed:
            rowIconButton("arrow.clockwise", "Retry upload") { store.retryCloud(row.name) }
        }
    }

    // ---------- widgets ----------

    /// A 44pt round icon button; filled ones sit on a sunken disc.
    private func rowIconButton(_ symbol: String, _ label: String, filled: Bool = false,
                               action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(INK)
                .frame(width: 40, height: 40)
                .background(filled ? SUNKEN : Color.clear, in: Circle())
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(label)
    }

    private func zoomButton(_ symbol: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(INK)
                .frame(width: 44, height: 44)
                .background(SUNKEN, in: Circle())
        }
        .accessibilityLabel(label)
    }

    // ---------- cloud settings ----------

    private var cloudSettingsSheet: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Signer URL", value: store.cloud.effSignerUrl())
                    LabeledContent("Signer token",
                                   value: store.cloud.effSignerToken().isEmpty
                                       ? "missing — rebuild the app to stamp one"
                                       : "stamped into this build ✓")
                } header: {
                    Text("Signer")
                } footer: {
                    Text("Build values, shown for debugging — they load fresh from this build and can't be changed here.")
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
        }
        .tint(EMBER_INK)
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
                ScrollView { hubDetailCard(detail).padding(.horizontal, 18).padding(.vertical, 10) }
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

    /// A lesson, listing style: the player (or a warm cover banner
    /// with the lesson's initial), the title and date, an ember Play
    /// pill, the write-up, corrections as quote cards, and chapters as
    /// time chips. Share and Delete live in the toolbar.
    private func hubDetailCard(_ detail: HubSession) -> some View {
        let title = detail.title ?? detail.videoId
        let w = washIndex(title)
        return VStack(alignment: .leading, spacing: 0) {
            if let hubPlayer {
                VideoPlayer(player: hubPlayer)
                    .frame(height: 230)
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .padding(.bottom, 16)
            } else {
                Text(initialOf(title))
                    .font(.system(size: 72, weight: .heavy, design: .rounded))
                    .foregroundStyle(WASH_INK[w])
                    .frame(maxWidth: .infinity)
                    .frame(height: 170)
                    .background(WASH[w], in: RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .accessibilityHidden(true)
                    .padding(.bottom, 16)
            }
            Text(title)
                .font(.system(size: 26, weight: .heavy, design: .rounded))
                .foregroundColor(INK)
            let detailSub = store.hubSubtitle(for: detail)
            if !detailSub.isEmpty {
                Text(detailSub)
                    .font(.system(size: 15))
                    .foregroundColor(DIM)
                    .padding(.top, 2)
            }
            if hubPlayer == nil {
                Button {
                    playHubSession(detail)
                } label: {
                    Label("Play", systemImage: "play.fill")
                        .font(.system(size: 17, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .buttonBorderShape(.capsule)
                .tint(BRIGHT)
                .padding(.top, 16)
            }
            // Share/delete/play outcomes report here, so no action on
            // this screen ever fails silently.
            if !store.status.isEmpty {
                Text(store.status)
                    .font(.system(size: 14))
                    .foregroundColor(DIM)
                    .padding(.top, 10)
            }
            // Parts: each plays on its own or unties; Play above runs
            // them all in order.
            let parts = store.hubParts(detail)
            let multi = parts.count > 1
            let pending = detail.pendingParts ?? 0
            if multi || pending > 0 {
                sectionTitle(Text("Parts")).padding(.top, 18).padding(.bottom, 6)
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(parts.enumerated()), id: \.offset) { i, p in
                        HStack(spacing: 10) {
                            Button {
                                playHubSession(detail, from: i)
                            } label: {
                                Label("Part \(i + 1)", systemImage: "play.fill")
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(EMBER_INK)
                                    .padding(.horizontal, 10).padding(.vertical, 4)
                                    .background(EMBER_SOFT, in: Capsule())
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Play part \(i + 1)")
                            let pd = (p.durationSeconds ?? 0) > 0 ? " \u{2022} " + store.hubDurationText(p.durationSeconds ?? 0) : ""
                            Text((p.title ?? p.videoId) + pd)
                                .font(.system(size: 15))
                                .foregroundColor(INK)
                            Spacer(minLength: 0)
                            if multi {
                                Button("Untie") { pendingUntie = p }
                                    .buttonStyle(.bordered)
                                    .buttonBorderShape(.capsule)
                                    .controlSize(.small)
                            }
                        }
                        .frame(minHeight: 48)
                        if i < parts.count - 1 { Divider().overlay(LINE) }
                    }
                }
                .padding(.horizontal, 14)
                .background(PANEL, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                if pending > 0 {
                    Text("\(pending) more part\(pending > 1 ? "s" : "") still processing — they appear here once the pipeline has written them up.")
                        .font(.system(size: 14))
                        .foregroundColor(DIM)
                        .padding(.top, 8)
                }
            }
            // Continue this session: whatever is recorded, uploaded or
            // fetched next becomes its next part.
            sectionTitle(Text("Add a part")).padding(.top, 18).padding(.bottom, 6)
            HStack(spacing: 8) {
                ForEach([("Record", Route.record), ("Upload", Route.upload)], id: \.0) { name, route in
                    Button {
                        store.joinTo = detail
                        stopHubPlayer()
                        path.append(route)
                    } label: {
                        Text(name).frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .buttonBorderShape(.capsule)
                }
            }
            Button {
                pendingTie = detail
            } label: {
                Text("Tie a session to this one").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .buttonBorderShape(.capsule)
            .padding(.top, 8)
            if let writeup = detail.writeupMd, !writeup.isEmpty {
                Divider().overlay(LINE).padding(.top, 18)
                Text(ContentView.markdown(writeup))
                    .font(.system(size: 17))
                    .foregroundColor(INK)
                    .lineSpacing(5)
                    .textSelection(.enabled)
                    .padding(.top, 16)
            }
            if let corrections = detail.corrections, !corrections.isEmpty {
                sectionTitle(Text("Corrections")).padding(.top, 14).padding(.bottom, 6)
                ForEach(Array(corrections.enumerated()), id: \.offset) { _, c in
                    // A quote card: time chip, the mentor's words, and
                    // what they were correcting.
                    VStack(alignment: .leading, spacing: 8) {
                        chip((multi && (c.part ?? 0) > 0 ? "Part \(c.part ?? 0) \u{00B7} " : "") + (c.start ?? ""), EMBER_SOFT, EMBER_INK)
                        Text("“\(c.quote ?? "")”")
                            .font(.system(size: 16))
                            .foregroundColor(INK)
                        if let fix = c.correcting, !fix.isEmpty {
                            Text("Correcting: \(fix)")
                                .font(.system(size: 14))
                                .foregroundColor(DIM)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(PANEL, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .padding(.bottom, 10)
                }
            }
            if let chapters = detail.chapters, !chapters.isEmpty {
                sectionTitle(Text("Chapters")).padding(.top, 8).padding(.bottom, 6)
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(chapters.enumerated()), id: \.offset) { i, ch in
                        HStack(spacing: 12) {
                            chip((multi && (ch.part ?? 0) > 0 ? "Part \(ch.part ?? 0) \u{00B7} " : "") + (ch.start ?? ""), EMBER_SOFT, EMBER_INK)
                            Text(ch.label ?? "")
                                .font(.system(size: 15))
                                .foregroundColor(INK)
                            Spacer()
                        }
                        .frame(minHeight: 44)
                        if i < chapters.count - 1 { Divider().overlay(LINE) }
                    }
                }
                .padding(.horizontal, 14)
                .background(PANEL, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Write-ups are Markdown; inline styling renders, line breaks stay.
    /// Step screengrabs (![Step N](stills/...)) live in the page, not the
    /// hub: the hub has no still URLs, so they strip out here.
    private static func markdown(_ text: String) -> AttributedString {
        let noImg = text.replacingOccurrences(of: "!\[Step\s+\d+\]\([^)]+\)", with: "", options: .regularExpression)
        let opts = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: noImg, options: opts)) ?? AttributedString(noImg)
    }
}

/// A device session's picture: a frame of the video with its length
/// on it, generated once off the main thread and cached; a warm cover
/// with a video (or mic) symbol until then, or for audio takes.
private struct LessonThumb: View {
    let url: URL
    let length: String
    let wash: Int
    let audio: Bool
    @State private var image: UIImage?
    private static let cache = NSCache<NSURL, UIImage>()

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 56, height: 56)
            } else {
                WASH[wash]
                    .overlay(
                        Image(systemName: audio ? "mic.fill" : "video.fill")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(WASH_INK[wash])
                    )
            }
            if !length.isEmpty {
                Text(length)
                    .font(.system(size: 11, weight: .semibold).monospacedDigit())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(.black.opacity(0.62), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .padding(4)
            }
        }
        .frame(width: 56, height: 56)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityHidden(true)
        .task(id: url) { await load() }
    }

    private func load() async {
        if audio { return }
        if let hit = Self.cache.object(forKey: url as NSURL) { image = hit; return }
        let gen = AVAssetImageGenerator(asset: AVURLAsset(url: url))
        gen.appliesPreferredTrackTransform = true
        gen.maximumSize = CGSize(width: 168, height: 168)
        if let frame = try? await gen.image(at: CMTime(seconds: 1, preferredTimescale: 600)) {
            let ui = UIImage(cgImage: frame.image)
            Self.cache.setObject(ui, forKey: url as NSURL)
            image = ui
        }
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
    weak var engine: CameraEngine?

    override func layoutSubviews() {
        super.layoutSubviews()
        applyInterfaceRotation()
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        applyInterfaceRotation()
    }

    /// The iPhone is portrait-only (90, the default). The iPad turns
    /// every way: the viewfinder and the take follow the screen, so
    /// what you see upright is what is filmed upright.
    private func applyInterfaceRotation() {
        guard UIDevice.current.userInterfaceIdiom == .pad,
              let orientation = window?.windowScene?.effectiveGeometry.interfaceOrientation
        else { return }
        let angle: CGFloat
        switch orientation {
        case .portraitUpsideDown: angle = 270
        case .landscapeLeft: angle = 180
        case .landscapeRight: angle = 0
        default: angle = 90
        }
        if let connection = previewLayer.connection,
           connection.isVideoRotationAngleSupported(angle) {
            connection.videoRotationAngle = angle
        }
        engine?.setInterfaceRotation(angle)
    }
}

struct CameraPreview: UIViewRepresentable {
    let engine: CameraEngine

    func makeUIView(context: Context) -> PreviewUIView {
        let view = PreviewUIView()
        view.backgroundColor = .black
        view.engine = engine
        engine.attachPreview(view.previewLayer)
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {}
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
