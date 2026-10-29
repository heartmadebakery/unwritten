// Unwritten Craft — thin Objective-C++ bridge over the portable
// uwcore luma analysis, so Swift can call it with zero copies.
#import <Foundation/Foundation.h>
#import <stdint.h>

@class AVCaptureSession;

#ifdef __cplusplus
extern "C" {
#endif

// Mean luma (0..255) over the Y plane; gridOut (if non-NULL) receives
// the 8x8 grid of cell means. Returns the mean, or 0 on bad input.
double UWComputeLumaMean(const uint8_t *y, int w, int h, int rowStride,
                         double *gridOut);

// Starts an AVCaptureSession behind an ObjC exception handler.
// startRunning throws (fatal in Swift, which cannot catch ObjC
// exceptions) when the session cannot run — e.g. no inputs on a
// camera-less device. Returns YES when the session started.
BOOL UWStartCaptureSession(AVCaptureSession *session);

#ifdef __cplusplus
}  // extern "C"
#endif

@interface UWFlashDetector : NSObject
- (BOOL)feedMean:(double)mean nowMs:(long long)nowMs;
- (void)reset;
- (double)baseline;
@end
