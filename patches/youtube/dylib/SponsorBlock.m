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

void YTFreedomSponsorBlockInit(void) {
    startSponsorTimer();
}
