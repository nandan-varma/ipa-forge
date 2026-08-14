// SponsorBlock.m — automatic skipping of sponsor segments.
//
// Port of iSponsorBlock's auto-skip (the old pure-skip version, no player-bar
// UI yet) onto the 21.32.4 player API, plain ObjC:
//   - fetch segments from the SponsorBlock API for the current video
//   - a 1s timer checks the playback position; when it enters a segment the
//     player seeks to the segment end via -[YTPlayerViewController seekToTime:]
// All selectors are header-verified on 21.32.4 (YTPlayerViewController:
// currentVideoID / currentVideoMediaTime / seekToTime:). The player VC comes
// from PlayerGestures.m (ytfCurrentPlayerViewController).
//
// Privacy: video IDs are sent to api.sponsor.ajay.app only when the toggle
// (KSponsorBlock, System group, default OFF) is enabled.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

// ---------------------------------------------------------------------------
// Segment cache + fetch
// ---------------------------------------------------------------------------

@interface YTFSegment : NSObject
@property (nonatomic) double start;
@property (nonatomic) double end;
@end
@implementation YTFSegment
@end

static NSArray<YTFSegment *> *sSegments = nil;   // segments for sSegmentVideoID
static NSString *sSegmentVideoID = nil;
static double sLastSkippedEnd = -1;               // avoid double-skipping the same segment

static NSArray<YTFSegment *> *ytfSegmentsForVideo(NSString *videoID) {
    if ([sSegmentVideoID isEqualToString:videoID]) return sSegments;
    return nil;
}

// For the player-bar renderer (below): segments for the current video.
NSArray *ytfSponsorSegments(void) {
    if (!IS_ENABLED(KSponsorBlock)) return nil;
    return sSegments;
}

// Fetch segments for videoID (async); updates the cache when done.
static void ytfFetchSegments(NSString *videoID) {
    NSString *urlString = [NSString stringWithFormat:
        @"https://api.sponsor.ajay.app/api/skipSegments?videoID=%@&categories=%%5B%%22sponsor%%22%%5D",
        videoID];
    NSURL *url = [NSURL URLWithString:urlString];
    if (!url) return;
    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithURL:url
        completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
            if (error || !data) return;
            NSArray *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if (![json isKindOfClass:[NSArray class]]) return;
            NSMutableArray *segments = [NSMutableArray array];
            for (id item in json) {
                if (![item isKindOfClass:[NSDictionary class]]) continue;
                NSArray *seg = item[@"segment"];
                if (![seg isKindOfClass:[NSArray class]] || seg.count < 2) continue;
                YTFSegment *s = [YTFSegment new];
                s.start = [seg[0] doubleValue];
                s.end = [seg[1] doubleValue];
                if (s.end > s.start) [segments addObject:s];
            }
            if (segments.count) {
                sSegments = segments;
                sSegmentVideoID = videoID;
                sLastSkippedEnd = -1;
                os_log(ytfLog(), "YTFreedom: SponsorBlock %lu segments for %@",
                      (unsigned long)segments.count, videoID);
            }
        }];
    [task resume];
}

// ---------------------------------------------------------------------------
// Poll loop
// ---------------------------------------------------------------------------

// Informal protocol so the modern clang accepts the player-VC selectors.
@protocol YTFreedomSponsorHooks <NSObject>
- (NSString *)currentVideoID;
- (double)currentVideoMediaTime;
- (double)currentVideoTotalMediaTime;
- (void)seekToTime:(CGFloat)time;
@end

