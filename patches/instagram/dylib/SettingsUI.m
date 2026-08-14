// SettingsUI.m — IGMod settings screen + entry points.
//
// Entry points (both verified in 442.0.0):
//   - long-press the home tab button (IGTabBarButton, "mainfeed-tab" — the
//     identifier SCInsta used; if it drifts, the 4-finger hold still works)
//   - 4-finger hold anywhere (IGRootViewController, the reliable fallback)
// The table is plain UIKit — no third-party UI.
#import "IGModHook.h"

@interface IGModSettingsViewController : UITableViewController
@end

@implementation IGModSettingsViewController

static NSString *const kSwitchCell = @"igmod-switch";

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"IGMod";
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc]
        initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done)];
    [self.tableView registerClass:UITableViewCell.class forCellReuseIdentifier:kSwitchCell];
}

- (void)done { [self dismissViewControllerAnimated:YES completion:nil]; }

typedef struct { NSString *key; const char *title; const char *detail; BOOL def; } SwitchSpec;
typedef struct { const char *title; SwitchSpec *items; NSUInteger count; } SectionSpec;

static SwitchSpec sGeneral[] = {
    { kIGHideAds, "Hide ads", "Removes feed ads and kills the ad response parsers", YES },
    { kIGHideStoryTray, "Hide stories tray", "Removes the stories tray from the home feed", NO },
    { kIGNoSuggestedPosts, "No suggested posts", "Hides 'suggested for you' posts in the feed", NO },
    { kIGNoSuggestedReels, "No suggested reels", "Hides the suggested reels carousel", NO },
    { kIGNoSuggestedAccounts, "No suggested accounts", "Hides suggested accounts in the feed", NO },
};
static SectionSpec sSections[] = {
    { "Feed", sGeneral, 5 },
};

static SwitchSpec sPrivacy[] = {
    { kIGNoStorySeen, "No story seen receipt", "View stories without notifying the author", NO },
    { kIGNoTypingStatus, "No typing indicator", "Send DMs without showing the typing bubble", NO },
    { kIGNoScreenshotAlerts, "No screenshot alerts", "Disables screenshot detection in stories/DMs", YES },
};
static SectionSpec sSections2[] = {
    { "Privacy", sPrivacy, 3 },
};

static SwitchSpec sDownloads[] = {
    { kIGFeedDownload, "Save feed posts", "Long-press any feed photo/video to share or save", YES },
    { kIGStoryDownload, "Save stories", "Long-press a story photo/video to share or save", YES },
    { kIGProfilePicDownload, "Save profile pictures", "Long-press a profile picture to share or save", YES },
    { kIGCopyCaptions, "Copy captions", "Long-press a caption to copy it", YES },
};
static SectionSpec sSections3[] = {
    { "Media", sDownloads, 4 },
};

static SwitchSpec sMisc[] = {
    { kIGDisableSafeMode, "Disable safe mode", "Stops Instagram's crash-loop safe mode from resetting things", NO },
    { kIGSettingsShortcut, "Home-tab settings shortcut", "Long-press the home tab to open settings", YES },
    { kIGSettingsFourFinger, "4-finger settings hold", "Hold 4 fingers on any screen to open settings", YES },
};
static SectionSpec sSections4[] = {
    { "Misc", sMisc, 3 },
};

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 4; }

- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    switch (section) {
        case 0: return @"Feed";
        case 1: return @"Privacy";
        case 2: return @"Media";
        default: return @"Misc";
    }
}

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    switch (section) {
        case 0: return 5;
        case 1: return 3;
        case 2: return 4;
        default: return 3;
    }
}

- (const SwitchSpec *)specForIndexPath:(NSIndexPath *)ip {
    switch (ip.section) {
        case 0: return &sGeneral[ip.row];
        case 1: return &sPrivacy[ip.row];
        case 2: return &sDownloads[ip.row];
        default: return &sMisc[ip.row];
    }
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:kSwitchCell forIndexPath:indexPath];
    const SwitchSpec *spec = [self specForIndexPath:indexPath];
    cell.textLabel.text = @(spec->title);
    cell.textLabel.adjustsFontSizeToFitWidth = YES;
    cell.detailTextLabel.text = @(spec->detail);
    cell.detailTextLabel.numberOfLines = 0;
    UISwitch *sw = [[UISwitch alloc] init];
    NSString *key = spec->key;
    sw.on = [[NSUserDefaults standardUserDefaults] boolForKey:key];
    sw.tag = indexPath.row + 100 * indexPath.section;
    [sw addTarget:self action:@selector(toggled:) forControlEvents:UIControlEventValueChanged];
    cell.accessoryView = sw;
    return cell;
}

