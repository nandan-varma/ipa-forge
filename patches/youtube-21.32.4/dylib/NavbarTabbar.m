// NavbarTabbar.m — navigation bar (G8) and tab bar (G9) toggles, ported
// from YouMod's Navbar.x / Tabbar.x. All hooks verified present in 21.32.4.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

@protocol YTFreedomNavHooks <NSObject>
@optional
- (id)iconImage;
- (void)setIconType:(int)type;
- (int)iconType;
- (void)setPremiumLogo:(BOOL)premium;
- (BOOL)isPremiumLogo;
- (id)notificationButton;
- (id)searchButton;
- (void)setTitle:(NSString *)title forState:(UIControlState)state;
- (void)setSizeWithPaddingAndInsets:(BOOL)flag;
- (id)navigationButton;
- (void)selectItemWithPivotIdentifier:(NSString *)identifier;
- (id)pivotBarItemRenderer;
- (id)pivotBarIconOnlyItemRenderer;
- (NSString *)pivotIdentifier;
- (void)setFillColor:(id)color;
- (void)setBorderColor:(id)color;
- (void)setRenderer:(id)renderer;
- (void)viewDidAppear:(BOOL)animated;
- (id)itemsArray;
- (void)setHidden:(BOOL)hidden;
@end

// --- G8: navigation bar -----------------------------------------------------

// Hide YT logo: init returns nil when enabled. `orig` is captured by value
// (safe inside the block) rather than through a shared static.
static void hookInitNilable(Class cls) {
    if (!cls) return;
    Method m = class_getInstanceMethod(cls, sel_registerName("init"));
    if (!m) return;
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel_registerName("init"),
        imp_implementationWithBlock(^id(id self) {
            return IS_ENABLED(KHideYTLogo) ? nil
                : ((id(*)(id, SEL))orig)(self, sel_registerName("init"));
        }), method_getTypeEncoding(m));
}

static void hookTopbarLogoRenderer(Class cls) {
    if (!cls) return;
    Method m = class_getInstanceMethod(cls, sel_registerName("setTopbarLogoRenderer:"));
    if (!m) return;
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel_registerName("setTopbarLogoRenderer:"),
        imp_implementationWithBlock(^void(id self, id renderer) {
            if (IS_ENABLED(KPremiumLogo)) {
                id<YTFreedomNavHooks> icon = [renderer respondsToSelector:@selector(iconImage)]
                    ? [renderer iconImage] : nil;
                if (icon) [icon setIconType:537];
            }
            ((void(*)(id, SEL, id))orig)(self, sel_registerName("setTopbarLogoRenderer:"), renderer);
        }), method_getTypeEncoding(m));
}

static void hookPremiumLogo(Class cls) {
    if (!cls) return;
    Method m = class_getInstanceMethod(cls, sel_registerName("setPremiumLogo:"));
    if (!m) return;
    IMP orig = method_getImplementation(m);
    class_replaceMethod(cls, sel_registerName("setPremiumLogo:"),
        imp_implementationWithBlock(^void(id self, BOOL premium) {
            ((void(*)(id, SEL, BOOL))orig)(self, sel_registerName("setPremiumLogo:"),
                IS_ENABLED(KPremiumLogo) ? YES : premium);
        }), method_getTypeEncoding(m));

    Method mi = class_getInstanceMethod(cls, sel_registerName("isPremiumLogo"));
    if (mi) {
        IMP origIs = method_getImplementation(mi);
        class_replaceMethod(cls, sel_registerName("isPremiumLogo"),
            imp_implementationWithBlock(^BOOL(id self) {
                return IS_ENABLED(KPremiumLogo) ? YES
                    : ((BOOL(*)(id, SEL))origIs)(self, sel_registerName("isPremiumLogo"));
            }), method_getTypeEncoding(mi));
    }
}