static void ytfSponsorTick(void) {
    UIViewController *playerVC = ytfCurrentPlayerViewController();
    if (!playerVC || !IS_ENABLED(KSponsorBlock)) return;
    id<YTFreedomSponsorHooks> pvc = (id<YTFreedomSponsorHooks>)playerVC;
    if (![pvc respondsToSelector:@selector(currentVideoID)] ||
        ![pvc respondsToSelector:@selector(currentVideoMediaTime)] ||
        ![pvc respondsToSelector:@selector(seekToTime:)]) return;

    NSString *videoID = [pvc currentVideoID];
    if (!videoID.length) return;

    // New video -> fetch its segments (once).
    if (![ytfSegmentsForVideo(videoID) count] && ![sSegmentVideoID isEqualToString:videoID]) {
        ytfFetchSegments(videoID);
        sSegmentVideoID = videoID;  // mark in-flight so we don't re-fetch every tick
        return;
    }
    NSArray *segments = ytfSegmentsForVideo(videoID);
    if (!segments.count) return;

    double time = [pvc currentVideoMediaTime];
    for (YTFSegment *seg in segments) {
        if (time >= seg.start && time < seg.end - 0.3 && fabs(time - sLastSkippedEnd) > 2.0) {
            sLastSkippedEnd = seg.end;
            os_log(ytfLog(), "YTFreedom: SponsorBlock skip %.1fs -> %.1fs", time, seg.end);
            [pvc seekToTime:(CGFloat)seg.end];
            return;
        }
    }
}

static void startSponsorTimer(void) {
    static dispatch_source_t timer;
    if (timer) return;
    timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0,
                                   dispatch_get_main_queue());
    dispatch_source_set_timer(timer, dispatch_walltime(NULL, 0),
                              (uint64_t)(1.0 * NSEC_PER_SEC), (uint64_t)(0.2 * NSEC_PER_SEC));
    dispatch_source_set_event_handler(timer, ^{ ytfSponsorTick(); });
    dispatch_resume(timer);
}

// ---------------------------------------------------------------------------
// Player-bar segment visualization: colored markers on the seekbar showing
// where the sponsor segments are. Rendered on the inline bar and the
// fullscreen bar; total duration comes from the player VC.
// ---------------------------------------------------------------------------

static const NSInteger kSBMarkerTag = 0x5342;

static void ytfRenderSegmentsOnBar(UIView *bar) {
    if (!bar || bar.bounds.size.width < 50) return;
    // Remove stale markers.
    for (UIView *sub in [bar subviews]) {
        if (sub.tag == kSBMarkerTag) [sub removeFromSuperview];
    }
    NSArray *segments = ytfSponsorSegments();
    if (!segments.count) return;
    UIViewController *playerVC = ytfCurrentPlayerViewController();
    if (!playerVC) return;
    id<YTFreedomSponsorHooks> pvc = (id<YTFreedomSponsorHooks>)playerVC;
    if (![pvc respondsToSelector:@selector(currentVideoTotalMediaTime)]) return;
    double totalTime = [pvc currentVideoTotalMediaTime];
    if (totalTime <= 0) return;

    CGFloat barWidth = bar.bounds.size.width;
    CGFloat barHeight = bar.bounds.size.height;
    for (YTFSegment *seg in segments) {
        CGFloat x = (CGFloat)(seg.start / totalTime) * barWidth;
        CGFloat w = (CGFloat)((seg.end - seg.start) / totalTime) * barWidth;
        if (w < 2.0) w = 2.0;
        UIView *marker = [[UIView alloc] initWithFrame:CGRectMake(x, barHeight - 3.0, w, 3.0)];
        marker.tag = kSBMarkerTag;
        marker.backgroundColor = [UIColor colorWithRed:0.0 green:0.64 blue:0.42 alpha:0.9];
        marker.userInteractionEnabled = NO;
        [bar addSubview:marker];
    }
}

static void fixSegmentBarOverlay(void) {
    static IMP orig_inlineLayout;
    orig_inlineLayout = ytfHookInstance(NSClassFromString(@"YTInlinePlayerBarContainerView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_inlineLayout)(self, @selector(layoutSubviews));
            ytfRenderSegmentsOnBar((UIView *)self);
        });
    (void)orig_inlineLayout;
    static IMP orig_barLayout;
    orig_barLayout = ytfHookInstance(NSClassFromString(@"YTPlayerBarView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_barLayout)(self, @selector(layoutSubviews));
            ytfRenderSegmentsOnBar((UIView *)self);
        });
    (void)orig_barLayout;
}

void YTFreedomSponsorBlockInit(void) {
    startSponsorTimer();
    fixSegmentBarOverlay();
}
