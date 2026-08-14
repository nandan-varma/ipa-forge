// PlayerQuickControls.m — the "Quality & Speed" pill on the fullscreen player.
//
// WHY this exists: the app's ...-menu quality/speed items in 21.32.4 are
// ELM/server-driven, and the handler selectors the old tweaks replaced
// (didPressVarispeed:/didPressVideoQuality:) are NOT implemented by any class
// in this binary — hooks on that path never produce UI. Instead of fighting
// the menu, we render our own small pill (current quality + speed) on the
// player controls and open OUR picker on tap:
//   - Speed: applied with -[YTPlayerViewController setPlaybackRate:] — the
//     same call the edge gestures use (verified working on device).
//   - Quality: built with MLQuickMenuVideoQualitySettingFormatConstraint and
//     applied via -didSelectVideoQualityFormatConstraint:forSelectableVideoFormats:
//     on the player VC, runtime-guarded and logged (the one remaining
//     assumption; device log confirms it).
// The current quality label is stashed by PlayerFeatures.m from the quality
// switch controllers; before that fires it reads "Auto".

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

static const NSInteger kPillTag = 0x5951;
static const float kPillSpeedRates[13] = {0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 5.0, 7.5, 10.0};

// Dynamic selectors used by this file — declared here so the modern clang
// accepts them (unknown selectors are hard errors even on id receivers).
@protocol YTFreedomQuickControlsHooks <NSObject>
- (NSString *)qualityLabel;
- (int)height;
- (double)FPS;
- (BOOL)isVideo;
- (id)initWithVideoQualitySetting:(int)setting formatSelectionReason:(NSInteger)reason qualityLabel:(NSString *)label;
- (void)didSelectVideoQualityFormatConstraint:(id)constraint forSelectableVideoFormats:(NSArray *)formats;
- (void)setPlaybackRate:(float)rate;
- (id)activeVideo;
- (NSArray *)selectableVideoFormats;
@end

// --- MLFormat dynamic accessors (header-documented; guarded) ----------------

static NSString *ytfFormatLabel(id format) {
    id<YTFreedomQuickControlsHooks> f = format;
    return [format respondsToSelector:@selector(qualityLabel)] ? f.qualityLabel : nil;
}
static int ytfFormatHeight(id format) {
    id<YTFreedomQuickControlsHooks> f = format;
    return [format respondsToSelector:@selector(height)] ? f.height : 0;
}
static float ytfFormatFPS(id format) {
    id<YTFreedomQuickControlsHooks> f = format;
    return [format respondsToSelector:@selector(FPS)] ? (float)f.FPS : 0;
}
static BOOL ytfFormatIsVideo(id format) {
    id<YTFreedomQuickControlsHooks> f = format;
    return [format respondsToSelector:@selector(isVideo)] ? f.isVideo : YES;
}

// --- Pill label -------------------------------------------------------------

@interface YTFPillLabel : UILabel
@property (nonatomic, copy) void (^onTap)(void);
@end

@implementation YTFPillLabel
- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        self.userInteractionEnabled = YES;
        self.font = [UIFont systemFontOfSize:12 weight:UIFontWeightSemibold];
        self.textColor = [UIColor whiteColor];
        self.backgroundColor = [[UIColor blackColor] colorWithAlphaComponent:0.6];
        self.layer.cornerRadius = 6;
        self.clipsToBounds = YES;
        self.textAlignment = NSTextAlignmentCenter;
        UITapGestureRecognizer *tap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(ytfPillTapped)];
        [self addGestureRecognizer:tap];
    }
    return self;
}
- (void)ytfPillTapped {
    if (self.onTap) self.onTap();
}
@end

static NSString *ytfPillText(void) {
    NSString *quality = ytfCurrentQualityLabel();
    if (!quality.length) quality = @"Auto";
    return [NSString stringWithFormat:@"%@ . %.2fx", quality, ytfPlaybackRateValue()];
}

// --- Quality apply ----------------------------------------------------------

static void ytfApplyQuality(UIViewController *playerVC, id format, NSArray *allFormats) {
    Class constraintCls = NSClassFromString(@"MLQuickMenuVideoQualitySettingFormatConstraint");
    SEL applySel = @selector(didSelectVideoQualityFormatConstraint:forSelectableVideoFormats:);
    if (!constraintCls) {
        os_log(ytfLog(), "YTFreedom: quality apply skipped - no constraint class");
        return;
    }
    if (![playerVC respondsToSelector:applySel]) {
        os_log(ytfLog(), "YTFreedom: quality apply skipped - player does not implement didSelectVideoQualityFormatConstraint:");
        return;
    }
    int setting = ytfFormatHeight(format);
    NSString *label = ytfFormatLabel(format);
    if (!label.length) label = [NSString stringWithFormat:@"%dp", setting];
    id<YTFreedomQuickControlsHooks> constraint = [(id)[constraintCls alloc] initWithVideoQualitySetting:setting
                                                                   formatSelectionReason:0
                                                                            qualityLabel:label];
    if (!constraint) return;
    [(id<YTFreedomQuickControlsHooks>)playerVC didSelectVideoQualityFormatConstraint:constraint forSelectableVideoFormats:allFormats];
    // Mirror the choice into the pill immediately.
    if (label.length) {
        ytfSetCurrentQualityLabel(label);
        os_log(ytfLog(), "YTFreedom: applied quality %@ (setting %d)", label, setting);
    }
}

// --- The picker sheet -------------------------------------------------------

