// SettingsUI.m - in-app "YTFreedom" settings section (port of YouMod's
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

static BOOL ytfKeyNeedsRestart(NSString *key);
static void ytfShowRestartHint(void);
static void ytfMarkDirtyIfRestartNeeded(NSString *key);

static id YTFSwitchItem(NSString *title, NSString *desc, NSString *key) {
    Class itemCls = NSClassFromString(@"YTSettingsSectionItem");
    if (!itemCls) return nil;
    return [(id<YTFreedomSettingsItemFactory>)itemCls switchItemWithTitle:title
                      titleDescription:desc
                accessibilityIdentifier:nil
                              switchOn:IS_ENABLED(key)
                            switchBlock:^BOOL(id cell, BOOL enabled) {
                                SET_BOOL(key, enabled);
                                ytfMarkDirtyIfRestartNeeded(key);
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

// ---------------------------------------------------------------------------
// Restart-needed hints
// ---------------------------------------------------------------------------
// Keys whose hooks are installed (or only meaningful) at launch/init. When
// one of these flips in Settings, show a small auto-dismissing hint so the
// tester knows to relaunch instead of reporting a "broken" toggle.
static BOOL ytfKeyNeedsRestart(NSString *key) {
    // Restart requirement lives in the feature catalog (YTFFeatures.m) -
    // the single source of truth. Keys are read at launch/init (gated
    // hooks, config getters, launch-only effects).
    for (YTFFeatureSpec *spec in ytfFeatureSpecs())
        if (spec.restartRequired && [spec.key isEqualToString:key]) return YES;
    return NO;
}

static void ytfShowRestartHint(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        UIWindow *window = [UIApplication sharedApplication].windows.firstObject;
        if (!window) return;
        UIView *existing = [window viewWithTag:0x59F0];
        if (existing) [existing removeFromSuperview];
        UILabel *label = [[UILabel alloc] initWithFrame:CGRectZero];
        label.tag = 0x59F0;
        label.text = @"Restart to apply";
        label.font = [UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
        label.textColor = [UIColor whiteColor];
        label.backgroundColor = [[UIColor blackColor] colorWithAlphaComponent:0.85];
        label.layer.cornerRadius = 14.0;
        label.clipsToBounds = YES;
        label.textAlignment = NSTextAlignmentCenter;
        CGSize size = [label.text sizeWithAttributes:@{NSFontAttributeName: label.font}];
        CGFloat width = size.width + 32.0;
        label.frame = CGRectMake((window.bounds.size.width - width) / 2.0, 60.0, width, 30.0);
        label.alpha = 0.0;
        [window addSubview:label];
        [UIView animateWithDuration:0.25 animations:^{ label.alpha = 1.0; }];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.5 * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            [UIView animateWithDuration:0.35 animations:^{ label.alpha = 0.0; }
                             completion:^(BOOL finished) { [label removeFromSuperview]; }];
        });
    });
}

static void ytfMarkDirtyIfRestartNeeded(NSString *key) {
    if (ytfKeyNeedsRestart(key)) ytfShowRestartHint();
}

