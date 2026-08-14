// MediaDownload.m — long-press to save/share media.
//
// All model hooks verified against the 442.0.0 binary:
//   - feed:  IGFeedItemMediaCell -post -> IGMedia (covers photo AND video
//            cells via the common superclass; the old IGFeedPhotoView /
//            IGModernFeedVideoCell hooks are gone in 442.0.0)
//   - story: IGStoryPhotoView -item / IGStoryVideoView -item -> IGMedia
//            (fallback: IGStoryFullscreenSectionController -currentStoryItem)
//   - pfp:   IGProfilePictureImageView -userGQL -> IGUser -> derivedProfilePicURL
// Media URL extraction mirrors SCInsta's helpers: photos via
// -imageURLForWidth:, videos via -allVideoURLs (both verified).
//
// Everything is resolved at runtime (NSClassFromString + performSelector) so
// the dylib never links against Instagram classes.
#import "IGModHook.h"

static Class igClass(const char *name) { return NSClassFromString(@(name)); }

// --- media URL extraction ----------------------------------------------------

// IGPhoto -imageURLForWidth: returns the highest-quality URL for a big width.
static NSURL *igPhotoURL(id photo) {
    if (!photo) return nil;
    SEL s = NSSelectorFromString(@"imageURLForWidth:");
    if (![photo respondsToSelector:s]) return nil;
    NSURL *url = ((NSURL * (*)(id, SEL, CGFloat))objc_msgSend)(photo, s, 100000.0);
    return url;
}

// IGVideo -allVideoURLs returns a set of NSURLs (post-v398 API; the older
// sortedVideoURLsBySize is gone in 442.0.0).
static NSURL *igVideoURL(id video) {
    if (!video) return nil;
    SEL s = NSSelectorFromString(@"allVideoURLs");
    if (![video respondsToSelector:s]) return nil;
    id urls = ((id (*)(id, SEL))objc_msgSend)(video, s);
    NSURL *url = [urls isKindOfClass:NSArray.class] ? [urls firstObject]
                 : [urls isKindOfClass:NSSet.class] ? [urls anyObject] : nil;
    return url;
}

static NSURL *igMediaPhotoURL(id media) { return igPhotoURL(igObj(media, NSSelectorFromString(@"photo"))); }
static NSURL *igMediaVideoURL(id media) { return igVideoURL(igObj(media, NSSelectorFromString(@"video"))); }

// --- long-press plumbing -----------------------------------------------------
// One gesture per view; the trigger block receives the view and decides what
// to share. Views that already carry Instagram gestures coexist fine — the
// long-press only fires when the user holds still.

// The gesture target retains the action block. Kept as a small internal class
// (not a block IMP) so we can attach to arbitrary views without swizzling.
@interface IGPressTarget : NSObject
- (instancetype)initWithAction:(void (^)(UIView *))action;
- (void)fire:(UILongPressGestureRecognizer *)sender;
@end

@implementation IGPressTarget {
    void (^_action)(UIView *);
}
- (instancetype)initWithAction:(void (^)(UIView *))action { self = [super init]; _action = [action copy]; return self; }
- (void)fire:(UILongPressGestureRecognizer *)sender {
    if (sender.state != UIGestureRecognizerStateBegan) return;
    if (_action) _action(sender.view);
}
@end

static void igAddLongPress(UIView *view, NSTimeInterval duration, void (^action)(UIView *v)) {
    if (!view) return;
    for (UIGestureRecognizer *g in view.gestureRecognizers) {
        if ([g isKindOfClass:UILongPressGestureRecognizer.class]) return; // one per view
    }
    UILongPressGestureRecognizer *lp = [[UILongPressGestureRecognizer alloc]
        initWithTarget:[[IGPressTarget alloc] initWithAction:action] action:@selector(fire:)];
    lp.minimumPressDuration = duration;
    [view addGestureRecognizer:lp];
}

// Attach a long-press to every instance of a view class as it joins the
// hierarchy (didMoveToSuperview is the standard attach point).
static void igEnableLongPressOn(Class viewCls, NSTimeInterval duration, void (^action)(UIView *v)) {
    if (!viewCls) return;
    __block IMP orig = NULL;
    orig = igHookInstance(viewCls, @selector(didMoveToSuperview),
        ^void(id self) {
            if (orig) ((void (*)(id, SEL))orig)(self, @selector(didMoveToSuperview));
            igAddLongPress(self, duration, action);
        });
}

// --- feature wiring ----------------------------------------------------------

void IGMediaDownloadInit(void) {
    // Feed media (photos + videos share IGFeedItemMediaCell in 442.0.0).
    if (igEnabled(kIGFeedDownload)) {
        igEnableLongPressOn(igClass("IGFeedItemMediaCell"), 0.6, ^(UIView *v) {
            id post = igObj(v, NSSelectorFromString(@"post"));
            NSURL *url = igMediaVideoURL(post) ?: igMediaPhotoURL(post);
            if (!url) { igShowToast(@"Could not extract media from post"); return; }
            igShareRemoteURL(url, @"Saving post media…");
        });
    }

    // Stories (photo + video views both expose -item in 442.0.0).
    if (igEnabled(kIGStoryDownload)) {
        igEnableLongPressOn(igClass("IGStoryPhotoView"), 0.6, ^(UIView *v) {
            id item = igObj(v, NSSelectorFromString(@"item"));
            NSURL *url = igMediaPhotoURL(item) ?: igMediaVideoURL(item);
            if (!url) { igShowToast(@"Could not extract story media"); return; }
            igShareRemoteURL(url, @"Saving story media…");
        });
        igEnableLongPressOn(igClass("IGStoryVideoView"), 0.6, ^(UIView *v) {
            id item = igObj(v, NSSelectorFromString(@"item"));
            if (!item) {
                id captionDelegate = igObj(v, NSSelectorFromString(@"captionDelegate"));
                item = igObj(captionDelegate, NSSelectorFromString(@"currentStoryItem"));
            }
            NSURL *url = igMediaVideoURL(item) ?: igMediaPhotoURL(item);
            if (!url) { igShowToast(@"Could not extract story media"); return; }
            igShareRemoteURL(url, @"Saving story media…");
        });
    }

    // Profile picture: IGUser -derivedProfilePicURL (verified in 442.0.0).
    if (igEnabled(kIGProfilePicDownload)) {
        igEnableLongPressOn(igClass("IGProfilePictureImageView"), 0.6, ^(UIView *v) {
            id user = igObj(v, NSSelectorFromString(@"userGQL"));
            NSURL *url = igObj(user, NSSelectorFromString(@"derivedProfilePicURL"));
            if (!url) { igShowToast(@"Could not extract profile picture"); return; }
            igShareRemoteURL(url, @"Saving profile picture…");
        });
    }
}