static void fixNavbar(void) {
    hookInitNilable(NSClassFromString(@"YTHeaderLogoController"));
    hookInitNilable(NSClassFromString(@"YTHeaderLogoControllerImpl"));
    hookTopbarLogoRenderer(NSClassFromString(@"YTHeaderLogoController"));
    hookTopbarLogoRenderer(NSClassFromString(@"YTHeaderLogoControllerImpl"));
    hookPremiumLogo(NSClassFromString(@"YTHeaderLogoController"));
    hookPremiumLogo(NSClassFromString(@"YTHeaderLogoControllerImpl"));

    // Right-side buttons: notification / search / voice search / cast.
    static IMP orig_rightButtonsLayout;
    orig_rightButtonsLayout = ytfHookInstance(NSClassFromString(@"YTRightNavigationButtons"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_rightButtonsLayout)(self, @selector(layoutSubviews));
            id<YTFreedomNavHooks> buttons = self;
            if (IS_ENABLED(KHideNoti) && [buttons respondsToSelector:@selector(notificationButton)])
                [[buttons notificationButton] setHidden:YES];
            if (IS_ENABLED(KHideSearch) && [buttons respondsToSelector:@selector(searchButton)])
                [[buttons searchButton] setHidden:YES];
            for (UIView *subview in [(UIView *)self subviews]) {
                if (IS_ENABLED(KHideVoiceSearch)
                    && [subview.accessibilityLabel isEqualToString:NSLocalizedString(@"search.voice.access", nil)])
                    subview.hidden = YES;
                if (IS_ENABLED(KHideCastButtonNav)
                    && [subview.accessibilityIdentifier isEqualToString:@"id.mdx.playbackroute.button"])
                    subview.hidden = YES;
            }
        });
    (void)orig_rightButtonsLayout;

    // Hide the yoodle logo in the navigation title.
    static IMP orig_navTitleLayout;
    orig_navTitleLayout = ytfHookInstance(NSClassFromString(@"YTNavigationBarTitleView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_navTitleLayout)(self, @selector(layoutSubviews));
            if (IS_ENABLED(KHideYTLogo)) {
                NSArray *subviews = [(UIView *)self subviews];
                if (subviews.count > 1
                    && [((UIView *)subviews[1]).accessibilityIdentifier isEqualToString:@"id.yoodle.logo"])
                    ((UIView *)subviews[1]).hidden = YES;
            }
        });
    (void)orig_navTitleLayout;
}

// --- G9: tab bar ------------------------------------------------------------

