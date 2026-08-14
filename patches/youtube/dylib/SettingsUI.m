// SettingsUI.m — in-app "YTFreedom" settings section (port of YouMod's
// Settings.x + YouModPerferences.x). Inserts a new category into the
// app's own Settings (YTSettingsGroupData / YTAppSettingsPresentationData),
// builds the section items via YTSettingsSectionItem factories, and pushes
// sub-sections with YTSettingsPickerViewController. All classes and
// selectors verified present in the 21.32.4 binary (forge hooks +
// strings); runtime-only calls are guarded where noted.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

static const NSInteger YTFreedomSection = 'ytfr';

// Runtime-called factories/objects that exist only in the YouTube binary;
// declared here so clang allows the dynamic dispatch.
@protocol YTFreedomSettingsItemFactory <NSObject>
+ (id)itemWithTitle:(NSString *)title titleDescription:(NSString *)desc
    accessibilityIdentifier:(NSString *)aid detailTextBlock:(id)block selectBlock:(id)sel;
+ (id)switchItemWithTitle:(NSString *)title titleDescription:(NSString *)desc
    accessibilityIdentifier:(NSString *)aid switchOn:(BOOL)on switchBlock:(id)block settingItemId:(long long)sid;
+ (id)checkmarkItemWithTitle:(NSString *)title titleDescription:(NSString *)desc selectBlock:(id)sel;
@end

@protocol YTFreedomSettingsPicker <NSObject>
- (id)initWithNavTitle:(NSString *)title pickerSectionTitle:(NSString *)pst rows:(NSArray *)rows
    selectedItemIndex:(NSUInteger)idx parentResponder:(id)pr;
@end

@protocol YTFreedomSettingsVC <NSObject>
- (void)setSectionItems:(id)items forCategory:(NSInteger)category title:(id)title icon:(id)icon
    titleDescription:(id)desc headerHidden:(BOOL)hidden;
- (void)pushViewController:(id)vc;
- (void)reloadData;
@end

@protocol YTFreedomSettingsManager <NSObject>
- (void)updateYTFreedomSectionWithEntry:(id)entry;
- (id)parentResponder;
@end

@protocol YTFreedomAlertFactory <NSObject>
+ (id)infoDialog;
+ (id)confirmationDialogWithAction:(void (^)(void))action actionTitle:(NSString *)title;
@end

@protocol YTFreedomToastFactory <NSObject>
+ (id)eventWithMessage:(NSString *)message firstResponder:(id)responder;
- (void)send;
@end

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

static id YTFItem(NSString *title, NSString *desc, BOOL (^select)(id cell, NSUInteger arg)) {
    Class itemCls = NSClassFromString(@"YTSettingsSectionItem");
    if (!itemCls) return nil;
    return [(id<YTFreedomSettingsItemFactory>)itemCls itemWithTitle:title
                titleDescription:desc
          accessibilityIdentifier:nil
                detailTextBlock:nil
                     selectBlock:select];
}

static id YTFSwitchItem(NSString *title, NSString *desc, NSString *key) {
    Class itemCls = NSClassFromString(@"YTSettingsSectionItem");
    if (!itemCls) return nil;
    return [(id<YTFreedomSettingsItemFactory>)itemCls switchItemWithTitle:title
                      titleDescription:desc
                accessibilityIdentifier:nil
                              switchOn:IS_ENABLED(key)
                            switchBlock:^BOOL(id cell, BOOL enabled) {
                                SET_BOOL(key, enabled);
                                return YES;
                            }
                          settingItemId:0];
}

static id YTFHeaderItem(NSString *desc) {
    return YTFItem(nil, desc, ^BOOL(id cell, NSUInteger arg) { return NO; });
}

static id YTFIcon(int type) {
    Class iconCls = NSClassFromString(@"YTIIcon");
    if (!iconCls) return nil;
    id<YTFreedomIconHooks> icon = [iconCls new];
    icon.iconType = type;
    return (id)icon;
}

