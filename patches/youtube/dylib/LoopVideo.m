// LoopVideo.m — restart playback when the video ends.
//
// Timer-based (same pattern as SponsorBlock): while KLoopVideo is on and a
// player is active, if the media position reaches the end, seek back to 0 via
// -[YTPlayerViewController seekToTime:]. No fragile end-of-playback callback
// to hook; currentVideoMediaTime/currentVideoTotalMediaTime are
// header-verified on YTPlayerViewController.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

@protocol YTFreedomLoopHooks <NSObject>
- (double)currentVideoMediaTime;
- (double)currentVideoTotalMediaTime;
- (void)seekToTime:(CGFloat)time;
@end

static void ytfLoopTick(void) {
    if (!IS_ENABLED(KLoopVideo)) return;
    UIViewController *playerVC = ytfCurrentPlayerViewController();
    if (!playerVC) return;
    id<YTFreedomLoopHooks> pvc = (id<YTFreedomLoopHooks>)playerVC;
    if (![pvc respondsToSelector:@selector(currentVideoMediaTime)] ||
        ![pvc respondsToSelector:@selector(currentVideoTotalMediaTime)] ||
        ![pvc respondsToSelector:@selector(seekToTime:)]) return;
    double time = [pvc currentVideoMediaTime];
    double total = [pvc currentVideoTotalMediaTime];
    if (total > 5.0 && time >= total - 0.4) {
        [pvc seekToTime:0.0];
    }
}

void YTFreedomLoopVideoInit(void) {
    static dispatch_source_t timer;
    if (timer) return;
    timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0,
                                   dispatch_get_main_queue());
    dispatch_source_set_timer(timer, dispatch_walltime(NULL, 0),
                              (uint64_t)(1.0 * NSEC_PER_SEC), (uint64_t)(0.2 * NSEC_PER_SEC));
    dispatch_source_set_event_handler(timer, ^{ ytfLoopTick(); });
    dispatch_resume(timer);
}
