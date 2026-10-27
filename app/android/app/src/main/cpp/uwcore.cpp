#include "uwcore.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace uwcore {
namespace {

constexpr size_t kRingCapacitySamples = 65536;
constexpr int kTargetRate = 16000;

void WriteU16LE(std::FILE* fp, uint16_t v) {
    uint8_t b[2];
    b[0] = static_cast<uint8_t>(v & 0xFFu);
    b[1] = static_cast<uint8_t>((v >> 8) & 0xFFu);
    std::fwrite(b, 1, 2, fp);
}

void WriteU32LE(std::FILE* fp, uint32_t v) {
    uint8_t b[4];
    b[0] = static_cast<uint8_t>(v & 0xFFu);
    b[1] = static_cast<uint8_t>((v >> 8) & 0xFFu);
    b[2] = static_cast<uint8_t>((v >> 16) & 0xFFu);
    b[3] = static_cast<uint8_t>((v >> 24) & 0xFFu);
    std::fwrite(b, 1, 4, fp);
}

// Canonical 44-byte PCM WAV header, mono, 16-bit.
void WriteWavHeader(std::FILE* fp, int32_t sampleRate, uint32_t dataBytes) {
    if (fp == nullptr) return;
    std::fseek(fp, 0, SEEK_SET);
    std::fwrite("RIFF", 1, 4, fp);
    WriteU32LE(fp, 36u + dataBytes);
    std::fwrite("WAVE", 1, 4, fp);
    std::fwrite("fmt ", 1, 4, fp);
    WriteU32LE(fp, 16u);
    WriteU16LE(fp, 1u);      // PCM
    WriteU16LE(fp, 1u);      // mono
    WriteU32LE(fp, static_cast<uint32_t>(sampleRate));
    WriteU32LE(fp, static_cast<uint32_t>(sampleRate * 2));  // byte rate
    WriteU16LE(fp, 2u);      // block align
    WriteU16LE(fp, 16u);     // bits per sample
    std::fwrite("data", 1, 4, fp);
    WriteU32LE(fp, dataBytes);
}

aaudio_data_callback_result_t DataCallback(AAudioStream* /*stream*/,
                                           void* userData,
                                           void* audioData,
                                           int32_t numFrames) {
    if (userData == nullptr || audioData == nullptr || numFrames <= 0) {
        return AAUDIO_CALLBACK_RESULT_CONTINUE;
    }
    auto* self = static_cast<WavRecorder*>(userData);
    return self->OnAudioData(audioData, numFrames);
}

void ErrorCallback(AAudioStream* /*stream*/, void* /*userData*/,
                   aaudio_result_t /*error*/) {
    // Recording failure is surfaced via Start/Stop return values and
    // stream state; nothing safe to do here beyond not crashing.
}

}  // namespace

// ---------------------------------------------------------------------------
// WavRecorder
// ---------------------------------------------------------------------------

WavRecorder::WavRecorder()
    : stream_(nullptr),
      file_(nullptr),
      streamRate_(0),
      outputRate_(kTargetRate),
      channels_(1),
      decimationFactor_(1),
      decimationPhase_(0),
      recording_(false),
      stopRequested_(false),
      framesWritten_(0),
      sumSquares_(0.0),
      samplesWritten_(0),
      ringHead_(0),
      ringTail_(0),
      ringCount_(0) {
    ring_.assign(kRingCapacitySamples, 0);
}

WavRecorder::~WavRecorder() {
    try {
        if (recording_.load()) {
            Stop();
        } else {
            // Ensure thread/stream/file are not leaked if Stop was
            // partially completed.
            stopRequested_.store(true);
            ringCv_.notify_all();
            if (writerThread_.joinable()) {
                writerThread_.join();
            }
            if (stream_ != nullptr) {
                AAudioStream_close(stream_);
                stream_ = nullptr;
            }
            if (file_ != nullptr) {
                std::fclose(file_);
                file_ = nullptr;
            }
        }
    } catch (...) {
        // Destructor must never throw.
    }
}

