// SettingsUI.m - in-app "SpotifyMod" settings screen: an inline row injected
// into Spotify's settings list (_TtC21Settings_PlatformImpl26SettingsList-
// ViewController, the 9.1.44+ settings root) that pushes the settings
// screen. The screen is table-driven from the feature catalog in
// SpotifyFeatures.m (the single source of truth): sections come from
// smGroupSpecs(), rows from smFeaturesInGroup(). Row kinds:
//   SMFeatureSwitch  -> switch row
//   SMFeatureChoice  -> dropdown row (shows the current value, taps into a
//                       checkmark picker)
//   SMFeatureDisabled-> greyed-out "Future" row
// The About section (version + reset) is app chrome and lives here.
//
// Toggles are read when hooks install (shortly after launch), so every
// change shows a "Restart to apply" hint.

#import "SpotifyHook.h"
#import <UIKit/UIKit.h>

static const NSInteger kSettingsRowTag = 20261;
static const CGFloat kSettingsRowHeight = 64;

// --- theme ------------------------------------------------------------------
static UIColor *smAccentColor(void) { return [UIColor colorWithRed:0.12 green:0.84 blue:0.38 alpha:1]; } // #1ED760
static UIColor *smCellBg(void) { return [UIColor colorWithWhite:0.08 alpha:1]; }
static UIColor *smDetailColor(void) { return [UIColor colorWithWhite:1 alpha:0.55]; }
static UIColor *smDisabledColor(void) { return [UIColor colorWithWhite:1 alpha:0.32]; }

// --- restart hint -----------------------------------------------------------
// Every setting is read when hooks install at launch, so a change needs a
// relaunch. Show a short auto-dismissing pill so a tester doesn't report a
// "broken" toggle.
static void smShowRestartHint(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        UIWindow *window = [UIApplication sharedApplication].windows.firstObject;
        if (!window) return;
        UIView *existing = [window viewWithTag:0x51AD];
        if (existing) [existing removeFromSuperview];
        UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(0, 0, 0, 0)];
        label.tag = 0x51AD;
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

// Title of the currently stored choice value for a dropdown row.
static NSString *smChoiceTitleForKey(NSString *key) {
    SMFeatureSpec *spec = smFeatureForKey(key);
    if (!spec || spec.kind != SMFeatureChoice) return nil;
    NSInteger current = smIntVal(key);
    for (NSArray *pair in spec.choices)
        if ([pair[1] integerValue] == current) return pair[0];
    return nil;
}

// --- choice picker (dropdown target) ----------------------------------------

@interface SMChoicePickerVC : UITableViewController
@property (nonatomic, strong) SMFeatureSpec *spec;
@end

@implementation SMChoicePickerVC

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = self.spec.title;
    self.view.backgroundColor = [UIColor blackColor];
    self.tableView.backgroundColor = [UIColor blackColor];
    self.tableView.separatorColor = [UIColor colorWithWhite:1 alpha:0.12];
}

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 1; }

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return (NSInteger)self.spec.choices.count;
}

- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    return self.spec.detail;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    static NSString *const reuse = @"sm-choice";
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:reuse];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:reuse];
    cell.backgroundColor = [UIColor colorWithWhite:0.08 alpha:1];
    cell.textLabel.textColor = [UIColor whiteColor];
    cell.textLabel.font = [UIFont systemFontOfSize:16];
    NSArray *pair = self.spec.choices[(NSUInteger)indexPath.row];
    cell.textLabel.text = pair[0];
    cell.accessoryType = ([pair[1] integerValue] == smIntVal(self.spec.key))
        ? UITableViewCellAccessoryCheckmark : UITableViewCellAccessoryNone;
    cell.tintColor = smAccentColor();
    return cell;
}

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    NSArray *pair = self.spec.choices[(NSUInteger)indexPath.row];
    [[NSUserDefaults standardUserDefaults] setInteger:[pair[1] integerValue] forKey:self.spec.key];
    os_log(spotLog(), "SpotifyMod: %@ -> %@", self.spec.key, pair[0]);
    if (self.spec.restartRequired) smShowRestartHint();
    [self.navigationController popViewControllerAnimated:YES];
}

@end

// --- the settings screen ----------------------------------------------------

@interface SpotifyModSettingsVC : UITableViewController
@end

@implementation SpotifyModSettingsVC

- (instancetype)init {
    self = [super initWithStyle:UITableViewStyleGrouped];
    return self;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"SpotifyMod";
    self.view.backgroundColor = [UIColor blackColor];
    self.tableView.backgroundColor = [UIColor blackColor];
    self.tableView.separatorColor = [UIColor colorWithWhite:1 alpha:0.12];
    self.navigationController.navigationBar.tintColor = [UIColor whiteColor];
    if (@available(iOS 13.0, *)) {
        self.navigationController.navigationBar.titleTextAttributes =
            @{NSForegroundColorAttributeName: [UIColor whiteColor]};
    }
}

// Sections: the catalog groups (Essentials, Advanced, Future) plus a
// hand-built About section (version + reset) appended last.
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView {
    return (NSInteger)smGroupSpecs().count + 1;
}

