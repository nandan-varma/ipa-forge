// Settings.m — in-app "SpotifyMod" settings: an inline row injected into
// Spotify's settings list (_TtC21Settings_PlatformImpl26SettingsListViewController,
// the 9.1.44+ settings root) that pushes a settings screen with feature
// toggles. All plain ObjC/UIKit; defaults are ON (see SpotifyHook.h).
//
// Notes: toggles are read when hooks install (shortly after launch), so
// changes apply on relaunch — the screen says so.

#import "SpotifyHook.h"
#import <UIKit/UIKit.h>

static const NSInteger kSettingsRowTag = 20261;
static const CGFloat kSettingsRowHeight = 64;

// --- the settings screen ----------------------------------------------------

@interface SMFeature : NSObject
@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NSString *detail;
@property (nonatomic, copy) NSString *key;
@end
@implementation SMFeature
@end

@interface SpotifyModSettingsVC : UITableViewController
@end

@implementation SpotifyModSettingsVC {
    NSArray<SMFeature *> *_features;
}

- (instancetype)init {
    self = [super initWithStyle:UITableViewStyleGrouped];
    _features = @[
        ({ SMFeature *f = [SMFeature new]; f.title = @"Premium unlock"; f.detail = @"Unlimited skips, no shuffle-lock, high quality (bootstrap rewrite)"; f.key = kSMPremium; f; }),
        ({ SMFeature *f = [SMFeature new]; f.title = @"Ad blocker"; f.detail = @"HUB ad cards + ad endpoints blocked"; f.key = kSMAdBlock; f; }),
        ({ SMFeature *f = [SMFeature new]; f.title = @"Session protection"; f.detail = @"Prevents forced logout / ad re-delivery"; f.key = kSMSession; f; }),
        ({ SMFeature *f = [SMFeature new]; f.title = @"App-group fix"; f.detail = @"Container fallback for re-signed installs"; f.key = kSMAppGroup; f; }),
    ];
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
        self.navigationController.navigationBar.titleTextAttributes = @{NSForegroundColorAttributeName: [UIColor whiteColor]};
    }
}

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 2; }

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return section == 0 ? (NSInteger)_features.count : 1;
}

- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    return section == 0 ? @"Features" : @"About";
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    static NSString *const reuse = @"sm-cell";
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:reuse];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:reuse];
    cell.backgroundColor = [UIColor colorWithWhite:0.08 alpha:1];
    cell.textLabel.textColor = [UIColor whiteColor];
    cell.detailTextLabel.textColor = [UIColor colorWithWhite:1 alpha:0.55];
    cell.selectionStyle = UITableViewCellSelectionStyleNone;

    if (indexPath.section == 0) {
        SMFeature *f = _features[(NSUInteger)indexPath.row];
        cell.textLabel.text = f.title;
        cell.detailTextLabel.text = f.detail;
        UISwitch *sw = [UISwitch new];
        sw.on = smEnabled(f.key);
        [sw addTarget:self action:@selector(toggled:) forControlEvents:UIControlEventValueChanged];
        cell.accessoryView = sw;
    } else {
        cell.textLabel.text = @"SpotifyMod — from-scratch Spotify enhancement";
        cell.detailTextLabel.text = @"Changes apply on relaunch";
        cell.textLabel.font = [UIFont systemFontOfSize:14];
    }
    return cell;
}

- (void)toggled:(UISwitch *)sw {
    // find the feature row for this switch
    UIView *cell = [sw superview];
    while (cell && ![cell isKindOfClass:[UITableViewCell class]]) cell = cell.superview;
    NSIndexPath *ip = [self.tableView indexPathForCell:(UITableViewCell *)cell];
    if (!ip || ip.section != 0) return;
    SMFeature *f = _features[(NSUInteger)ip.row];
    [[NSUserDefaults standardUserDefaults] setBool:sw.on forKey:f.key];
    os_log(spotLog(), "SpotifyMod: %@ -> %@", f.key, sw.on ? @"ON" : @"OFF");
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
    UINavigationController *nav = vc.navigationController ?: [[UINavigationController alloc] initWithRootViewController:settings];
    if (vc.navigationController) {
        [vc.navigationController pushViewController:settings animated:YES];
    } else {
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
    row.backgroundColor = [UIColor colorWithWhite:0.08 alpha:1];

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