aaudio_data_callback_result_t WavRecorder::OnAudioData(void* audioData,
                                                       int32_t numFrames) {
    if (stopRequested_.load()) {
        return AAUDIO_CALLBACK_RESULT_STOP;
    }
    if (audioData == nullptr || numFrames <= 0 || channels_ <= 0) {
        return AAUDIO_CALLBACK_RESULT_CONTINUE;
    }
    const auto* src = static_cast<const int16_t*>(audioData);
    const size_t totalSamples =
            static_cast<size_t>(numFrames) * static_cast<size_t>(channels_);
    {
        std::lock_guard<std::mutex> lock(ringMutex_);
        for (size_t i = 0; i < totalSamples; ++i) {
            if (ringCount_ >= ring_.size()) {
                // Ring full: drop incoming sample rather than block
                // the realtime audio callback.
                break;
            }
            ring_[ringTail_] = src[i];
            ringTail_ = (ringTail_ + 1) % ring_.size();
            ++ringCount_;
        }
    }
    ringCv_.notify_one();
    return AAUDIO_CALLBACK_RESULT_CONTINUE;
}

bool WavRecorder::WriteHeaderPlaceholder() {
    if (file_ == nullptr) return false;
    WriteWavHeader(file_, outputRate_, 0);
    std::fflush(file_);
    return std::fseek(file_, 44, SEEK_SET) == 0;
}

bool WavRecorder::PatchHeader() {
    if (file_ == nullptr) return false;
    std::fflush(file_);
    const int64_t frames = framesWritten_.load();
    const uint32_t dataBytes =
            static_cast<uint32_t>(frames > 0 ? frames * 2 : 0);
    const int rate = outputRate_ > 0 ? outputRate_ : kTargetRate;
    WriteWavHeader(file_, rate, dataBytes);
    std::fflush(file_);
    return true;
}

void WavRecorder::CleanupStreamLocked() {
    if (stream_ != nullptr) {
        AAudioStream_close(stream_);
        stream_ = nullptr;
    }
}

void WavRecorder::CloseFileLocked() {
    if (file_ != nullptr) {
        std::fclose(file_);
        file_ = nullptr;
    }
}

bool WavRecorder::Start(const std::string& path) {
    try {
        std::lock_guard<std::mutex> stateLock(stateMutex_);
        if (recording_.load()) {
            return false;
        }
        if (path.empty()) {
            return false;
        }

        // Reset state.
        stopRequested_.store(false);
        framesWritten_.store(0);
        decimationPhase_ = 0;
        streamRate_ = 0;
        outputRate_ = kTargetRate;
        channels_ = 1;
        decimationFactor_ = 1;
        {
            std::lock_guard<std::mutex> lock(statsMutex_);
            sumSquares_ = 0.0;
            samplesWritten_ = 0;
        }
        {
            std::lock_guard<std::mutex> lock(ringMutex_);
            ringHead_ = 0;
            ringTail_ = 0;
            ringCount_ = 0;
        }

        file_ = std::fopen(path.c_str(), "wb");
        if (file_ == nullptr) {
            return false;
        }
        // Placeholder header; real rate patched once stream is known,
        // and again on Stop with real sizes.
        outputRate_ = kTargetRate;
        if (!WriteHeaderPlaceholder()) {
            CloseFileLocked();
            return false;
        }

        AAudioStreamBuilder* builder = nullptr;
        aaudio_result_t result = AAudio_createStreamBuilder(&builder);
        if (result != AAUDIO_OK || builder == nullptr) {
            CloseFileLocked();
            return false;
        }

        AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_INPUT);
        AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_I16);
        AAudioStreamBuilder_setChannelCount(builder, 1);
        AAudioStreamBuilder_setSampleRate(builder, 48000);
        AAudioStreamBuilder_setDataCallback(builder, DataCallback, this);
        AAudioStreamBuilder_setErrorCallback(builder, ErrorCallback, this);
        AAudioStreamBuilder_setPerformanceMode(
                builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
        AAudioStreamBuilder_setSharingMode(builder, AAUDIO_SHARING_MODE_SHARED);
        /* AAudioStreamBuilder_setInputPreset needs API 28; we target 26
           (Pixel 2). The preset is only a hint — GENERIC is the default. */

        result = AAudioStreamBuilder_openStream(builder, &stream_);
        AAudioStreamBuilder_delete(builder);
        builder = nullptr;

        if (result != AAUDIO_OK || stream_ == nullptr) {
            stream_ = nullptr;
            CloseFileLocked();
            return false;
        }

        streamRate_ = AAudioStream_getSampleRate(stream_);
        channels_ = AAudioStream_getChannelCount(stream_);
        if (streamRate_ <= 0) {
            streamRate_ = 48000;
        }
        if (channels_ <= 0) {
            channels_ = 1;
        }

        if (streamRate_ >= kTargetRate &&
            (streamRate_ % kTargetRate) == 0) {
            decimationFactor_ = streamRate_ / kTargetRate;
            outputRate_ = kTargetRate;
        } else {
            decimationFactor_ = 1;
            outputRate_ = streamRate_;
        }
        if (decimationFactor_ < 1) {
            decimationFactor_ = 1;
            outputRate_ = streamRate_;
        }

        // Rewrite placeholder with the actual output rate.
        if (!WriteHeaderPlaceholder()) {
            CleanupStreamLocked();
            CloseFileLocked();
            return false;
        }

        recording_.store(true);
        try {
            writerThread_ = std::thread(&WavRecorder::WriterLoop, this);
        } catch (...) {
            recording_.store(false);
            CleanupStreamLocked();
            CloseFileLocked();
            return false;
        }

        result = AAudioStream_requestStart(stream_);
        if (result != AAUDIO_OK) {
            stopRequested_.store(true);
            ringCv_.notify_all();
            if (writerThread_.joinable()) {
                writerThread_.join();
            }
            recording_.store(false);
            CleanupStreamLocked();
            CloseFileLocked();
            return false;
        }

        return true;
    } catch (...) {
        // No exceptions escape; attempt best-effort cleanup.
        try {
            stopRequested_.store(true);
            ringCv_.notify_all();
            if (writerThread_.joinable()) {
                writerThread_.join();
            }
        } catch (...) {
        }
        recording_.store(false);
        if (stream_ != nullptr) {
            AAudioStream_close(stream_);
            stream_ = nullptr;
        }
        if (file_ != nullptr) {
            std::fclose(file_);
            file_ = nullptr;
        }
        return false;
    }
}

