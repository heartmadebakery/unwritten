import AVFoundation
import UIKit

/// Careful AVFoundation wrapper for the iPhone base device (and anything
/// at or above its iOS 17 baseline). Mirrors Android's CameraEngine:
/// hardware-encoded video (720p H.264) + audio (AAC) via a single
/// movie-file output, a video-only fallback when the microphone is
/// denied, zoom against the device's reported range, and an optional
/// native luma listener (uwcore, ≤10 fps) that the UI leaves detached.
///
/// All session work runs on a single serial queue; no public method
/// throws — failures surface through `statusHandler` and never crash.
final class CameraEngine: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var micWarning = false
    @Published var speechWarning = false
    @Published var cameraDenied = false
    @Published var maxZoom: Float = 1.0
    @Published var zoom: Float = 1.0
    @Published var isFront = false
    @Published var sessionRunning = false

    /// Status lines for the on-screen status text. Always called on main.
    var statusHandler: ((String) -> Void)?
    /// Called on main when a recording finishes: the temp .mov URL, or
    /// nil when nothing usable was captured (the message went to
    /// `statusHandler` instead — takes are never lost silently).
    var recordingFinishedHandler: ((URL?) -> Void)?

    private let session = AVCaptureSession()
    private let sessionQueue = DispatchQueue(label: "org.tinio.unwritten.cam")
    private let lumaQueue = DispatchQueue(label: "org.tinio.unwritten.luma")
    private let audioQueue = DispatchQueue(label: "org.tinio.unwritten.audio")
    private let movieOutput = AVCaptureMovieFileOutput()
    private var videoDataOutput: AVCaptureVideoDataOutput?
    private var audioDataOutput: AVCaptureAudioDataOutput?
    private var lastSpeechMs: Int64 = 0
    private var lastSpeechCheckMs: Int64 = 0
    private var videoDevice: AVCaptureDevice?
    private var lumaListener: ((Double, [Double]) -> Void)?
    private var lastLumaMs: Int64 = 0

    private func onMain(_ work: @escaping () -> Void) {
        if Thread.isMainThread { work() } else { DispatchQueue.main.async(execute: work) }
    }

    private func report(_ message: String) {
        onMain { [weak self] in self?.statusHandler?(message) }
    }

    /// Diagnostic logging (stderr + syslog + stdout) so a capture
    /// failure can be read off the device console. Mirrors Android's
    /// "UWCloud" Log usage; prefixed [UWCam] and never user-visible.
    func diag(_ message: String) {
        let line = "[UWCam] \(message)\n"
        FileHandle.standardError.write(line.data(using: .utf8)!)
        print(line, terminator: "")
        NSLog("%@", line)
    }

    // ---------- preview ----------

    func makePreviewLayer() -> AVCaptureVideoPreviewLayer {
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        return layer
    }

    /// Binds a SwiftUI-hosted preview layer to this engine's session.
    func attachPreview(_ layer: AVCaptureVideoPreviewLayer) {
        layer.session = session
        layer.videoGravity = .resizeAspectFill
    }

    // ---------- setup ----------

    func requestAccessAndConfigure() {
        AVCaptureDevice.requestAccess(for: .video) { [weak self] videoGranted in
            guard let self else { return }
            if !videoGranted {
                self.onMain { self.cameraDenied = true }
                self.report("Camera access is off — enable it in Settings to record.")
                return
            }
            AVAudioApplication.requestRecordPermission { [weak self] _ in
                // The mic answer only decides audio vs video-only; either
                // way the session is configured below.
                self?.configureSession()
            }
        }
    }

    private func micGranted() -> Bool {
        AVAudioApplication.shared.recordPermission == .granted
    }

    private var observersInstalled = false

    private func installSessionObservers() {
        if observersInstalled { return }
        observersInstalled = true
        let nc = NotificationCenter.default
        nc.addObserver(forName: .AVCaptureSessionRuntimeError, object: session, queue: nil) { [weak self] note in
            let err = note.userInfo?[AVCaptureSessionErrorKey] as? AVError
            self?.diag("SESSION RUNTIME ERROR: \(err?.localizedDescription ?? "\(note.userInfo ?? [:])")")
        }
        nc.addObserver(forName: .AVCaptureSessionDidStartRunning, object: session, queue: nil) { [weak self] _ in
            self?.diag("SESSION DID START RUNNING")
        }
        nc.addObserver(forName: .AVCaptureSessionWasInterrupted, object: session, queue: nil) { [weak self] note in
            self?.diag("SESSION INTERRUPTED: \(note.userInfo ?? [:])")
        }
        nc.addObserver(forName: .AVCaptureSessionInterruptionEnded, object: session, queue: nil) { [weak self] _ in
            self?.diag("SESSION INTERRUPTION ENDED")
            self?.resumeSession()
        }
    }

    private func configureSession() {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            self.installSessionObservers()
            self.session.beginConfiguration()
            if self.session.canSetSessionPreset(.hd1280x720) {
                self.session.sessionPreset = .hd1280x720
            }
            self.attachInputsLocked(front: self.isFront)
            // No inputs (no camera, as in the simulator): starting the
            // session would throw an uncatchable exception, so stop here.
            // attachInputsLocked already reported the reason on screen.
            self.diag("configure: inputs=\(self.session.inputs.count) videoDevice=\(self.videoDevice?.localizedName ?? "nil") outputsBefore=\(self.session.outputs.count)")
            let hasInputs = !self.session.inputs.isEmpty
            var outputFailed = false
            if hasInputs && !self.session.outputs.contains(self.movieOutput) {
                if self.session.canAddOutput(self.movieOutput) {
                    self.session.addOutput(self.movieOutput)
                } else {
                    outputFailed = true
                }
            }
            // Audio tap for the quiet-minute check: observing levels never
            // alters the recorded take. Absent when unsupported — then the
            // banner simply never appears.
            if self.audioDataOutput == nil {
                let audioOut = AVCaptureAudioDataOutput()
                audioOut.setSampleBufferDelegate(self, queue: self.audioQueue)
                if self.session.canAddOutput(audioOut) {
                    self.session.addOutput(audioOut)
                    self.audioDataOutput = audioOut
                }
            }
            // startRunning may NOT be called between beginConfiguration
            // and commitConfiguration (it throws NSGenericException) —
            // commit first, then start.
            self.session.commitConfiguration()
            guard hasInputs else { return }
            if outputFailed {
                self.report("Camera error: could not add the movie output.")
                return
            }
            self.refreshZoomLocked()
            // startRunning can throw (uncaught in Swift) in exotic states;
            // the bridge starts it behind an ObjC exception handler.
            if !UWStartCaptureSession(self.session) {
                self.diag("startRunning failed; isRunning=\(self.session.isRunning)")
                self.report("Camera error: could not start the camera.")
                return
            }
            self.diag("startRunning ok; isRunning=\(self.session.isRunning)")
            self.onMain { self.sessionRunning = true }
        }
    }

    private func attachInputsLocked(front: Bool) {
        for input in session.inputs { session.removeInput(input) }
        let position: AVCaptureDevice.Position = front ? .front : .back
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: position),
              let videoInput = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(videoInput) else {
            report("Camera error: no \(front ? "front" : "back") camera found.")
            return
        }
        session.addInput(videoInput)
        videoDevice = device
        if micGranted() {
            if let mic = AVCaptureDevice.default(for: .audio),
               let audioInput = try? AVCaptureDeviceInput(device: mic),
               session.canAddInput(audioInput) {
                session.addInput(audioInput)
            }
            onMain { [weak self] in self?.micWarning = false }
        } else {
            // A denied/busy microphone must not cost the video too — but
            // a video-only take must never be silent about being silent:
            // the lesson IS the mentor's words.
            onMain { [weak self] in self?.micWarning = true }
        }
    }

    func switchCamera() {
        if movieOutput.isRecording { return }
        let next = !isFront
        onMain { [weak self] in self?.isFront = next }
        sessionQueue.async { [weak self] in
            guard let self else { return }
            // A take may have started after the caller-thread check —
            // re-check on the queue before swapping inputs mid-take.
            if self.movieOutput.isRecording {
                self.onMain { [weak self] in self?.isFront = !next }
                return
            }
            self.session.beginConfiguration()
            defer { self.session.commitConfiguration() }
            self.attachInputsLocked(front: next)
            self.refreshZoomLocked()
        }
    }

    /// Stops the capture session when the app backgrounds (the view
    /// stops any take first, so the take is kept). Restart with
    /// resumeSession() — without this pair the camera runs behind
    /// the app's back with no resume path.
    func pauseSession() {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if self.session.isRunning { self.session.stopRunning() }
            self.onMain { self.sessionRunning = false }
        }
    }

    /// Restarts a paused session. Safe to call redundantly: running
    /// and input-less sessions are left alone.
    func resumeSession() {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if self.session.isRunning || self.session.inputs.isEmpty { return }
            if UWStartCaptureSession(self.session) {
                self.onMain { self.sessionRunning = true }
            } else {
                self.diag("resumeSession failed; isRunning=\(self.session.isRunning)")
            }
        }
    }

    /// Re-checks permissions when the app returns to the foreground:
    /// granting access in Settings then returning unblocks Record
    /// (or lifts video-only) without a relaunch.
    func refreshPermissions() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            onMain { [weak self] in self?.cameraDenied = false }
            sessionQueue.async { [weak self] in
                guard let self else { return }
                if !self.session.isRunning && self.session.inputs.isEmpty {
                    self.configureSession()
                } else if !self.movieOutput.isRecording {
                    // A newly-granted mic joins outside a take; a live
                    // take keeps the inputs it started with.
                    self.session.beginConfiguration()
                    self.attachInputsLocked(front: self.isFront)
                    self.session.commitConfiguration()
                }
            }
        case .denied, .restricted:
            onMain { [weak self] in self?.cameraDenied = true }
        case .notDetermined:
            break // the launch-time prompt flow owns this case
        @unknown default:
            break
        }
    }

    // ---------- zoom ----------

    private func refreshZoomLocked() {
        guard let device = videoDevice else { return }
        let max = Float(device.maxAvailableVideoZoomFactor)
        let clamped = max > 1.0 ? max : 1.0
        onMain { [weak self] in
            self?.maxZoom = clamped
            self?.zoom = 1.0
        }
    }

    func setZoom(_ ratio: Float) {
        sessionQueue.async { [weak self] in
            guard let self, let device = self.videoDevice else { return }
            let max = Float(device.maxAvailableVideoZoomFactor)
            let clamped = min(max > 1.0 ? max : 1.0, Swift.max(1.0, ratio))
            do {
                try device.lockForConfiguration()
                device.videoZoomFactor = CGFloat(clamped)
                device.unlockForConfiguration()
                self.onMain { self.zoom = clamped }
            } catch {
                self.report("Zoom failed: \(error.localizedDescription)")
            }
        }
    }

    func nudgeZoom(_ delta: Float) {
        setZoom(zoom + delta)
    }

    // ---------- recording ----------

    /// Records to a temp .mov; the finished file arrives through
    /// `recordingFinishedHandler` for the remux-to-.mp4 step.
    func startVideo(to tempURL: URL) {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if self.movieOutput.isRecording {
                self.report("Already recording.")
                return
            }
            self.diag("startVideo: isRunning=\(self.session.isRunning) isRecording=\(self.movieOutput.isRecording)")
            guard self.session.isRunning else {
                self.report("Camera not ready yet — try again in a moment.")
                return
            }
            try? FileManager.default.removeItem(at: tempURL)
            if let connection = self.movieOutput.connection(with: .video) {
                // Portrait recording (90° rotation, like .portrait).
                if connection.isVideoRotationAngleSupported(90) {
                    connection.videoRotationAngle = 90
                }
            }
            self.movieOutput.startRecording(to: tempURL, recordingDelegate: self)
        }
    }

    func stopVideo() {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if self.movieOutput.isRecording { self.movieOutput.stopRecording() }
        }
    }

    // ---------- native luma (uwcore, retained) ----------

    /// Attaches the per-frame luma analysis (mean + 8x8 grid, ≤10 fps).
    /// Passing nil detaches it. The app UI leaves this detached —
    /// it exists so the native core stays linked and exercised, exactly
    /// like Android's setLumaListener.
    func setLumaListener(_ listener: ((Double, [Double]) -> Void)?) {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if self.movieOutput.isRecording {
                self.report("Luma listener changes are for between takes.")
                return
            }
            self.lumaListener = listener
            self.session.beginConfiguration()
            defer { self.session.commitConfiguration() }
            if let existing = self.videoDataOutput {
                self.session.removeOutput(existing)
                self.videoDataOutput = nil
            }
            guard listener != nil else { return }
            let output = AVCaptureVideoDataOutput()
            output.videoSettings = [
                kCVPixelBufferPixelFormatTypeKey as String:
                    kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
            ]
            output.alwaysDiscardsLateVideoFrames = true
            output.setSampleBufferDelegate(self, queue: self.lumaQueue)
            if self.session.canAddOutput(output) {
                self.session.addOutput(output)
                self.videoDataOutput = output
            } else {
                self.report("Camera error: could not add the luma output.")
            }
        }
    }
}

