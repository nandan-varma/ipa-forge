// PlayerGestures.m — edge-swipe gestures (G6), ported from YouMod's Player.x
// gestures group (itself from YTLitePlus, @bhackel). Vertical swipes on the
// left/right edges of the player control brightness / volume / playback
// speed; a HUD shows the current value. Toggles and options live in the
// Player settings section (GestureControls + GestureActivationArea +
// LeftSideGesture/RightSideGesture + GestureHUD/HUDSize/HUDPosition).
//
// Plain-runtime notes: YouMod's %property YouModPanGesture/YouModGestureHUD
// become associated objects; the %new gesture-delegate methods are added via
// ytfAddInstanceMethod.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>
#import <MediaPlayer/MediaPlayer.h>

@protocol YTFreedomGestureHooks <NSObject>
@optional
- (void)setPlaybackRate:(float)rate;
- (void)addGestureRecognizer:(UIGestureRecognizer *)gesture;
- (void)setDelegate:(id)delegate;
@end

static const void *kPanGestureKey = &kPanGestureKey;
static const void *kGestureHUDKey = &kGestureHUDKey;

static float ytfPlaybackRate = 1.0f;

static float ytfAreaPercent(void) {
    int setting = INTFORVAL(KGestureActivationArea);
    switch (setting) {
        case 0: return 0.10f;
        case 2: return 0.20f;
        case 3: return 0.25f;
        case 4: return 0.30f;
        case 5: return 0.35f;
        case 6: return 0.40f;
        case 7: return 0.45f;
        case 8: return 0.50f;
        default: return 0.15f;
    }
}

static int ytfSideAction(NSString *key, int fallback) {
    NSNumber *value = [[NSUserDefaults standardUserDefaults] objectForKey:key];
    return value ? (int)[value integerValue] : fallback;
}

static void ytfUpdateHUD(id player, NSString *symbol, NSString *text) {
    UILabel *hud = objc_getAssociatedObject(player, kGestureHUDKey);
    if (!hud) return;
    NSTextAttachment *attachment = [NSTextAttachment new];
    UIImageSymbolConfiguration *config =
        [UIImageSymbolConfiguration configurationWithPointSize:hud.font.pointSize - 1];
    UIImage *image = [UIImage systemImageNamed:symbol withConfiguration:config];
    attachment.image = [image imageWithRenderingMode:UIImageRenderingModeAlwaysTemplate];
    CGFloat iconY = (hud.font.capHeight - attachment.image.size.height) / 2.0;
    attachment.bounds = CGRectMake(0, iconY, attachment.image.size.width, attachment.image.size.height);
    NSMutableAttributedString *attributed =
        [[NSMutableAttributedString alloc] initWithAttributedString:
            [NSAttributedString attributedStringWithAttachment:attachment]];
    [attributed appendAttributedString:
        [[NSAttributedString alloc] initWithString:text
            attributes:@{NSFontAttributeName: hud.font, NSForegroundColorAttributeName: hud.textColor}]];
    hud.attributedText = attributed;
    hud.alpha = 1.0;
}

static void ytfSetupHUD(id player) {
    if (!IS_ENABLED(KGestureHUD)) return;
    UILabel *hud = objc_getAssociatedObject(player, kGestureHUDKey);
    if (hud) return;
    UIView *view = ((UIViewController *)player).view;
    if (!view) return;
    hud = [[UILabel alloc] initWithFrame:CGRectZero];
    hud.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.5];
    hud.textColor = [UIColor colorWithWhite:1.0 alpha:0.75];
    hud.tintColor = [UIColor colorWithWhite:1.0 alpha:0.75];
    hud.textAlignment = NSTextAlignmentCenter;
    hud.layer.masksToBounds = YES;
    hud.alpha = 0.0;
    objc_setAssociatedObject(player, kGestureHUDKey, hud, OBJC_ASSOCIATION_RETAIN_NONATOMIC);

    int sizeSetting = [[NSUserDefaults standardUserDefaults] objectForKey:KGestureHUDSize]
        ? INTFORVAL(KGestureHUDSize) : 1;
    CGFloat fontSize = 14.0 + (sizeSetting * 2.0);
    CGFloat hudWidth = 74.0 + (sizeSetting * 10.0);
    CGFloat hudHeight = 30.0 + (sizeSetting * 4.0);
    hud.frame = CGRectMake(0, 0, hudWidth, hudHeight);
    hud.layer.cornerRadius = hudHeight / 2.0;
    hud.font = [UIFont boldSystemFontOfSize:fontSize];
    [view addSubview:hud];

    int posSetting = [[NSUserDefaults standardUserDefaults] objectForKey:KGestureHUDPosition]
        ? INTFORVAL(KGestureHUDPosition) : 0;
    CGFloat viewHeight = view.bounds.size.height;
    CGFloat centerY = viewHeight / 6.0;
    if (posSetting == 1) centerY = viewHeight / 2.0;
    else if (posSetting == 2) centerY = viewHeight * 5.0 / 6.0;
    [view bringSubviewToFront:hud];
    hud.center = CGPointMake(view.bounds.size.width / 2, centerY);
}