static void YTFPushPicker(id manager, id settingsVC, NSString *title, NSArray *rows) {
    Class pickerCls = NSClassFromString(@"YTSettingsPickerViewController");
    if (!pickerCls || !settingsVC) return;
    id picker = [(id<YTFreedomSettingsPicker>)[pickerCls alloc] initWithNavTitle:title
                                 pickerSectionTitle:nil
                                               rows:rows
                                  selectedItemIndex:0
                                     parentResponder:[(id<YTFreedomSettingsManager>)manager parentResponder]];
    [(id<YTFreedomSettingsVC>)settingsVC pushViewController:picker];
}

static NSString *cacheSizeString(void) {
    NSString *cachePath = NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject;
    NSArray *files = [[NSFileManager defaultManager] subpathsOfDirectoryAtPath:cachePath error:nil];
    unsigned long long total = 0;
    for (NSString *name in files) {
        NSString *path = [cachePath stringByAppendingPathComponent:name];
        NSDictionary *attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:path error:nil];
        total += [attrs fileSize];
    }
    NSByteCountFormatter *fmt = [NSByteCountFormatter new];
    fmt.countStyle = NSByteCountFormatterCountStyleFile;
    return [fmt stringFromByteCount:total];
}

static void clearAppCache(void) {
    NSString *cachePath = NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject;
    [[NSFileManager defaultManager] removeItemAtPath:cachePath error:nil];
}

// ---------------------------------------------------------------------------
// Preferences manager (import / export / reset)
// ---------------------------------------------------------------------------
@interface YTFreedomPrefsManager : NSObject <UIDocumentPickerDelegate>
@end

@implementation YTFreedomPrefsManager

+ (instancetype)sharedManager {
    static YTFreedomPrefsManager *shared;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ shared = [self new]; });
    return shared;
}

- (void)importFromVC:(UIViewController *)vc {
    UIDocumentPickerViewController *picker =
        [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypePropertyList, UTTypeData]
                                                                   asCopy:YES];
    picker.delegate = self;
    picker.modalPresentationStyle = UIModalPresentationFormSheet;
    [vc presentViewController:picker animated:YES completion:nil];
}

- (void)exportFromVC:(UIViewController *)vc {
    NSMutableDictionary *ours = [NSMutableDictionary dictionary];
    for (NSString *key in [[NSUserDefaults standardUserDefaults] dictionaryRepresentation]) {
        if ([key hasPrefix:@"YTFreedom"]) ours[key] = [[NSUserDefaults standardUserDefaults] objectForKey:key];
    }
    if (ours.count == 0) {
        [self showAlert:@"Export" subtitle:@"No YTFreedom settings to export." action:NO];
        return;
    }
    NSString *tmp = [NSTemporaryDirectory() stringByAppendingPathComponent:@"YTFreedom_Preferences.plist"];
    [ours writeToFile:tmp atomically:YES];
    UIDocumentPickerViewController *picker =
        [[UIDocumentPickerViewController alloc] initForExportingURLs:@[[NSURL fileURLWithPath:tmp]] asCopy:YES];
    picker.modalPresentationStyle = UIModalPresentationFormSheet;
    [vc presentViewController:picker animated:YES completion:nil];
}

- (void)restoreDefaults {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    for (NSString *key in [defaults dictionaryRepresentation]) {
        if ([key hasPrefix:@"YTFreedom"]) [defaults removeObjectForKey:key];
    }
    [defaults synchronize];
    exit(0);
}

- (void)showAlert:(NSString *)title subtitle:(NSString *)subtitle action:(BOOL)confirm {
    Class alertCls = NSClassFromString(@"YTAlertView");
    if (!alertCls) return;
    id<YTFreedomAlertHooks> alert = confirm
        ? [(id<YTFreedomAlertFactory>)alertCls confirmationDialogWithAction:^{ [self restoreDefaults]; } actionTitle:@"Yes"]
        : [(id<YTFreedomAlertFactory>)alertCls infoDialog];
    alert.title = title;
    alert.subtitle = subtitle;
    [alert show];
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller
    didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
    NSURL *fileURL = urls.firstObject;
    if (!fileURL) return;
    NSDictionary *data = [NSDictionary dictionaryWithContentsOfURL:fileURL];
    if (![data isKindOfClass:[NSDictionary class]]) {
        [self showAlert:@"Import" subtitle:@"Invalid file." action:NO];
        return;
    }
    BOOL found = NO;
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    for (NSString *key in [defaults dictionaryRepresentation]) {
        if ([key hasPrefix:@"YTFreedom"]) [defaults removeObjectForKey:key];
    }
    for (NSString *key in data) {
        if ([key hasPrefix:@"YTFreedom"]) { [defaults setObject:data[key] forKey:key]; found = YES; }
    }
    [defaults synchronize];
    if (!found) {
        [self showAlert:@"Import" subtitle:@"No YTFreedom keys found in file." action:NO];
        return;
    }
    [self showAlert:@"Import done" subtitle:@"Restart to apply." action:NO];
}