static void YTFPushPicker(id manager, id settingsVC, NSString *title, NSArray *rows, NSUInteger selectedIndex) {
    Class pickerCls = NSClassFromString(@"YTSettingsPickerViewController");
    if (!pickerCls || !settingsVC) return;
    id picker = [(id<YTFreedomSettingsPicker>)[pickerCls alloc] initWithNavTitle:title
                                 pickerSectionTitle:nil
                                               rows:rows
                                  selectedItemIndex:selectedIndex
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

// ---------------------------------------------------------------------------
// Section builder (table-driven - the catalog in YTFFeatures.m decides what
// renders, in what order, and with what defaults).
// ---------------------------------------------------------------------------

static NSInteger ytfGroupIcon(NSString *group) {
    if ([group isEqualToString:@"player"]) return 658;      // settings gear
    if ([group isEqualToString:@"appearance"]) return 921;  // palette
    if ([group isEqualToString:@"shorts"]) return 769;      // shorts
    if ([group isEqualToString:@"feed"]) return 193;        // filter
    if ([group isEqualToString:@"navigation"]) return 60;   // header
    if ([group isEqualToString:@"tabbar"]) return 66;       // tabs
    if ([group isEqualToString:@"advanced"]) return 495;    // YT_EXPERIMENT
    return 530;                                             // tune
}

// Choices for YTFFeatureChoices features: {label, stored value} pairs.
static NSArray *ytfChoicesFor(YTFFeatureSpec *spec) {
    if ([spec.key isEqualToString:KDefaultTab])
        return @[ @[@"Home", @0], @[@"Shorts", @1], @[@"Subscriptions", @2],
                  @[@"Library / You", @3], @[@"You", @4] ];
    if ([spec.key isEqualToString:KLeftSideGesture] || [spec.key isEqualToString:KRightSideGesture])
        return @[ @[@"Brightness", @1], @[@"Volume", @2], @[@"Speed", @3] ];
    return nil;
}

// Push a picker listing one checkmark row per choice; the stored value is
// highlighted.
static void ytfPushChoicesPicker(id manager, id settingsVC, YTFFeatureSpec *spec) {
    NSArray *choices = ytfChoicesFor(spec);
    if (!choices.count) return;
    Class itemCls = NSClassFromString(@"YTSettingsSectionItem");
    if (!itemCls) return;
    NSMutableArray *rows = [NSMutableArray array];
    [rows addObject:YTFHeaderItem(spec.title)];
    NSUInteger current = (NSUInteger)INTFORVAL(spec.key);
    NSUInteger selectedIndex = 0;
    for (NSUInteger i = 0; i < choices.count; i++) {
        NSArray *pair = choices[i];
        int value = [pair[1] intValue];
        if (current == (NSUInteger)value) selectedIndex = i;
        [rows addObject:[(id<YTFreedomSettingsItemFactory>)itemCls checkmarkItemWithTitle:pair[0]
                              titleDescription:nil
                                  selectBlock:^BOOL(id c, NSUInteger a) {
                                      SET_INT(spec.key, value);
                                      ytfMarkDirtyIfRestartNeeded(spec.key);
                                      return YES;
                                  }]];
    }
    YTFPushPicker(manager, settingsVC, spec.title, rows, selectedIndex);
}

// Push the picker for one feature group (rows come from the catalog).
static void ytfPushGroupPicker(id manager, id settingsVC, YTFGroupSpec *group) {
    NSMutableArray *rows = [NSMutableArray array];
    [rows addObject:YTFHeaderItem(group.title)];
    if (group.detail)
        [rows addObject:YTFItem(nil, group.detail, ^BOOL(id c, NSUInteger a) { return NO; })];
    for (YTFFeatureSpec *spec in ytfFeaturesInGroup(group.group)) {
        if (spec.hidden) continue;
        NSString *title = spec.beta ? [spec.title stringByAppendingString:@" (beta)"] : spec.title;
        if (spec.kind == YTFFeatureChoices) {
            [rows addObject:YTFItem(title, spec.detail, ^BOOL(id cell, NSUInteger arg) {
                ytfPushChoicesPicker(manager, settingsVC, spec);
                return YES;
            })];
        } else {
            [rows addObject:YTFSwitchItem(title, spec.detail, spec.key)];
        }
    }
    YTFPushPicker(manager, settingsVC, group.title, rows, 0);
}

// Advanced container: sub-groups from the catalog + disabled Future rows.
static id ytfAdvancedRow(id manager, id settingsVC) {
    return YTFItem(@"Advanced", @"Rarely changed settings and experimental flags",
                   ^BOOL(id cell, NSUInteger arg) {
        NSMutableArray *rows = [NSMutableArray array];
        [rows addObject:YTFHeaderItem(@"Advanced")];
        for (YTFGroupSpec *sub in ytfGroupSpecs()) {
            if (sub.isTopLevel || sub.container) continue;
            [rows addObject:YTFItem(sub.title, sub.detail, ^BOOL(id c, NSUInteger a) {
                ytfPushGroupPicker(manager, settingsVC, sub);
                return YES;
            })];
        }
        // Future - disabled rows for not-yet-implemented features.
        [rows addObject:YTFHeaderItem(@"Future - not implemented")];
        [rows addObject:YTFItem(@"Downloads", @"Disabled - not implemented", ^BOOL(id c, NSUInteger a) { return NO; })];
        [rows addObject:YTFItem(@"Native share sheet", @"Disabled - not implemented", ^BOOL(id c, NSUInteger a) { return NO; })];
        [rows addObject:YTFItem(@"Dislike counts (RYD)", @"Disabled - not implemented", ^BOOL(id c, NSUInteger a) { return NO; })];
        [rows addObject:YTFItem(@"SponsorBlock", @"Disabled - not implemented", ^BOOL(id c, NSUInteger a) { return NO; })];
        YTFPushPicker(manager, settingsVC, @"Advanced", rows, 0);
        return YES;
    });
}

// Preferences container: import/export/restore + cache management.
static id ytfPrefsRow(id manager, id settingsVC) {
    return YTFItem(@"Preferences", nil, ^BOOL(id cell, NSUInteger arg) {
        NSMutableArray *rows = [NSMutableArray array];
        [rows addObject:YTFHeaderItem(@"Preferences")];
        [rows addObject:YTFItem(@"Import settings", @"Restore from an exported file", ^BOOL(id c, NSUInteger a) {
            [[YTFreedomPrefsManager sharedManager] importFromVC:settingsVC];
            return YES;
        })];
        [rows addObject:YTFItem(@"Export settings", @"Save all YTFreedom settings", ^BOOL(id c, NSUInteger a) {
            [[YTFreedomPrefsManager sharedManager] exportFromVC:settingsVC];
            return YES;
        })];
        [rows addObject:YTFItem(@"Restore defaults", nil, ^BOOL(id c, NSUInteger a) {
            [[YTFreedomPrefsManager sharedManager] showAlert:@"Warning"
                                                   subtitle:@"Reset all YTFreedom settings?"
                                                      action:YES];
            return YES;
        })];
        [rows addObject:YTFHeaderItem(@"Cache")];
        [rows addObject:YTFItem(@"Clear cache", cacheSizeString(), ^BOOL(id c, NSUInteger a) {
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
        })];
        // Cache switches come from the catalog too (group "prefs").
        for (YTFFeatureSpec *spec in ytfFeaturesInGroup(@"prefs")) {
            if (spec.hidden) continue;
            [rows addObject:YTFSwitchItem(spec.title, spec.detail, spec.key)];
        }
        YTFPushPicker(manager, settingsVC, @"Preferences", rows, 0);
        return YES;
    });
}

static void buildYTFreedomSection(id manager) {
    Class itemCls = NSClassFromString(@"YTSettingsSectionItem");
    if (!itemCls) return;
    id settingsVC = [manager valueForKey:@"_settingsViewControllerDelegate"];
    if (!settingsVC) return;

    NSMutableArray *items = [NSMutableArray array];

    // Version row.
    [items addObject:YTFItem([NSString stringWithFormat:@"YTFreedom v%@", YTFREEDOM_VERSION],
                             @"Settings for the YTFreedom tweak",
                             ^BOOL(id cell, NSUInteger arg) { return NO; })];

    // One row per top-level group, in catalog order.
    for (YTFGroupSpec *group in ytfGroupSpecs()) {
        if (!group.isTopLevel) continue;
        id row = nil;
        if ([group.group isEqualToString:@"advanced"])
            row = ytfAdvancedRow(manager, settingsVC);
        else if ([group.group isEqualToString:@"prefs"])
            row = ytfPrefsRow(manager, settingsVC);
        else
            row = YTFItem(group.title, group.detail, ^BOOL(id cell, NSUInteger arg) {
                ytfPushGroupPicker(manager, settingsVC, group);
                return YES;
            });
        if (row) {
            ((id<YTFreedomSettingsItemHooks>)row).settingIcon = YTFIcon((int)ytfGroupIcon(group.group));
            [items addObject:row];
        }
    }

    if ([settingsVC respondsToSelector:@selector(setSectionItems:forCategory:title:icon:titleDescription:headerHidden:)]) {
        [(id<YTFreedomSettingsVC>)settingsVC setSectionItems:items
                        forCategory:YTFreedomSection
                              title:@"YTFreedom"
                               icon:YTFIcon(658)
                  titleDescription:nil
                      headerHidden:NO];
    } else {
        os_log(ytfLog(), "YTFreedom: settings VC lacks setSectionItems:... - section not shown");
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