void WavRecorder::WriterLoop() {
    std::vector<int16_t> chunk;
    chunk.reserve(4096);
    std::vector<int16_t> out;
    out.reserve(2048);

    while (true) {
        chunk.clear();
        {
            std::unique_lock<std::mutex> lock(ringMutex_);
            ringCv_.wait(lock, [this] {
                return ringCount_ > 0 || stopRequested_.load();
            });
            if (ringCount_ == 0 && stopRequested_.load()) {
                break;
            }
            const size_t toCopy = std::min<size_t>(ringCount_, 4096);
            chunk.resize(toCopy);
            for (size_t i = 0; i < toCopy; ++i) {
                chunk[i] = ring_[ringHead_];
                ringHead_ = (ringHead_ + 1) % ring_.size();
                --ringCount_;
            }
        }

        if (chunk.empty()) {
            if (stopRequested_.load()) {
                // Check once more for drained data.
                std::lock_guard<std::mutex> lock(ringMutex_);
                if (ringCount_ == 0) break;
            }
            continue;
        }

        out.clear();
        const int ch = channels_ > 0 ? channels_ : 1;
        const size_t frames = chunk.size() / static_cast<size_t>(ch);
        double localSumSq = 0.0;
        int64_t localCount = 0;

        for (size_t f = 0; f < frames; ++f) {
            int32_t acc = 0;
            for (int c = 0; c < ch; ++c) {
                acc += static_cast<int32_t>(chunk[f * static_cast<size_t>(ch) +
                                                  static_cast<size_t>(c)]);
            }
            const int16_t mono = static_cast<int16_t>(acc / ch);

            if (decimationFactor_ <= 1) {
                out.push_back(mono);
            } else {
                if (decimationPhase_ == 0) {
                    out.push_back(mono);
                }
                decimationPhase_++;
                if (decimationPhase_ >= decimationFactor_) {
                    decimationPhase_ = 0;
                }
            }
        }

        if (!out.empty() && file_ != nullptr) {
            std::fwrite(out.data(), sizeof(int16_t), out.size(), file_);
            for (int16_t s : out) {
                const double d = static_cast<double>(s);
                localSumSq += d * d;
                ++localCount;
            }
            framesWritten_.fetch_add(static_cast<int64_t>(out.size()));
            std::lock_guard<std::mutex> lock(statsMutex_);
            sumSquares_ += localSumSq;
            samplesWritten_ += localCount;
        }
    }
}