@end

// ---------------------------------------------------------------------------
// Section builder
// ---------------------------------------------------------------------------

static void buildYTFreedomSection(id manager) {
    Class itemCls = NSClassFromString(@"YTSettingsSectionItem");
    if (!itemCls) return;
    id settingsVC = [manager valueForKey:@"_settingsViewControllerDelegate"];
    if (!settingsVC) return;

    NSMutableArray *items = [NSMutableArray array];

    // Version
    [items addObject:YTFItem([NSString stringWithFormat:@"YTFreedom v%@", YTFREEDOM_VERSION], nil,
                             ^BOOL(id cell, NSUInteger arg) { return NO; })];

    // Downloading
    id downloading = YTFItem(@"Downloading", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Downloading", @[
            YTFHeaderItem(@"Downloading"),
            YTFSwitchItem(@"Download Manager", @"Adds a download button to the player", KDownloadManager),
            YTFSwitchItem(@"Save to Photos", @"Save downloads to the Photos library", KDownloadSaveToPhotos),
            YTFSwitchItem(@"Prefer DRC audio", @"Prefer DRM-free audio tracks", KDownloadPreferDRCAudio),
        ]);
        return YES;
    });
    id<YTFreedomSettingsItemHooks> dIcon = downloading;
    dIcon.settingIcon = YTFIcon(57);
    [items addObject:downloading];

    // Appearance
    id appearance = YTFItem(@"Appearance", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Appearance", @[
            YTFHeaderItem(@"Appearance"),
            YTFSwitchItem(@"OLED theme", @"True black dark theme", KOLEDTheme),
            YTFSwitchItem(@"OLED keyboard", @"True black keyboard in dark mode", KOLEDKeyboard),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)appearance).settingIcon = YTFIcon(921);
    [items addObject:appearance];

    // Navbar
    id navbar = YTFItem(@"Navigation bar", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Navigation bar", @[
            YTFHeaderItem(@"Navigation bar"),
            YTFSwitchItem(@"Hide YT logo", @"Hide the YouTube logo in the header", KHideYTLogo),
            YTFSwitchItem(@"Premium logo", @"Use the premium-style logo", KPremiumLogo),
            YTFSwitchItem(@"Hide notification button", nil, KHideNoti),
            YTFSwitchItem(@"Hide search button", nil, KHideSearch),
            YTFSwitchItem(@"Hide voice search button", nil, KHideVoiceSearch),
            YTFSwitchItem(@"Hide cast button", nil, KHideCastButtonNav),
            YTFSwitchItem(@"Sticky navigation bar", nil, KStickyNavbar),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)navbar).settingIcon = YTFIcon(60);
    [items addObject:navbar];

    // Feed
    id feed = YTFItem(@"Feed", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Feed", @[
            YTFHeaderItem(@"Feed"),
            YTFSwitchItem(@"Hide sub bar", @"Hide the channel filter bar", KHideSubbar),
            YTFSwitchItem(@"Hide music playlists shelf", nil, KHideGenMusicShelf),
            YTFSwitchItem(@"Hide feed posts", nil, KHideFeedPost),
            YTFSwitchItem(@"Hide Shorts shelf", nil, KHideShortsShelf),
            YTFSwitchItem(@"Hide search history", nil, KHideSearchHis),
            YTFSwitchItem(@"Hide related videos", @"Hide related videos on watch page", KNoRelatedVideos),
            YTFSwitchItem(@"Hide subscribe button", nil, KHideSubButton),
            YTFSwitchItem(@"Hide shop button", nil, KHideShoppingButton),
            YTFSwitchItem(@"Hide memberships button", nil, KHideMemberButton),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)feed).settingIcon = YTFIcon(193);
    [items addObject:feed];

    // Player
    id player = YTFItem(@"Player", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Player", @[
            YTFHeaderItem(@"Player"),
            YTFSwitchItem(@"Hide autoplay toggle", nil, KHideAutoPlayToggle),
            YTFSwitchItem(@"Hide captions button", nil, KHideCaptionsButton),
            YTFSwitchItem(@"Hide cast button", nil, KHideCastButtonPlayer),
            YTFSwitchItem(@"Hide previous button", nil, KHidePrevButton),
            YTFSwitchItem(@"Hide next button", nil, KHideNextButton),
            YTFSwitchItem(@"Replace prev/next with rewind/ffw", nil, KReplacePrevNextButtons),
            YTFSwitchItem(@"Remove dark overlay", @"Remove the gradient behind controls", KRemoveDarkOverlay),
            YTFSwitchItem(@"Hide endscreen cards", nil, KHideEndScreenCards),
            YTFSwitchItem(@"Hide suggested video on finish", nil, KHideSuggestedVideo),
            YTFSwitchItem(@"Hide paid promo overlay", nil, KHidePaidPromoOverlay),
            YTFSwitchItem(@"Hide watermark", nil, KHideWaterMark),
            YTFSwitchItem(@"Gesture controls", @"Edge swipes: brightness/volume/speed", KGestureControls),
            YTFSwitchItem(@"Disable double-tap seek", nil, KDisablesDoubleTap),
            YTFSwitchItem(@"Disable long-press", nil, KDisablesLongHold),
            YTFSwitchItem(@"Exit fullscreen on finish", nil, KAutoExitFullScreen),
            YTFSwitchItem(@"Auto-disable captions", nil, KDisablesCaptions),
            YTFSwitchItem(@"Disable remaining-time toggle", nil, KDisablesShowRemaining),
            YTFSwitchItem(@"Always show remaining time", nil, KAlwaysShowRemaining),
            YTFSwitchItem(@"Hide fullscreen actions", nil, KHideFullAction),
            YTFSwitchItem(@"Hide fullscreen title", nil, KHideFullvidTitle),
            YTFSwitchItem(@"Stop autoplay", nil, KStopAutoplayVideo),
            YTFSwitchItem(@"Skip content warning", @"Auto-confirm age/content warnings", KHideContentWarning),
            YTFSwitchItem(@"Auto fullscreen", nil, KAutoFullScreen),
            YTFSwitchItem(@"Portrait fullscreen", nil, KPortFull),
            YTFSwitchItem(@"Old quality picker", nil, KOldQualityPicker),
            YTFSwitchItem(@"Extra speeds (0.25x-10x)", nil, KExtraSpeed),
            YTFSwitchItem(@"Mute button in player", @"Adds a mute control (new-IPA flag)", KMuteButtonPlayer),
            YTFSwitchItem(@"Pinch to fullscreen", @"Restore the pinch-to-fullscreen gesture", KPinchToFullscreen),
            YTFSwitchItem(@"Tap progress bar to seek", @"Restore tap-to-seek on the scrubber", KTapToSeek),
            YTFSwitchItem(@"Hide player heatmap", @"Remove the red popularity heatmap", KHidePlayerHeatmap),
            YTFSwitchItem(@"Inline chapter seek", @"Tap chapters/segments to seek inline", KChapterSeek),
            YTFSwitchItem(@"Reduce player overlays", @"Reveal YouTube's reduce-overlays setting", KReduceOverlays),
            YTFSwitchItem(@"High-quality audio setting", @"Reveal the audio-quality setting", KHQAAudio),
            YTFSwitchItem(@"Animated previews setting", @"Reveal the animated-preview setting", KAnimatedPreviews),
            YTFSwitchItem(@"Disable pull-to-fullscreen", @"Stop overscroll from entering fullscreen", KDisablePullToFull),
            YTFSwitchItem(@"Red progress bar", @"Resting bar color becomes red", KRedProgressBar),
            YTFSwitchItem(@"Copy timestamped link on pause", @"Copies watch URL with current time", KCopyTimestampedLink),
            YTFSwitchItem(@"Disable hints", nil, KDisableHints),
            YTFSwitchItem(@"Force miniplayer", nil, KForceMiniPlayer),
            YTFSwitchItem(@"Always show seekbar", nil, KAlwaysShowSeekbar),
            YTFSwitchItem(@"Hide like button", nil, KHideLikeButton),
            YTFSwitchItem(@"Hide dislike button", nil, KHideDisLikeButton),
            YTFSwitchItem(@"Hide share button", nil, KHideShareButton),
            YTFSwitchItem(@"Hide download button", nil, KHideDownloadButton),
            YTFSwitchItem(@"Hide clip button", nil, KHideClipButton),
            YTFSwitchItem(@"Hide remix button", nil, KHideRemixButton),
            YTFSwitchItem(@"Hide save button", nil, KHideSaveButton),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)player).settingIcon = YTFIcon(658);
    [items addObject:player];

    // Shorts
    id shorts = YTFItem(@"Shorts", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Shorts", @[
            YTFHeaderItem(@"Shorts"),
            YTFSwitchItem(@"Hide like button", nil, KHideShortsLikeButton),
            YTFSwitchItem(@"Hide dislike button", nil, KHideShortsDisLikeButton),
            YTFSwitchItem(@"Hide comment button", nil, KHideShortsCommentButton),
            YTFSwitchItem(@"Hide share button", nil, KHideShortsShareButton),
            YTFSwitchItem(@"Hide remix button", nil, KHideShortsRemixButton),
            YTFSwitchItem(@"Hide metadata button", nil, KHideShortsMetaButton),
            YTFSwitchItem(@"Hide products", nil, KHideShortsProducts),
            YTFSwitchItem(@"Hide rec bar", nil, KHideShortsRecbar),
            YTFSwitchItem(@"Hide commit pill", nil, KHideShortsCommit),
            YTFSwitchItem(@"Hide subscribe button", nil, KHideShortsSubscriptButton),
            YTFSwitchItem(@"Hide live button", nil, KHideShortsLiveButton),
            YTFSwitchItem(@"Hide lens button", nil, KHideShortsLensButton),
            YTFSwitchItem(@"Hide trends button", nil, KHideShortsTrendsButton),
            YTFSwitchItem(@"Hide 'to video' pill", nil, KHideShortsToVideo),
            YTFSwitchItem(@"Enable quality selector", nil, KEnablesShortsQuality),
            YTFSwitchItem(@"Show seekbar", nil, KShowShortsSeekbar),
            YTFSwitchItem(@"Playback speed from menu", @"⋯ menu gains speed options (new-IPA flag)", KShortsPlaybackSpeed),
            YTFSwitchItem(@"Inline playback on Shorts shelf", @"Play Shorts inline in the feed", KInlineShortsPlayback),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)shorts).settingIcon = YTFIcon(769);
    [items addObject:shorts];

    // Tab bar
    id tabbar = YTFItem(@"Tab bar", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Default tab", @[
            YTFHeaderItem(@"Default tab"),
            [(id<YTFreedomSettingsItemFactory>)itemCls checkmarkItemWithTitle:@"Home" titleDescription:nil
                               selectBlock:^BOOL(id c, NSUInteger a) { SET_INT(KDefaultTab, 0); return YES; }],
            [(id<YTFreedomSettingsItemFactory>)itemCls checkmarkItemWithTitle:@"Shorts" titleDescription:nil
                               selectBlock:^BOOL(id c, NSUInteger a) { SET_INT(KDefaultTab, 1); return YES; }],
            [(id<YTFreedomSettingsItemFactory>)itemCls checkmarkItemWithTitle:@"Subscriptions" titleDescription:nil
                               selectBlock:^BOOL(id c, NSUInteger a) { SET_INT(KDefaultTab, 2); return YES; }],
            [(id<YTFreedomSettingsItemFactory>)itemCls checkmarkItemWithTitle:@"Library" titleDescription:nil
                               selectBlock:^BOOL(id c, NSUInteger a) { SET_INT(KDefaultTab, 3); return YES; }],
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)tabbar).settingIcon = YTFIcon(66);
    [items addObject:tabbar];

    // Miscellaneous
    id misc = YTFItem(@"Miscellaneous", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Miscellaneous", @[
            YTFHeaderItem(@"Miscellaneous"),
            YTFSwitchItem(@"Background playback", @"Audio continues with screen off", KBackgroundPlayback),
            YTFSwitchItem(@"Disable Shorts PiP", nil, KDisablesShortsPiP),
            YTFSwitchItem(@"Block upgrade dialogs", nil, KBlockUpgradeDialogs),
            YTFSwitchItem(@"Hide 'Are you there?' dialog", nil, KHideAreYouThereDialog),
            YTFSwitchItem(@"Fix slow miniplayer", nil, KFixesSlowMiniPlayer),
            YTFSwitchItem(@"Disable new miniplayer", nil, KDisablesNewMiniPlayer),
            YTFSwitchItem(@"Disable snackbar", nil, KDisablesSnackBar),
            YTFSwitchItem(@"Hide startup animations", nil, KHideStartupAni),
            YTFSwitchItem(@"Hide 'Play next in queue'", nil, KHidePlayInNextQueue),
            YTFSwitchItem(@"Hide like/dislike votes", @"Silent voting", KHideLikeDislikeVotes),
            YTFSwitchItem(@"Disable rate prompts", @"Never ask to rate the app", KDisableRatePrompts),
            YTFSwitchItem(@"Hide HUD/toast messages", @"Suppress like-saved style toasts", KHideHUDMessages),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)misc).settingIcon = YTFIcon(1101);
    [items addObject:misc];

    // Menu
    id menu = YTFItem(@"Menu items", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Menu items", @[
            YTFHeaderItem(@"Menu items"),
            YTFSwitchItem(@"Remove Download", nil, KRemoveDownloadMenu),
            YTFSwitchItem(@"Remove Watch later", nil, KRemoveWatchLaterMenu),
            YTFSwitchItem(@"Remove Save to playlist", nil, KRemoveSaveToPlaylistMenu),
            YTFSwitchItem(@"Remove Share", nil, KRemoveShareMenu),
            YTFSwitchItem(@"Remove Not interested", nil, KRemoveNotInterestedMenu),
            YTFSwitchItem(@"Remove Don't recommend channel", nil, KRemoveDontRecommendMenu),
            YTFSwitchItem(@"Remove Report", nil, KRemoveReportMenu),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)menu).settingIcon = YTFIcon(120);
    [items addObject:menu];

    // Preferences
    id prefs = YTFItem(@"Preferences", nil, ^BOOL(id cell, NSUInteger arg) {
        YTFPushPicker(manager, settingsVC, @"Preferences", @[
            YTFHeaderItem(@"Preferences"),
            YTFItem(@"Import settings", @"Restore from an exported file", ^BOOL(id c, NSUInteger a) {
                [[YTFreedomPrefsManager sharedManager] importFromVC:settingsVC];
                return YES;
            }),
            YTFItem(@"Export settings", @"Save all YTFreedom settings", ^BOOL(id c, NSUInteger a) {
                [[YTFreedomPrefsManager sharedManager] exportFromVC:settingsVC];
                return YES;
            }),
            YTFItem(@"Restore defaults", nil, ^BOOL(id c, NSUInteger a) {
                [[YTFreedomPrefsManager sharedManager] showAlert:@"Warning"
                                                       subtitle:@"Reset all YTFreedom settings?"
                                                          action:YES];
                return YES;
            }),
            YTFHeaderItem(@"Cache"),
            YTFItem(@"Clear cache", cacheSizeString(), ^BOOL(id c, NSUInteger a) {
                dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
                    clearAppCache();
                    dispatch_async(dispatch_get_main_queue(), ^{
                        Class toastCls = NSClassFromString(@"YTToastResponderEvent");
                        if (toastCls) {
                            id event = [(id<YTFreedomToastFactory>)toastCls eventWithMessage:@"Cache cleared"
                                                                                firstResponder:[(id<YTFreedomSettingsManager>)manager parentResponder]];
                            [event send];
                        }
                    });
                });
                return YES;
            }),
            YTFSwitchItem(@"Auto-clear cache", @"Clear cache on launch", KAutoClearCache),
        ]);
        return YES;
    });
    ((id<YTFreedomSettingsItemHooks>)prefs).settingIcon = YTFIcon(530);
    [items addObject:prefs];

    if ([settingsVC respondsToSelector:@selector(setSectionItems:forCategory:title:icon:titleDescription:headerHidden:)]) {
        [(id<YTFreedomSettingsVC>)settingsVC setSectionItems:items
                        forCategory:YTFreedomSection
                              title:@"YTFreedom"
                               icon:YTFIcon(658)
                  titleDescription:nil
                      headerHidden:NO];
    } else {
        os_log(ytfLog(), "YTFreedom: settings VC lacks setSectionItems:... — section not shown");
    }
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