static void ytfHandlePan(UIPanGestureRecognizer *pan, id player) {
    static float initialVolume, initialBrightness, initialSpeed;
    static int controlType = 0;
    static CGFloat deadzoneStart = 0;
    static float lastUpdatedSpeed = 0;
    static MPVolumeView *volumeView;
    static UISlider *volumeSlider;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        volumeView = [[MPVolumeView alloc] initWithFrame:CGRectZero];
        for (UIView *subview in volumeView.subviews) {
            if ([subview isKindOfClass:[UISlider class]]) { volumeSlider = (UISlider *)subview; break; }
        }
    });

    if (pan.state == UIGestureRecognizerStateBegan) {
        ytfSetupHUD(player);
        UIView *view = ((UIViewController *)player).view;
        if (!view) return;
        CGPoint location = [pan locationInView:view];
        CGFloat width = view.bounds.size.width;
        float area = ytfAreaPercent();
        int left = ytfSideAction(KLeftSideGesture, 1);
        int right = ytfSideAction(KRightSideGesture, 2);
        if (location.x <= width * area) controlType = left;
        else if (location.x >= width * (1.0 - area)) controlType = right;
        else controlType = 0;
        deadzoneStart = [pan translationInView:view].y;
        if (controlType == 1) initialBrightness = [UIScreen mainScreen].brightness;
        else if (controlType == 2) initialVolume = [AVAudioSession sharedInstance].outputVolume;
        else if (controlType == 3) initialSpeed = ytfPlaybackRate;
    }

    if (pan.state == UIGestureRecognizerStateChanged) {
        if (controlType == 0) return;
        UIView *view = ((UIViewController *)player).view;
        if (!view) return;
        CGPoint translation = [pan translationInView:view];
        CGFloat delta = (-(translation.y - deadzoneStart) / view.bounds.size.height);
        NSString *symbol = nil, *text = nil;
        if (controlType == 1) {
            float brightness = fmaxf(fminf(initialBrightness + delta, 1.0), 0.0);
            [UIScreen mainScreen].brightness = brightness;
            symbol = @"sun.max.fill";
            text = [NSString stringWithFormat:@" %d%%", (int)(brightness * 100)];
        } else if (controlType == 2) {
            float volume = fmaxf(fminf(initialVolume + delta, 1.0), 0.0);
            volumeSlider.value = volume;
            symbol = @"speaker.wave.2.fill";
            text = [NSString stringWithFormat:@" %d%%", (int)(volume * 100)];
        } else if (controlType == 3) {
            float raw = fmaxf(fminf(initialSpeed + delta * 8.0, 10.0), 0.25);
            float stepped = roundf(raw * 4.0) / 4.0;
            if (stepped != lastUpdatedSpeed) {
                id<YTFreedomGestureHooks> hooks = player;
                if ([hooks respondsToSelector:@selector(setPlaybackRate:)])
                    [hooks setPlaybackRate:stepped];
                lastUpdatedSpeed = stepped;
            }
            symbol = @"speedometer";
            text = [NSString stringWithFormat:@" %.2fx", stepped];
        }
        if (IS_ENABLED(KGestureHUD) && symbol)
            ytfUpdateHUD(player, symbol, text);
    } else if (pan.state == UIGestureRecognizerStateEnded
               || pan.state == UIGestureRecognizerStateCancelled
               || pan.state == UIGestureRecognizerStateFailed) {
        UILabel *hud = objc_getAssociatedObject(player, kGestureHUDKey);
        if (hud) {
            [UIView animateWithDuration:0.3 delay:0.5 options:UIViewAnimationOptionCurveEaseOut
                animations:^{ hud.alpha = 0.0; } completion:nil];
        }
        lastUpdatedSpeed = 0;
    }
}