- (void)toggled:(UISwitch *)sw {
    // Recover section/row from the tag (see cellForRowAtIndexPath).
    NSInteger section = sw.tag / 100, row = sw.tag % 100;
    const SwitchSpec *spec = nil;
    switch (section) {
        case 0: spec = &sGeneral[row]; break;
        case 1: spec = &sPrivacy[row]; break;
        case 2: spec = &sDownloads[row]; break;
        default: spec = &sMisc[row]; break;
    }
    [[NSUserDefaults standardUserDefaults] setBool:sw.on forKey:spec->key];
}

@end

// --- entry points --------------------------------------------------------------

static void igPresentSettings(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        UIViewController *top = igTopMostViewController();
        if (!top) return;
        IGModSettingsViewController *settings = [IGModSettingsViewController new];
        UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:settings];
        nav.modalPresentationStyle = UIModalPresentationFullScreen;
        [top presentViewController:nav animated:YES completion:nil];
    });
}

// Gesture target for the settings entry points (long-press home tab / 4-finger
// hold): presents the settings screen when the gesture fires.
@interface IGSettingsPressTarget : NSObject
- (void)fire:(UILongPressGestureRecognizer *)sender;
@end

@implementation IGSettingsPressTarget
- (void)fire:(UILongPressGestureRecognizer *)sender {
    if (sender.state != UIGestureRecognizerStateBegan) return;
    igPresentSettings();
}
@end

void IGSettingsInit(void) {
    // 1) Long-press the home tab (IGTabBarButton, verified).
    if (igEnabled(kIGSettingsShortcut)) {
        Class tabBtn = NSClassFromString(@"IGTabBarButton");
        if (tabBtn) {
            __block IMP orig = NULL;
            orig = igHookInstance(tabBtn, @selector(didMoveToSuperview),
                ^void(id self) {
                    if (orig) ((void (*)(id, SEL))orig)(self, @selector(didMoveToSuperview));
                    NSString *aid = ((UIView *)self).accessibilityIdentifier;
                    if (![aid isEqualToString:@"mainfeed-tab"]) return;
                    for (UIGestureRecognizer *g in ((UIView *)self).gestureRecognizers) {
                        if ([g isKindOfClass:UILongPressGestureRecognizer.class]) return;
                    }
                    UILongPressGestureRecognizer *lp = [[UILongPressGestureRecognizer alloc]
                        initWithTarget:[[IGSettingsPressTarget alloc] init] action:@selector(fire:)];
                    lp.minimumPressDuration = 0.4;
                    for (UIGestureRecognizer *existing in ((UIView *)self).gestureRecognizers) {
                        [existing requireGestureRecognizerToFail:lp];
                    }
                    [((UIView *)self) addGestureRecognizer:lp];
                });
        }
    }

    // 2) 4-finger hold anywhere (IGRootViewController — always works).
    if (igEnabled(kIGSettingsFourFinger)) {
        Class root = NSClassFromString(@"IGRootViewController");
        if (root) {
            __block IMP orig = NULL;
            orig = igHookInstance(root, @selector(viewDidLoad),
                ^void(id self) {
                    if (orig) ((void (*)(id, SEL))orig)(self, @selector(viewDidLoad));
                    UILongPressGestureRecognizer *lp = [[UILongPressGestureRecognizer alloc]
                        initWithTarget:[[IGSettingsPressTarget alloc] init] action:@selector(fire:)];
                    lp.minimumPressDuration = 1.0;
                    lp.numberOfTouchesRequired = 4;
                    [((UIViewController *)self).view addGestureRecognizer:lp];
                });
        }
    }
}