- (NSInteger)aboutSection { return (NSInteger)smGroupSpecs().count; }

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    if (section == [self aboutSection]) return [self aboutRowCount];
    SMGroupSpec *group = smGroupSpecs()[(NSUInteger)section];
    return (NSInteger)smFeaturesInGroup(group.group).count;
}

- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    if (section == [self aboutSection]) return @"About";
    return smGroupSpecs()[(NSUInteger)section].title;
}

- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (section == [self aboutSection]) return nil;
    return smGroupSpecs()[(NSUInteger)section].detail;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    if (indexPath.section == [self aboutSection]) return [self aboutCellForRow:indexPath.row];
    SMGroupSpec *group = smGroupSpecs()[(NSUInteger)indexPath.section];
    SMFeatureSpec *spec = smFeaturesInGroup(group.group)[(NSUInteger)indexPath.row];

    if (spec.kind == SMFeatureSwitch) {
        static NSString *const reuse = @"sm-switch";
        UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:reuse];
        if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:reuse];
        cell.backgroundColor = smCellBg();
        cell.textLabel.textColor = [UIColor whiteColor];
        cell.detailTextLabel.textColor = smDetailColor();
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
        cell.textLabel.text = spec.title;
        cell.detailTextLabel.text = spec.detail;
        UISwitch *sw = [UISwitch new];
        sw.on = smEnabled(spec.key);
        [sw addTarget:self action:@selector(toggled:) forControlEvents:UIControlEventValueChanged];
        cell.accessoryView = sw;
        return cell;
    }

    if (spec.kind == SMFeatureChoice) {
        static NSString *const reuse = @"sm-choice";
        UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:reuse];
        if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:reuse];
        cell.backgroundColor = smCellBg();
        cell.textLabel.textColor = [UIColor whiteColor];
        cell.detailTextLabel.textColor = smDetailColor();
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
        cell.textLabel.text = spec.title;
        cell.detailTextLabel.text = smChoiceTitleForKey(spec.key);
        return cell;
    }

    // SMFeatureDisabled — Future row, greyed out, no interaction.
    static NSString *const reuse = @"sm-disabled";
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:reuse];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:reuse];
    cell.backgroundColor = smCellBg();
    cell.textLabel.textColor = smDisabledColor();
    cell.detailTextLabel.textColor = smDisabledColor();
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    cell.textLabel.text = spec.title;
    cell.detailTextLabel.text = [spec.detail stringByAppendingString:@" (not implemented)"];
    return cell;
}

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if (indexPath.section == [self aboutSection]) {
        [self resetAllSettingsIfRequested:indexPath.row];
        return;
    }
    SMGroupSpec *group = smGroupSpecs()[(NSUInteger)indexPath.section];
    SMFeatureSpec *spec = smFeaturesInGroup(group.group)[(NSUInteger)indexPath.row];
    if (spec.kind != SMFeatureChoice) return;
    SMChoicePickerVC *picker = [SMChoicePickerVC new];
    picker.spec = spec;
    [self.navigationController pushViewController:picker animated:YES];
}

- (void)toggled:(UISwitch *)sw {
    UIView *cell = sw.superview;
    while (cell && ![cell isKindOfClass:[UITableViewCell class]]) cell = cell.superview;
    NSIndexPath *ip = [self.tableView indexPathForCell:(UITableViewCell *)cell];
    if (!ip) return;
    SMGroupSpec *group = smGroupSpecs()[(NSUInteger)ip.section];
    SMFeatureSpec *spec = smFeaturesInGroup(group.group)[(NSUInteger)ip.row];
    [[NSUserDefaults standardUserDefaults] setBool:sw.on forKey:spec.key];
    os_log(spotLog(), "SpotifyMod: %@ -> %@", spec.key, sw.on ? @"ON" : @"OFF");
    if (spec.restartRequired) smShowRestartHint();
}

// --- About (app chrome - version + reset) -----------------------------------

- (NSInteger)aboutRowCount { return 3; }

- (UITableViewCell *)aboutCellForRow:(NSInteger)row {
    static NSString *const reuse = @"sm-about";
    UITableViewCell *cell = [self.tableView dequeueReusableCellWithIdentifier:reuse];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:reuse];
    cell.backgroundColor = smCellBg();
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    if (row == 0) {
        cell.textLabel.textColor = smAccentColor();
        cell.textLabel.font = [UIFont systemFontOfSize:16 weight:UIFontWeightSemibold];
        cell.textLabel.text = [NSString stringWithFormat:@"SpotifyMod v%s", SPOTIFYMOD_VERSION];
        cell.detailTextLabel.textColor = smDetailColor();
        cell.detailTextLabel.text = @"From-scratch enhancement - see TESTING.md";
    } else if (row == 1) {
        cell.textLabel.textColor = [UIColor whiteColor];
        cell.textLabel.text = @"Reset all settings";
        cell.detailTextLabel.textColor = smDetailColor();
        cell.detailTextLabel.text = @"Restore every toggle to its default";
        cell.selectionStyle = UITableViewCellSelectionStyleDefault;
    } else {
        cell.textLabel.textColor = smDetailColor();
        cell.textLabel.font = [UIFont systemFontOfSize:13];
        cell.textLabel.text = @"Changes apply on relaunch";
        cell.detailTextLabel.text = nil;
    }
    return cell;
}