static void fixTabbar(void) {
    // Remove tabs by pivot identifier.
    static IMP orig_setPivotRenderer;
    orig_setPivotRenderer = ytfHookInstance(NSClassFromString(@"YTPivotBarView"),
        @selector(setRenderer:),
        ^void(id self, id renderer) {
            NSMutableArray *items = [renderer respondsToSelector:@selector(itemsArray)]
                ? [renderer valueForKey:@"itemsArray"] : nil;
            if ([items isKindOfClass:[NSMutableArray class]]) {
                NSMutableIndexSet *remove = [NSMutableIndexSet indexSet];
                [items enumerateObjectsUsingBlock:^(id item, NSUInteger idx, BOOL *stop) {
                    id<YTFreedomNavHooks> hooks = item;
                    NSString *pID = nil, *pID2 = nil;
                    if ([hooks respondsToSelector:@selector(pivotBarItemRenderer)]) {
                        id<YTFreedomNavHooks> renderer1 = [hooks pivotBarItemRenderer];
                        if ([renderer1 respondsToSelector:@selector(pivotIdentifier)])
                            pID = [renderer1 pivotIdentifier];
                    }
                    if ([hooks respondsToSelector:@selector(pivotBarIconOnlyItemRenderer)]) {
                        id<YTFreedomNavHooks> renderer2 = [hooks pivotBarIconOnlyItemRenderer];
                        if ([renderer2 respondsToSelector:@selector(pivotIdentifier)])
                            pID2 = [renderer2 pivotIdentifier];
                    }
                    if ([pID isEqualToString:@"FEwhat_to_watch"] && IS_ENABLED(KHideHomeTab))
                        [remove addIndex:idx];
                    if ([pID isEqualToString:@"FEshorts"] && IS_ENABLED(KHideShortsTab))
                        [remove addIndex:idx];
                    if ([pID2 isEqualToString:@"FEuploads"] && IS_ENABLED(KHideCreateButton))
                        [remove addIndex:idx];
                    if ([pID isEqualToString:@"FEsubscriptions"] && IS_ENABLED(KHideSubscriptTab))
                        [remove addIndex:idx];
                }];
                if (remove.count > 0) [items removeObjectsAtIndexes:remove];
            }
            ((void(*)(id, SEL, id))orig_setPivotRenderer)(self, @selector(setRenderer:), renderer);
        });
    (void)orig_setPivotRenderer;

    // Tab indicators -> clear.
    static IMP orig_setFillColor;
    orig_setFillColor = ytfHookInstance(NSClassFromString(@"YTPivotBarIndicatorView"),
        @selector(setFillColor:),
        ^void(id self, id color) {
            ((void(*)(id, SEL, id))orig_setFillColor)(
                self, @selector(setFillColor:), IS_ENABLED(KHideTabIndi) ? [UIColor clearColor] : color);
        });
    (void)orig_setFillColor;
    static IMP orig_setBorderColor;
    orig_setBorderColor = ytfHookInstance(NSClassFromString(@"YTPivotBarIndicatorView"),
        @selector(setBorderColor:),
        ^void(id self, id color) {
            ((void(*)(id, SEL, id))orig_setBorderColor)(
                self, @selector(setBorderColor:), IS_ENABLED(KHideTabIndi) ? [UIColor clearColor] : color);
        });
    (void)orig_setBorderColor;

    // Tab labels -> empty.
    static IMP orig_setPivotItemRenderer;
    orig_setPivotItemRenderer = ytfHookInstance(NSClassFromString(@"YTPivotBarItemView"),
        @selector(setRenderer:),
        ^void(id self, id renderer) {
            ((void(*)(id, SEL, id))orig_setPivotItemRenderer)(self, @selector(setRenderer:), renderer);
            if (IS_ENABLED(KHideTabLabels)) {
                id<YTFreedomNavHooks> hooks = self;
                if ([hooks respondsToSelector:@selector(navigationButton)]) {
                    id button = [hooks navigationButton];
                    if ([button respondsToSelector:@selector(setTitle:forState:)])
                        [button setTitle:@"" forState:UIControlStateNormal];
                    if ([button respondsToSelector:@selector(setSizeWithPaddingAndInsets:)])
                        [button setSizeWithPaddingAndInsets:NO];
                }
            }
        });
    (void)orig_setPivotItemRenderer;

    // Startup tab.
    static IMP orig_pivotViewDidAppear;
    orig_pivotViewDidAppear = ytfHookInstance(NSClassFromString(@"YTPivotBarViewController"),
        @selector(viewDidAppear:),
        ^void(id self, BOOL animated) {
            ((void(*)(id, SEL, BOOL))orig_pivotViewDidAppear)(self, @selector(viewDidAppear:), animated);
            static BOOL isTabSelected = NO;
            if (!isTabSelected) {
                NSArray *identifiers = @[@"FEwhat_to_watch", @"FEshorts", @"FEsubscriptions", @"FElibrary"];
                int tab = INTFORVAL(KDefaultTab);
                if (tab >= 0 && tab < (int)identifiers.count) {
                    id<YTFreedomNavHooks> hooks = self;
                    if ([hooks respondsToSelector:@selector(selectItemWithPivotIdentifier:)])
                        [hooks selectItemWithPivotIdentifier:identifiers[tab]];
                }
                isTabSelected = YES;
            }
        });
    (void)orig_pivotViewDidAppear;
}

void YTFreedomNavbarTabbarInit(void) {
    fixNavbar();
    fixTabbar();
}