// %new delegate methods on YTPlayerViewController (UIGestureRecognizerDelegate).
static void addGestureDelegateMethods(Class cls) {
    // gestureRecognizerShouldBegin:
    ytfAddInstanceMethod(cls, sel_registerName("gestureRecognizerShouldBegin:"),
        ^BOOL(id self, UIGestureRecognizer *gesture) {
            UIPanGestureRecognizer *ourPan = objc_getAssociatedObject(self, kPanGestureKey);
            if (gesture == ourPan) {
                UIView *view = ((UIViewController *)self).view;
                if (!view) return NO;
                CGPoint start = [ourPan locationInView:view];
                CGFloat width = view.bounds.size.width;
                float area = ytfAreaPercent();
                int left = ytfSideAction(KLeftSideGesture, 1);
                int right = ytfSideAction(KRightSideGesture, 2);
                if (start.x > width * area && start.x < width * (1.0 - area)) return NO;
                if (start.x <= width * area && left == 0) return NO;
                if (start.x >= width * (1.0 - area) && right == 0) return NO;
                CGPoint velocity = [ourPan velocityInView:view];
                if (fabs(velocity.x) > fabs(velocity.y)) return NO;
                return YES;
            }
            return YES;
        }, "c@:@");

    ytfAddInstanceMethod(cls,
        sel_registerName("gestureRecognizer:shouldBeRequiredToFailByGestureRecognizer:"),
        ^BOOL(id self, UIGestureRecognizer *gesture, UIGestureRecognizer *other) {
            UIPanGestureRecognizer *ourPan = objc_getAssociatedObject(self, kPanGestureKey);
            if (gesture == ourPan && [other isKindOfClass:[UIPanGestureRecognizer class]])
                return YES;
            return NO;
        }, "c@:@@");

    ytfAddInstanceMethod(cls,
        sel_registerName("gestureRecognizer:shouldRecognizeSimultaneouslyWithGestureRecognizer:"),
        ^BOOL(id self, UIGestureRecognizer *gesture, UIGestureRecognizer *other) {
            UIPanGestureRecognizer *ourPan = objc_getAssociatedObject(self, kPanGestureKey);
            if (gesture == ourPan) return NO;
            return YES;
        }, "c@:@@");
}

// Weak ref to the current player VC, exported for SponsorBlock.m (it needs
// currentVideoID / currentVideoMediaTime / seekToTime:).
static __weak UIViewController *sCurrentPlayerVC = nil;
UIViewController *ytfCurrentPlayerViewController(void) { return sCurrentPlayerVC; }

static void fixGestures(void) {
    if (!IS_ENABLED(KGestureControls)) return;
    Class playerVC = NSClassFromString(@"YTPlayerViewController");
    if (!playerVC) return;
    addGestureDelegateMethods(playerVC);

    // Track playback rate so the speed gesture starts from the current rate.
    static IMP orig_setPlaybackRate;
    orig_setPlaybackRate = ytfHookInstance(playerVC, @selector(setPlaybackRate:),
        ^void(id self, float rate) {
            ytfPlaybackRate = rate;
            ((void(*)(id, SEL, float))orig_setPlaybackRate)(self, @selector(setPlaybackRate:), rate);
        });
    (void)orig_setPlaybackRate;

    // Attach the pan gesture when the player view controller is set.
    static IMP orig_didSetPlayerVC;
    orig_didSetPlayerVC = ytfHookInstance(NSClassFromString(@"YTWatchLayerViewController"),
        @selector(watchController:didSetPlayerViewController:),
        ^void(id self, id watchController, id playerViewController) {
            sCurrentPlayerVC = playerViewController;
            if (playerViewController) {
                UIPanGestureRecognizer *pan = objc_getAssociatedObject(playerViewController, kPanGestureKey);
                if (!pan) {
                    pan = [[UIPanGestureRecognizer alloc] initWithTarget:playerViewController
                                                                  action:@selector(YTFreedomHandlePanGesture:)];
                    pan.delegate = playerViewController;
                    objc_setAssociatedObject(playerViewController, kPanGestureKey, pan,
                                             OBJC_ASSOCIATION_RETAIN_NONATOMIC);
                    id<YTFreedomGestureHooks> hooks = playerViewController;
                    id playerView = [(id)hooks valueForKey:@"playerView"];
                    if ([playerView respondsToSelector:@selector(addGestureRecognizer:)])
                        [playerView addGestureRecognizer:pan];
                }
            }
            ((void(*)(id, SEL, id, id))orig_didSetPlayerVC)(
                self, @selector(watchController:didSetPlayerViewController:), watchController, playerViewController);
        });
    (void)orig_didSetPlayerVC;

    // Handler invoked by the pan gesture.
    ytfAddInstanceMethod(playerVC, sel_registerName("YTFreedomHandlePanGesture:"),
        ^void(id self, UIPanGestureRecognizer *pan) {
            ytfHandlePan(pan, self);
        }, "v@:@");
}

void YTFreedomPlayerGesturesInit(void) {
    fixGestures();
}
