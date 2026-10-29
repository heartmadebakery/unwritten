// Unwritten Craft — uwcore luma analysis, ported verbatim from the
// platform-independent section of
// app/android/app/src/main/cpp/uwcore.cpp.
#include "uwcore_luma.h"

#include <cmath>
#include <cstddef>

namespace uwcore {

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
