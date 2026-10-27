#pragma once

#include <aaudio/AAudio.h>

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace uwcore {

// ---------------------------------------------------------------------------
// WavRecorder
// ---------------------------------------------------------------------------
class WavRecorder {
public:
    WavRecorder();
    ~WavRecorder();

    WavRecorder(const WavRecorder&) = delete;
    WavRecorder& operator=(const WavRecorder&) = delete;

    // Opens an AAudio input stream and starts recording to path.
    // Returns true on success, false on any failure (no crash, no leak).
    bool Start(const std::string& path);

    // Stops the stream, joins the writer thread and patches the WAV header.
    // Returns true on success, false if not recording or on failure.
    bool Stop();

    bool IsRecording() const { return recording_.load(); }

    // Running RMS over written (post-conversion, post-decimation) samples, 0..1.
    double GetRms() const;

    // Duration of written audio in milliseconds.
    int64_t GetDurationMs() const;

    int GetStreamSampleRate() const { return streamRate_; }
    int GetOutputSampleRate() const { return outputRate_; }
    int GetChannelCount() const { return channels_; }

    // Internal: called from the AAudio data callback. Do not call directly.
    aaudio_data_callback_result_t OnAudioData(void* audioData, int32_t numFrames);

private:
    void WriterLoop();
    bool WriteHeaderPlaceholder();
    bool PatchHeader();
    void CleanupStreamLocked();
    void CloseFileLocked();

    AAudioStream* stream_;
    std::FILE* file_;

    int streamRate_;
    int outputRate_;
    int channels_;
    int decimationFactor_;
    int decimationPhase_;

    std::atomic<bool> recording_;
    std::atomic<bool> stopRequested_;
    std::atomic<int64_t> framesWritten_;

    mutable std::mutex statsMutex_;
    double sumSquares_;
    int64_t samplesWritten_;

    // Ring buffer (interleaved int16 samples).
    std::vector<int16_t> ring_;
    size_t ringHead_;
    size_t ringTail_;
    size_t ringCount_;
    std::mutex ringMutex_;
    std::condition_variable ringCv_;

    std::thread writerThread_;
    std::mutex stateMutex_;
};

// ---------------------------------------------------------------------------
// Luma analysis (pure C++)
// ---------------------------------------------------------------------------

// Computes overall mean (0..255) and an 8x8 grid of cell means.
// y: pointer to Y plane, rowStride in bytes (>= w).
// Returns true on success, false on invalid arguments.
bool ComputeLumaStats(const uint8_t* y, int w, int h, int rowStride,
                      double* meanOut, double gridOut[64]);

class FlashDetector {
public:
    FlashDetector();
    void Reset();

    // Returns true exactly once per flash event, subject to a
    // 1000 ms refractory period after a trigger.
    bool Feed(double mean, int64_t nowMs);

    double GetBaseline() const { return baseline_; }

private:
    bool seeded_;
    double baseline_;
    bool hasTriggered_;
    int64_t lastTriggerMs_;
};

}  // namespace uwcore