// MARK: - AVCaptureFileOutputRecordingDelegate

extension CameraEngine: AVCaptureFileOutputRecordingDelegate {
    func fileOutput(_ output: AVCaptureFileOutput, didStartRecordingTo fileURL: URL,
                    from connections: [AVCaptureConnection]) {
        onMain { [weak self] in
            self?.isRecording = true
            self?.speechWarning = false
            self?.lastSpeechMs = Int64(Date().timeIntervalSince1970 * 1000)
            self?.lastSpeechCheckMs = 0
            UIApplication.shared.isIdleTimerDisabled = true
        }
    }

    func fileOutput(_ output: AVCaptureFileOutput, didFinishRecordingTo outputFileURL: URL,
                    from connections: [AVCaptureConnection], error: Error?) {
        onMain { [weak self] in
            guard let self else { return }
            self.isRecording = false
            self.speechWarning = false
            UIApplication.shared.isIdleTimerDisabled = false
            if let error {
                let ns = error as NSError
                // Stopping a sub-second take surfaces as a spurious
                // error with a usable file — keep the file anyway.
                let size = (try? FileManager.default.attributesOfItem(atPath: outputFileURL.path)[.size] as? Int64) ?? 0
                if size > 0 {
                    self.recordingFinishedHandler?(outputFileURL)
                } else {
                    self.statusHandler?("Recording failed: \(ns.localizedDescription)")
                    self.recordingFinishedHandler?(nil)
                }
                return
            }
            self.recordingFinishedHandler?(outputFileURL)
        }
    }
}