static NSArray *ytfSortedQualityLabels(NSArray *formats) {
    NSMutableDictionary *byLabel = [NSMutableDictionary dictionary];
    for (id format in formats) {
        if (!ytfFormatIsVideo(format)) continue;
        NSString *label = ytfFormatLabel(format);
        if (!label.length) continue;
        id existing = byLabel[label];
        if (!existing) { byLabel[label] = format; continue; }
        // Prefer the higher-resolution duplicate of the same label.
        if (ytfFormatHeight(format) > ytfFormatHeight(existing)) byLabel[label] = format;
    }
    NSArray *labels = [byLabel allKeys];
    return [labels sortedArrayUsingComparator:^NSComparisonResult(NSString *a, NSString *b) {
        id fa = byLabel[a], fb = byLabel[b];
        int ha = ytfFormatHeight(fa), hb = ytfFormatHeight(fb);
        if (ha != hb) return ha > hb ? NSOrderedAscending : NSOrderedDescending;
        float fa2 = ytfFormatFPS(fa), fb2 = ytfFormatFPS(fb);
        if (fa2 != fb2) return fa2 > fb2 ? NSOrderedAscending : NSOrderedDescending;
        return NSOrderedSame;
    }];
}

static void ytfShowQualitySpeedSheet(UIViewController *overlayVC, UIView *sourceView) {
    UIViewController *playerVC = ytfCurrentPlayerViewController();
    if (!playerVC) {
        os_log(ytfLog(), "YTFreedom: pill tapped with no player VC");
        return;
    }
    UIAlertController *sheet = [UIAlertController alertControllerWithTitle:@"Quality & Speed"
        message:[NSString stringWithFormat:@"Current: %@", ytfPillText()]
        preferredStyle:UIAlertControllerStyleActionSheet];

    // Speed.
    for (int i = 0; i < 13; i++) {
        float rate = kPillSpeedRates[i];
        NSString *title = [NSString stringWithFormat:@"Speed %.2fx", rate];
        [sheet addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
            [(id<YTFreedomQuickControlsHooks>)playerVC setPlaybackRate:rate];
            os_log(ytfLog(), "YTFreedom: pill set playback rate %.2f", rate);
        }]];
    }

    // Quality — prefer the live list from the active video; fall back to the stash.
    NSArray *formats = nil;
    id<YTFreedomQuickControlsHooks> pvc = (id<YTFreedomQuickControlsHooks>)playerVC;
    id activeVideo = [pvc respondsToSelector:@selector(activeVideo)] ? [pvc activeVideo] : nil;
    id<YTFreedomQuickControlsHooks> av = activeVideo;
    if ([av respondsToSelector:@selector(selectableVideoFormats)])
        formats = [av selectableVideoFormats];
    if (!formats.count) formats = ytfSelectableFormats();
    if (formats.count) {
        NSArray *labels = ytfSortedQualityLabels(formats);
        NSString *current = ytfCurrentQualityLabel();
        for (NSString *label in labels) {
            NSString *title = [label isEqualToString:current] ? [label stringByAppendingString:@" (current)"] : label;
            // Resolve the exact format for this label (prefer the highest-resolution one).
            id picked = nil;
            int bestHeight = -1;
            for (id f in formats) {
                if (![ytfFormatLabel(f) isEqualToString:label]) continue;
                if (ytfFormatHeight(f) > bestHeight) { bestHeight = ytfFormatHeight(f); picked = f; }
            }
            [sheet addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
                ytfApplyQuality(playerVC, picked ?: formats.firstObject, formats);
            }]];
        }
    } else {
        [sheet addAction:[UIAlertAction actionWithTitle:@"Quality: no formats available" style:UIAlertActionStyleDefault handler:nil]];
    }

    [sheet addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    if (sheet.popoverPresentationController) {
        sheet.popoverPresentationController.sourceView = sourceView;
        sheet.popoverPresentationController.sourceRect = sourceView.bounds;
    }
    UIViewController *presenter = overlayVC;
    while (presenter.presentedViewController) presenter = presenter.presentedViewController;
    [presenter presentViewController:sheet animated:YES completion:nil];
}

// --- Overlay attachment -----------------------------------------------------

static void fixPillOnOverlay(void) {
    static IMP orig_layout;
    orig_layout = ytfHookInstance(NSClassFromString(@"YTMainAppVideoPlayerOverlayViewController"),
        @selector(viewDidLayoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_layout)(self, @selector(viewDidLayoutSubviews));
            UIView *view = [(UIViewController *)self view];
            if (!view || view.bounds.size.width < 200) return;
            YTFPillLabel *pill = (YTFPillLabel *)[view viewWithTag:kPillTag];
            if (!pill) {
                __weak UIViewController *weakOverlay = self;
                __weak YTFPillLabel *weakPill = nil;
                pill = [[YTFPillLabel alloc] initWithFrame:CGRectMake(16, 0, 150, 28)];
                pill.tag = kPillTag;
                weakPill = pill;
                pill.onTap = ^{
                    UIViewController *strong = weakOverlay;
                    YTFPillLabel *strongPill = weakPill;
                    if (strong && strongPill) ytfShowQualitySpeedSheet(strong, strongPill);
                };
                [view addSubview:pill];
            }
            pill.frame = CGRectMake(16, view.bounds.size.height - 118, 150, 28);
            pill.text = ytfPillText();
        });
    (void)orig_layout;
}

void YTFreedomPlayerQuickControlsInit(void) {
    fixPillOnOverlay();
}
