// StoryPrivacy.m — story seen receipts, DM typing status, screenshot alerts.
//
// All hooks verified against the 442.0.0 binary:
//   - IGStorySeenStateUploader -initWithUserSessionPK:networker: / -networker
//     (killing both stops the seen-receipt upload)
//   - IGDirectTypingStatusService -updateOutgoingStatusIsActive:...
//   - IGViewController -screenshotObserver (returns the observer every VC
//     consults; nil disables screenshot detection app-wide)
//   - IGScreenshotObserver -initForController: (never create an observer)
//   - IGDirectVisualMessageScreenshotSafetyLogger -initWithUserSession:entryPoint:
//   - IGStoryViewerContainerView -setShouldBlockScreenshot:viewModel:
//   - the screenshotObserverDidSee* delegate methods on the three viewers
//     that still implement them in 442.0.0
#import "IGModHook.h"

// --- story seen receipt ------------------------------------------------------

static void hookSeenStateUploader(Class cls) {
    if (!cls) return;
    __block IMP origInit = NULL;
    origInit = igHookInstance(cls, @selector(initWithUserSessionPK:networker:),
        ^id(id self, id pk, id networker) {
            if (igEnabled(kIGNoStorySeen)) return nil;
            return origInit ? ((id (*)(id, SEL, id, id))origInit)(self, @selector(initWithUserSessionPK:networker:), pk, networker) : nil;
        });
    __block IMP origNet = NULL;
    origNet = igHookInstance(cls, @selector(networker),
        ^id(id self) {
            if (igEnabled(kIGNoStorySeen)) return nil;
            return origNet ? ((id (*)(id, SEL))origNet)(self, @selector(networker)) : nil;
        });
}

// --- typing status -----------------------------------------------------------

static void hookTypingStatusService(Class cls) {
    if (!cls) return;
    __block IMP orig = NULL;
    orig = igHookInstance(cls, @selector(updateOutgoingStatusIsActive:threadKey:threadMetadata:typingStatusType:),
        ^void(id self, BOOL active, id key, id metadata, long long type) {
            if (igEnabled(kIGNoTypingStatus)) return; // stay silent
            if (orig) ((void (*)(id, SEL, BOOL, id, id, long long))orig)(
                self, @selector(updateOutgoingStatusIsActive:threadKey:threadMetadata:typingStatusType:),
                active, key, metadata, type);
        });
}

// --- screenshot alerts --------------------------------------------------------

static void hookScreenshotObserverProperty(Class cls) {
    if (!cls) return;
    __block IMP orig = NULL;
    orig = igHookInstance(cls, @selector(screenshotObserver),
        ^id(id self) {
            if (igEnabled(kIGNoScreenshotAlerts)) return nil;
            return orig ? ((id (*)(id, SEL))orig)(self, @selector(screenshotObserver)) : nil;
        });
}

static void hookObserverNilInit(Class cls, SEL sel) {
    if (!cls) return;
    if (sel == @selector(initForController:)) {
        __block IMP orig = NULL;
        orig = igHookInstance(cls, sel,
            ^id(id self, id controller) {
                if (igEnabled(kIGNoScreenshotAlerts)) return nil;
                return orig ? ((id (*)(id, SEL, id))orig)(self, sel, controller) : nil;
            });
        return;
    }
    if (sel == @selector(initWithUserSession:entryPoint:)) {
        __block IMP orig = NULL;
        orig = igHookInstance(cls, sel,
            ^id(id self, id session, long long entryPoint) {
                if (igEnabled(kIGNoScreenshotAlerts)) return nil;
                return orig ? ((id (*)(id, SEL, id, long long))orig)(self, sel, session, entryPoint) : nil;
            });
        return;
    }
}

// Delegate methods — present on IGStoryViewerViewController,
// IGDirectVisualMessageViewerController and
// IGDirectAggregatedMediaViewerViewController in 442.0.0.
static void hookScreenshotDelegate(Class cls) {
    if (!cls) return;
    __block IMP origTaken = NULL;
    origTaken = igHookInstance(cls, @selector(screenshotObserverDidSeeScreenshotTaken:),
        ^void(id self, id observer) {
            if (igEnabled(kIGNoScreenshotAlerts)) return;
            if (origTaken) ((void (*)(id, SEL, id))origTaken)(self, @selector(screenshotObserverDidSeeScreenshotTaken:), observer);
        });
    __block IMP origCapture = NULL;
    origCapture = igHookInstance(cls, @selector(screenshotObserverDidSeeActiveScreenCapture:event:),
        ^void(id self, id observer, long long event) {
            if (igEnabled(kIGNoScreenshotAlerts)) return;
            if (origCapture) ((void (*)(id, SEL, id, long long))origCapture)(self, @selector(screenshotObserverDidSeeActiveScreenCapture:event:), observer, event);
        });
}

void IGStoryPrivacyInit(void) {
    hookSeenStateUploader(NSClassFromString(@"IGStorySeenStateUploader"));
    hookTypingStatusService(NSClassFromString(@"IGDirectTypingStatusService"));
    hookScreenshotObserverProperty(NSClassFromString(@"IGViewController"));
    hookObserverNilInit(NSClassFromString(@"IGScreenshotObserver"), @selector(initForController:));
    hookObserverNilInit(NSClassFromString(@"IGDirectVisualMessageScreenshotSafetyLogger"), @selector(initWithUserSession:entryPoint:));

    Class viewerContainer = NSClassFromString(@"IGStoryViewerContainerView");
    if (viewerContainer) {
        __block IMP origBlock = NULL;
        origBlock = igHookInstance(viewerContainer, @selector(setShouldBlockScreenshot:viewModel:),
            ^void(id self, BOOL block, id viewModel) {
                if (igEnabled(kIGNoScreenshotAlerts)) return; // don't block screenshots
                if (origBlock) ((void (*)(id, SEL, BOOL, id))origBlock)(self, @selector(setShouldBlockScreenshot:viewModel:), block, viewModel);
            });
    }

    hookScreenshotDelegate(NSClassFromString(@"IGStoryViewerViewController"));
    hookScreenshotDelegate(NSClassFromString(@"IGDirectVisualMessageViewerController"));
    hookScreenshotDelegate(NSClassFromString(@"IGDirectAggregatedMediaViewerViewController"));
}