static void hookCategoryInjection(void) {
    static IMP orig_orderedCategories;
    orig_orderedCategories = ytfHookInstance(NSClassFromString(@"YTSettingsGroupData"),
        @selector(orderedCategories),
        ^id(id self) {
            // Only for the settings group (type 1); avoid double-insert if
            // another tweak already installed a section.
            if ([[self valueForKey:@"type"] integerValue] != 1
                || class_getClassMethod(NSClassFromString(@"YTSettingsGroupData"), @selector(tweaks)))
                return ((id(*)(id, SEL))orig_orderedCategories)(self, @selector(orderedCategories));
            NSMutableArray *cats = [((id(*)(id, SEL))orig_orderedCategories)(self, @selector(orderedCategories)) mutableCopy];
            if (![cats containsObject:@(YTFreedomSection)])
                [cats insertObject:@(YTFreedomSection) atIndex:0];
            return cats;
        });
    (void)orig_orderedCategories;

    static IMP orig_settingsCategoryOrder;
    orig_settingsCategoryOrder = ytfHookClass(NSClassFromString(@"YTAppSettingsPresentationData"),
        @selector(settingsCategoryOrder),
        ^id(id cls) {
            NSArray *order = ((id(*)(id, SEL))orig_settingsCategoryOrder)(cls, @selector(settingsCategoryOrder));
            if ([order containsObject:@(YTFreedomSection)]) return order;
            NSMutableArray *mutable = [order mutableCopy];
            NSUInteger idx = [mutable indexOfObject:@(1)];
            if (idx != NSNotFound)
                [mutable insertObject:@(YTFreedomSection) atIndex:idx + 1];
            else
                [mutable insertObject:@(YTFreedomSection) atIndex:0];
            return mutable;
        });
    (void)orig_settingsCategoryOrder;
}

static void hookSectionItemManager(void) {
    // %new: route the YTFreedom category to our builder.
    ytfAddInstanceMethod(NSClassFromString(@"YTSettingsSectionItemManager"),
        sel_registerName("updateYTFreedomSectionWithEntry:"),
        ^void(id self, id entry) { buildYTFreedomSection(self); }, "v@:@");

    static IMP orig_updateSection;
    orig_updateSection = ytfHookInstance(NSClassFromString(@"YTSettingsSectionItemManager"),
        @selector(updateSectionForCategory:withEntry:),
        ^void(id self, NSUInteger category, id entry) {
            if (category == (NSUInteger)YTFreedomSection) {
                [(id<YTFreedomSettingsManager>)self updateYTFreedomSectionWithEntry:entry];
                return;
            }
            ((void(*)(id, SEL, NSUInteger, id))orig_updateSection)(
                self, @selector(updateSectionForCategory:withEntry:), category, entry);
        });
    (void)orig_updateSection;
}

void YTFreedomSettingsUIInit(void) {
    hookCategoryInjection();
    hookSectionItemManager();

    // Auto-clear cache on launch.
    if (IS_ENABLED(KAutoClearCache)) {
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
            clearAppCache();
        });
    }
}