- (void)resetAllSettings {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    for (SMFeatureSpec *spec in smFeatureSpecs()) {
        if (spec.key) [defaults removeObjectForKey:spec.key];
    }
    os_log(spotLog(), "SpotifyMod: all settings reset");
    smShowRestartHint();
    [self.tableView reloadData];
}

- (void)resetAllSettingsIfRequested:(NSInteger)row {
    if (row != 1) return;
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Reset all settings?"
                                                                   message:@"Every SpotifyMod setting returns to its default. Requires relaunch."
                                                            preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Reset" style:UIAlertActionStyleDestructive
                                            handler:^(UIAlertAction *a) { [self resetAllSettings]; }]];
    [self presentViewController:alert animated:YES completion:nil];
}

@end

// --- inline row injection ---------------------------------------------------

static BOOL findCollectionViewInView(UIView *view, UICollectionView **out) {
    if ([view isKindOfClass:[UICollectionView class]]) { *out = (UICollectionView *)view; return YES; }
    for (UIView *sub in view.subviews) {
        if (findCollectionViewInView(sub, out)) return YES;
    }
    return NO;
}

static void pushSettings(id fromVC) {
    UIViewController *vc = fromVC;
    SpotifyModSettingsVC *settings = [SpotifyModSettingsVC new];
    if (vc.navigationController) {
        [vc.navigationController pushViewController:settings animated:YES];
    } else {
        UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:settings];
        [vc presentViewController:nav animated:YES completion:nil];
    }
}

static void injectSettingsRow(id vc) {
    UIView *view = [vc valueForKey:@"view"];
    UICollectionView *cv = nil;
    if (!view || !findCollectionViewInView(view, &cv)) return;
    if ([cv viewWithTag:kSettingsRowTag]) return; // already injected

    UIButton *row = [UIButton buttonWithType:UIButtonTypeCustom];
    row.tag = kSettingsRowTag;
    row.frame = CGRectMake(0, -kSettingsRowHeight, cv.bounds.size.width, kSettingsRowHeight);
    row.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    row.backgroundColor = smCellBg();

    UILabel *title = [[UILabel alloc] initWithFrame:CGRectMake(20, 10, cv.bounds.size.width - 60, 22)];
    title.text = @"SpotifyMod";
    title.textColor = [UIColor whiteColor];
    title.font = [UIFont systemFontOfSize:16 weight:UIFontWeightSemibold];
    title.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    [row addSubview:title];

    UILabel *subtitle = [[UILabel alloc] initWithFrame:CGRectMake(20, 33, cv.bounds.size.width - 60, 18)];
    subtitle.text = @"Patches, settings & enhancements";
    subtitle.textColor = [UIColor colorWithWhite:1 alpha:0.6];
    subtitle.font = [UIFont systemFontOfSize:12];
    subtitle.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    [row addSubview:subtitle];

    UIImageView *chevron = [[UIImageView alloc] initWithImage:[UIImage systemImageNamed:@"chevron.right"]];
    chevron.tintColor = [UIColor colorWithWhite:1 alpha:0.55];
    chevron.frame = CGRectMake(cv.bounds.size.width - 34, (kSettingsRowHeight - 14) / 2, 14, 14);
    chevron.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin;
    [row addSubview:chevron];

    // tap -> push the settings screen (weak ref avoids a retain cycle)
    __weak id weakVC = vc;
    UIAction *action = [UIAction actionWithHandler:^(UIAction *a) {
        pushSettings(weakVC);
    }];
    [row addAction:action forControlEvents:UIControlEventTouchUpInside];

    [cv addSubview:row];

    UIEdgeInsets inset = cv.contentInset;
    inset.top += kSettingsRowHeight;
    cv.contentInset = inset;
}

static void hookSettingsList(void) {
    Class cls = NSClassFromString(@"_TtC21Settings_PlatformImpl26SettingsListViewController");
    if (!cls) return;

    static IMP orig_viewWillAppear;
    orig_viewWillAppear = sptHookInstance(cls, @selector(viewWillAppear:),
        ^void(id self, BOOL animated) {
            ((void(*)(id, SEL, BOOL))orig_viewWillAppear)(self, @selector(viewWillAppear:), animated);
            injectSettingsRow(self);
        });
    (void)orig_viewWillAppear;

    static IMP orig_viewDidLayoutSubviews;
    orig_viewDidLayoutSubviews = sptHookInstance(cls, @selector(viewDidLayoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_viewDidLayoutSubviews)(self, @selector(viewDidLayoutSubviews));
            injectSettingsRow(self);
        });
    (void)orig_viewDidLayoutSubviews;
}

void SpotifySettingsInit(void) {
    hookSettingsList();
}
