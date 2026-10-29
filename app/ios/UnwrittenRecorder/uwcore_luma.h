// Unwritten Craft — uwcore luma analysis (portable C++).
//
// This is the platform-independent half of the Android C++ core
// (app/android/app/src/main/cpp/uwcore.{h,cpp}): mean luma plus an 8x8
// grid over the Y plane, and the EMA-baseline flash detector. The
// WavRecorder half stays Android-only — it drives AAudio, which has no
// iOS equivalent — so it is not ported here.
#pragma once

#include <cstdint>

namespace uwcore {

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