bool WavRecorder::Stop() {
    try {
        std::lock_guard<std::mutex> stateLock(stateMutex_);
        if (!recording_.load()) {
            return false;
        }

        stopRequested_.store(true);
        ringCv_.notify_all();

        bool ok = true;
        if (stream_ != nullptr) {
            aaudio_result_t result = AAudioStream_requestStop(stream_);
            (void) result;
            result = AAudioStream_close(stream_);
            if (result != AAUDIO_OK) {
                ok = false;
            }
            stream_ = nullptr;
        }

        ringCv_.notify_all();
        if (writerThread_.joinable()) {
            writerThread_.join();
        }

        recording_.store(false);

        if (file_ != nullptr) {
            if (!PatchHeader()) {
                ok = false;
            }
            std::fflush(file_);
            std::fclose(file_);
            file_ = nullptr;
        }

        return ok;
    } catch (...) {
        recording_.store(false);
        return false;
    }
}

double WavRecorder::GetRms() const {
    try {
        std::lock_guard<std::mutex> lock(statsMutex_);
        if (samplesWritten_ <= 0) {
            return 0.0;
        }
        const double meanSq = sumSquares_ / static_cast<double>(samplesWritten_);
        double rms = std::sqrt(meanSq) / 32768.0;
        if (rms < 0.0) rms = 0.0;
        if (rms > 1.0) rms = 1.0;
        return rms;
    } catch (...) {
        return 0.0;
    }
}

int64_t WavRecorder::GetDurationMs() const {
    const int rate = outputRate_ > 0 ? outputRate_ : kTargetRate;
    const int64_t frames = framesWritten_.load();
    if (frames <= 0 || rate <= 0) {
        return 0;
    }
    return (frames * 1000) / rate;
}

// ---------------------------------------------------------------------------
// Luma analysis
// ---------------------------------------------------------------------------

bool ComputeLumaStats(const uint8_t* y, int w, int h, int rowStride,
                      double* meanOut, double gridOut[64]) {
    if (y == nullptr || w <= 0 || h <= 0 || rowStride < w) {
        if (meanOut != nullptr) *meanOut = 0.0;
        if (gridOut != nullptr) {
            for (int i = 0; i < 64; ++i) gridOut[i] = 0.0;
        }
        return false;
    }

    double cellSum[64] = {0.0};
    double cellCount[64] = {0.0};
    double total = 0.0;

    for (int row = 0; row < h; ++row) {
        const uint8_t* rowPtr = y + static_cast<size_t>(row) *
                                      static_cast<size_t>(rowStride);
        int cellRow = (row * 8) / h;
        if (cellRow < 0) cellRow = 0;
        if (cellRow > 7) cellRow = 7;
        for (int col = 0; col < w; ++col) {
            const double v = static_cast<double>(rowPtr[col]);
            total += v;
            int cellCol = (col * 8) / w;
            if (cellCol < 0) cellCol = 0;
            if (cellCol > 7) cellCol = 7;
            const int idx = cellRow * 8 + cellCol;
            cellSum[idx] += v;
            cellCount[idx] += 1.0;
        }
    }

    const double count = static_cast<double>(w) * static_cast<double>(h);
    const double mean = count > 0.0 ? total / count : 0.0;
    if (meanOut != nullptr) {
        *meanOut = mean;
    }
    if (gridOut != nullptr) {
        for (int i = 0; i < 64; ++i) {
            gridOut[i] = cellCount[i] > 0.0 ? cellSum[i] / cellCount[i] : 0.0;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// FlashDetector
// ---------------------------------------------------------------------------

FlashDetector::FlashDetector()
    : seeded_(false), baseline_(0.0), hasTriggered_(false), lastTriggerMs_(0) {}

void FlashDetector::Reset() {
    seeded_ = false;
    baseline_ = 0.0;
    hasTriggered_ = false;
    lastTriggerMs_ = 0;
}

bool FlashDetector::Feed(double mean, int64_t nowMs) {
    if (!seeded_) {
        baseline_ = mean;
        seeded_ = true;
        return false;
    }

    const double threshold = baseline_ * 1.8 + 12.0;
    if (mean > threshold) {
        if (hasTriggered_ && (nowMs - lastTriggerMs_) < 1000) {
            return false;
        }
        hasTriggered_ = true;
        lastTriggerMs_ = nowMs;
        return true;
    }

    // EMA update only for non-flash samples so a flash does not
    // pollute the baseline.
    baseline_ = baseline_ * 0.95 + mean * 0.05;
    return false;
}

}  // namespace uwcore