// MARK: - sample-buffer delegates (luma + mic level)

extension CameraEngine: AVCaptureVideoDataOutputSampleBufferDelegate, AVCaptureAudioDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        if output === audioDataOutput { handleAudio(sampleBuffer); return }
        guard let listener = lumaListener,
              let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        if nowMs - lastLumaMs < 100 { return } // ≤10 fps, like Android
        lastLumaMs = nowMs
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) else { return }
        let w = CVPixelBufferGetWidthOfPlane(pixelBuffer, 0)
        let h = CVPixelBufferGetHeightOfPlane(pixelBuffer, 0)
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
        var grid = [Double](repeating: 0, count: 64)
        let y = base.assumingMemoryBound(to: UInt8.self)
        let mean = grid.withUnsafeMutableBufferPointer { buf in
            UWComputeLumaMean(y, Int32(w), Int32(h), Int32(stride), buf.baseAddress)
        }
        let gridCopy = grid
        onMain { listener(mean, gridCopy) }
    }

    // Quiet-minute check, mirroring the web app: capture RMS is
    // evaluated while recording, and a full quiet minute raises the
    // speech banner. The tap only observes — never touches the take.
    private func handleAudio(_ sampleBuffer: CMSampleBuffer) {
        guard movieOutput.isRecording else { return }
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        if nowMs - lastSpeechCheckMs < 2000 { return } // poll like the web
        lastSpeechCheckMs = nowMs
        let rms = Self.captureRms(of: sampleBuffer)
        if rms < 0 { return } // unknown format; stay silent, not wrong
        if rms > 0.008 {
            lastSpeechMs = nowMs
            onMain { [weak self] in self?.speechWarning = false }
        } else if nowMs - lastSpeechMs > 60000 {
            onMain { [weak self] in self?.speechWarning = true }
        }
    }

    /// RMS level (0..1) of the buffer's first channel, or -1 for formats
    /// this tap does not understand. Linear PCM int16/float only.
    static func captureRms(of sampleBuffer: CMSampleBuffer) -> Double {
        guard let block = CMSampleBufferGetDataBuffer(sampleBuffer),
              let fmt = CMSampleBufferGetFormatDescription(sampleBuffer),
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmt)?.pointee,
              asbd.mFormatID == kAudioFormatLinearPCM,
              asbd.mChannelsPerFrame > 0,
              (asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved) == 0 else { return -1 }
        var length = 0
        var data: UnsafeMutablePointer<Int8>?
        guard CMBlockBufferGetDataPointer(block, atOffset: 0, lengthAtOffsetOut: nil,
                                          totalLengthOut: &length, dataPointerOut: &data) == noErr,
              let bytes = data, length > 0 else { return -1 }
        let channels = Int(asbd.mChannelsPerFrame)
        let raw = UnsafeRawPointer(bytes)
        let isFloat = (asbd.mFormatFlags & kAudioFormatFlagIsFloat) != 0
        let bigEndian = (asbd.mFormatFlags & kAudioFormatFlagIsBigEndian) != 0
        let bytesPerSample: Int
        if isFloat && asbd.mBitsPerChannel == 32 { bytesPerSample = 4 }
        else if !isFloat && asbd.mBitsPerChannel == 16 { bytesPerSample = 2 }
        else { return -1 }
        let frames = length / (bytesPerSample * channels)
        guard frames > 0 else { return -1 }
        var sum = 0.0
        for i in 0 ..< frames {
            let v: Double
            if isFloat {
                v = Double(raw.load(fromByteOffset: i * channels * 4, as: Float32.self))
            } else {
                var s: Int16 = raw.load(fromByteOffset: i * channels * 2, as: Int16.self)
                if bigEndian { s = Int16(bigEndian: s) }
                v = Double(s) / 32768.0
            }
            sum += v * v
        }
        return (sum / Double(frames)).squareRoot()
    }
}
