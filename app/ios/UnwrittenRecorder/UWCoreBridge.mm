// Unwritten Craft — UWCoreBridge implementation.
#import "UWCoreBridge.h"
#import "uwcore_luma.h"
#import <AVFoundation/AVFoundation.h>

BOOL UWStartCaptureSession(AVCaptureSession *session) {
    if (session == nil) return NO;
    @try {
        [session startRunning];
        return session.isRunning ? YES : NO;
    } @catch (NSException *exception) {
        return NO;
    }
}

double UWComputeLumaMean(const uint8_t *y, int w, int h, int rowStride,
                         double *gridOut) {
    double mean = 0.0;
    double grid[64];
    if (!uwcore::ComputeLumaStats(y, w, h, rowStride, &mean, grid)) return 0.0;
    if (gridOut != nullptr) {
        for (int i = 0; i < 64; ++i) gridOut[i] = grid[i];
    }
    return mean;
}

@implementation UWFlashDetector {
    uwcore::FlashDetector _detector;
}

- (BOOL)feedMean:(double)mean nowMs:(long long)nowMs {
    return _detector.Feed(mean, (int64_t)nowMs) ? YES : NO;
}

- (void)reset {
    _detector.Reset();
}

- (double)baseline {
    return _detector.GetBaseline();
}

@end
