// TabBarFix.m — hide the Premium and Create bottom-bar tabs (one toggle:
// kSMHideExtraTabs) and make the surviving tabs fill the bar width.
//
// Spotify 9.1.x bottom bar (NavigationUI_TabBarImpl) — structure verified
// from the 9.1.72 binary's method tables:
//   _TtC23NavigationUI_TabBarImpl15TabBarContainer  — UIViewController
//       (setViewControllers:, tabBarView, viewDidLayoutSubviews).
//   _TtCE14Encore_TabsKitO16EncoreFoundation6Encore8TabsView — a
//       UICollectionView (collectionView:didSelectItemAtIndexPath:,
//       intrinsicContentSize) hosting one TabItemCell per tab, each holding
//       one _TtC23NavigationUI_TabBarImpl21TabBarItemElementView (plain
//       UIView). Removing the element empties its cell but the CELL keeps
//       its slot — the collection layout positions cells by data-source
//       count, so the empty space is structural and never re-flows.
//
// Detection (multiple independent signals; each is cheap and idempotent):
//   Premium: id/label (element or its cell) contains "premium".
//   Create : id/label contains "create"/"creation", or the element subtree
//            contains CreateMenuTabBarItemView / CreateTabView.
// Evaluated independently, then gated by the SINGLE toggle — both tabs are
// always removed together (v0.0.7's two toggles could race and leave one).
//
// The fix has three layers, each self-sufficient:
//   1. setViewControllers: filter — drop Premium/Create VCs before items
//      are built (belt; the Premium tab is item-only so this alone is not
//      enough).
//   2. Element removal + slot spreading from SAFE contexts (post-layout /
//      async): remove hidden elements, spread the visible slots evenly
//      across the full width, zero-width the hidden cells.
//   3. Spread-only re-application inside TabsView.layoutSubviews (after
//      orig): the collection view re-positions cells on every layout pass,
//      so we re-assert our spread right after it — the app can never win
//      the layout fight. No removal happens in this pass (mutating the tree
//      inside a collection layout is the risky path we avoid).
//
// Safety: every hook captures its original IMP in its own __block local
// (a shared static across classes crashed v0.0.5 — never again); every
// apply is wrapped in @try so a hiccup logs instead of crashing.
//
// All classes are looked up at runtime; a future rename degrades to a no-op
// and the yaml hooks block flags the drift. The toggle defaults OFF.

#import "SpotifyHook.h"
#import <UIKit/UIKit.h>

static Class smElementCls;       // TabBarItemElementView — the per-tab view
static Class smCreateContentCls; // CreateMenuTabBarItemView — Create tab content
static Class smCreateTabCls;     // CreateTabView — alternate Create marker
static Class smContainerCls;     // TabBarContainer — the tab bar UIViewController
static Class smTabsViewCls;      // Encore TabsView — the bar's UICollectionView
static Class smPremiumVCCls;     // PDPViewController — Premium tab content
static Class smCreateVCCls;      // CreateMenuViewController — Create tab content

// --- small helpers ----------------------------------------------------------

static BOOL smSubtreeContains(UIView *view, Class cls) {
    if (!view || !cls) return NO;
    if ([view isKindOfClass:cls]) return YES;
    for (UIView *sub in view.subviews) {
        if (smSubtreeContains(sub, cls)) return YES;
    }
    return NO;
}

// Any UILabel / accessibility label in the subtree equal to `text`.
static BOOL smElementHasText(UIView *view, NSString *text) {
    if (!view || !text) return NO;
    NSString *label = view.accessibilityLabel;
    if ([label isKindOfClass:[NSString class]] && [label caseInsensitiveCompare:text] == NSOrderedSame) return YES;
    if ([view isKindOfClass:[UILabel class]]) {
        NSString *t = ((UILabel *)view).text;
        if ([t isKindOfClass:[NSString class]] && [t caseInsensitiveCompare:text] == NSOrderedSame) return YES;
    }
    for (UIView *sub in view.subviews) {
        if (smElementHasText(sub, text)) return YES;
    }
    return NO;
}

// Nearest UICollectionViewCell ancestor (the bar's per-tab slots), else nil.
static UIView *smEnclosingCell(UIView *v) {
    while (v) {
        if ([v isKindOfClass:[UICollectionViewCell class]]) return v;
        v = v.superview;
    }
    return nil;
}

// --- detection ---------------------------------------------------------------

// Classify `element` as premium / create / neither. Checks the element AND
// its enclosing cell (identifiers/labels live on the cell in some builds).
static void smClassifyElement(UIView *element, BOOL *isPremium, BOOL *isCreate) {
    *isPremium = NO;
    *isCreate = NO;
    if (!element) return;

    UIView *cell = smEnclosingCell(element);
    NSArray<UIView *> *views = cell ? @[ element, cell ] : @[ element ];
    for (UIView *v in views) {
        NSString *aid = v.accessibilityIdentifier;
        NSString *alabel = v.accessibilityLabel;
        for (NSString *s in @[ aid, alabel ]) {
            if (![s isKindOfClass:[NSString class]] || s.length == 0) continue;
            NSString *low = s.lowercaseString;
            if (!*isPremium && [low containsString:@"premium"]) *isPremium = YES;
            if (!*isCreate && ([low containsString:@"create"] || [low containsString:@"creation"])) *isCreate = YES;
        }
    }
    if (!*isCreate) {
        if (smSubtreeContains(element, smCreateContentCls) || smSubtreeContains(element, smCreateTabCls))
            *isCreate = YES;
    }
    if (!*isPremium && smElementHasText(element, @"Premium")) *isPremium = YES;
    if (!*isCreate && smElementHasText(element, @"Create")) *isCreate = YES;
}

// --- VC-level detection (setViewControllers: filter) -------------------------

typedef NS_ENUM(NSInteger, SMHiddenKind) { SMHiddenNone = 0, SMHiddenPremium, SMHiddenCreate };

static SMHiddenKind smHiddenKindForVC(UIViewController *vc) {
    if (!vc) return SMHiddenNone;
    if (smPremiumVCCls && [vc isKindOfClass:smPremiumVCCls]) return SMHiddenPremium;
    if (smCreateVCCls && [vc isKindOfClass:smCreateVCCls]) return SMHiddenCreate;
    NSString *cls = NSStringFromClass(vc.class);
    if ([cls containsString:@"Premium"]) return SMHiddenPremium;
    if ([cls containsString:@"CreateMenu"]) return SMHiddenCreate;
    NSString *title = vc.tabBarItem.title;
    if ([title isKindOfClass:[NSString class]]) {
        NSString *low = title.lowercaseString;
        if ([low isEqualToString:@"premium"]) return SMHiddenPremium;
        if ([low isEqualToString:@"create"]) return SMHiddenCreate;
    }
    return SMHiddenNone;
}

// --- slot spreading ----------------------------------------------------------

// The bar root for a view: the nearest UICollectionView ancestor (the bar's
// slot container), else the topmost view below the window. Scanning anything
// smaller can never spread a whole bar.
static UIView *smBarRootForView(UIView *v) {
    UIView *top = v;
    UIView *cur = v ? v.superview : nil;
    while (cur) {
        if ([cur isKindOfClass:[UICollectionView class]]) return cur;
        top = cur;
        cur = cur.superview;
    }
    return top;
}

// Is `v` a slot view? A cell, an element, or something containing an element.
static BOOL smIsSlotView(UIView *v) {
    if (!v) return NO;
    if ([v isKindOfClass:[UICollectionViewCell class]]) return YES;
    return smSubtreeContains(v, smElementCls);
}

// Group `slot` under `container` and record it as hidden if `isHidden`.
static void smRecordSlot(NSMutableDictionary<NSValue *, NSMutableArray<UIView *> *> *slotsByContainer,
                         NSMutableDictionary<NSValue *, NSMutableSet<UIView *> *> *hiddenByContainer,
                         UIView *container, UIView *slot, BOOL isHidden) {
    if (!container || !slot) return;
    NSValue *pk = [NSValue valueWithNonretainedObject:container];
    NSMutableArray *slots = slotsByContainer[pk];
    if (!slots) { slots = [NSMutableArray array]; slotsByContainer[pk] = slots; }
    if (![slots containsObject:slot]) [slots addObject:slot];
    if (isHidden) {
        NSMutableSet *hidden = hiddenByContainer[pk];
        if (!hidden) { hidden = [NSMutableSet set]; hiddenByContainer[pk] = hidden; }
        [hidden addObject:slot];
    }
}

// Core: classify every element under `root`, remove hidden ones when
// `allowRemoval`, then spread each slot container's visible slots evenly and
// zero-width the hidden ones. Runs only from safe contexts (post-layout,
// async, or a plain message send) — never inside a layout pass.
static void smApplyBarLayoutUnsafe(UIView *root, BOOL allowRemoval) {
    if (!root || !smElementCls) return;
    if (!smEnabled(kSMHideExtraTabs)) return;

    NSMutableDictionary<NSValue *, NSMutableArray<UIView *> *> *slotsByContainer =
        [NSMutableDictionary dictionary];
    NSMutableDictionary<NSValue *, NSMutableSet<UIView *> *> *hiddenByContainer =
        [NSMutableDictionary dictionary];
    NSMutableArray<UIView *> *plainElements = [NSMutableArray array]; // plain-view case
    NSMutableSet<UIView *> *plainHidden = [NSMutableSet set];

    NSMutableArray<UIView *> *stack = [NSMutableArray arrayWithObject:root];
    while (stack.count) {
        UIView *v = stack.lastObject;
        [stack removeLastObject];
        for (UIView *sub in [v.subviews copy]) {
            if (![sub isKindOfClass:smElementCls]) { [stack addObject:sub]; continue; }

            BOOL isPremium = NO, isCreate = NO;
            smClassifyElement(sub, &isPremium, &isCreate);
            BOOL hidden = isPremium || isCreate;
            os_log(spotLog(), "SpotifyMod: tab detect %@: create=%d premium=%d hidden=%d id=%@",
                   NSStringFromClass(sub.class), isCreate, isPremium, hidden,
                   sub.accessibilityIdentifier ?: @"(none)");

            UIView *cell = smEnclosingCell(sub);
            if (cell && cell.superview) {
                // Collection case: the slot is the cell, grouped under the
                // collection view. Record even hidden cells so they get
                // zero-widthed in the spread.
                smRecordSlot(slotsByContainer, hiddenByContainer, cell.superview, cell, hidden);
            } else if (hidden && allowRemoval) {
                // Plain case, removal pass: drop the element entirely.
                [sub removeFromSuperview];
            } else {
                // Plain case: every element is a slot. Hidden ones are
                // zero-widthed by the spread (needed when allowRemoval is
                // NO, e.g. re-asserting from inside a layout pass).
                [plainElements addObject:sub];
                if (hidden) [plainHidden addObject:sub];
            }
        }
    }

    // Plain-view case: group every element under the first ancestor whose
    // direct children include >= 2 slot views; the slot is the element's
    // direct child under that container.
    for (UIView *el in plainElements) {
        UIView *container = el.superview;
        while (container) {
            NSInteger n = 0;
            for (UIView *c in container.subviews) if (smIsSlotView(c)) n++;
            if (n >= 2) break;
            container = container.superview;
        }
        UIView *slot = el;
        while (slot.superview && slot.superview != container) slot = slot.superview;
        smRecordSlot(slotsByContainer, hiddenByContainer, container, slot,
                     [plainHidden containsObject:el]);
    }

    // Spread: sort each container's slots by x; visible slots get equal
    // widths across the full width; hidden slots are zero-widthed and parked
    // off the right edge.
    for (NSValue *pk in slotsByContainer) {
        UIView *container = pk.nonretainedObjectValue;
        NSArray<UIView *> *slots = [slotsByContainer[pk]
            sortedArrayUsingComparator:^NSComparisonResult(UIView *a, UIView *b) {
                if (a.frame.origin.x < b.frame.origin.x) return NSOrderedAscending;
                if (a.frame.origin.x > b.frame.origin.x) return NSOrderedDescending;
                return NSOrderedSame;
            }];
        if (slots.count == 0) continue;
        CGFloat width = container.bounds.size.width;
        if (width <= 0) width = ((UIView *)slots.lastObject).frame.origin.x
                              + ((UIView *)slots.lastObject).frame.size.width;
        if (width <= 0) continue;

        NSSet<UIView *> *hidden = hiddenByContainer[pk] ?: [NSSet set];
        NSMutableArray<UIView *> *visible = [NSMutableArray array];
        for (UIView *slot in slots) if (![hidden containsObject:slot]) [visible addObject:slot];
        if (visible.count == 0) continue;

        CGFloat slotW = width / (CGFloat)visible.count;
        CGFloat y = visible.firstObject.frame.origin.y;
        CGFloat h = visible.firstObject.frame.size.height;
        if (h <= 0) h = container.bounds.size.height;
        CGFloat x = 0;
        for (UIView *slot in slots) {
            CGRect f = slot.frame;
            if ([hidden containsObject:slot]) {
                f.origin.x = width; // zero-width, parked off the right edge
                f.size.width = 0;
            } else {
                f.origin.x = x;
                f.size.width = slotW;
                x += slotW;
            }
            f.origin.y = y;
            f.size.height = h;
            // Idempotent: only write frames that differ, so re-asserting
            // from inside layout passes converges instead of looping.
            // (Inline comparison — CGRectEqualToRect is not linkable with
            // this framework set.)
            if (slot.frame.origin.x != f.origin.x || slot.frame.origin.y != f.origin.y
                || slot.frame.size.width != f.size.width || slot.frame.size.height != f.size.height) {
                slot.frame = f;
            }
        }
        os_log(spotLog(), "SpotifyMod: tab layout: %lu visible of %lu slots in %@",
               (unsigned long)visible.count, (unsigned long)slots.count,
               NSStringFromClass(container.class));
    }
}

// Safety net: a layout hiccup must log, never crash the app.
static void smApplyBarLayout(UIView *root, BOOL allowRemoval) {
    @try {
        smApplyBarLayoutUnsafe(root, allowRemoval);
    } @catch (NSException *e) {
        os_log(spotLog(), "SpotifyMod: tab layout error: %@", e);
    }
}

// --- hooks ------------------------------------------------------------------
// Each hook captures its original IMP in its own __block local — never a
// shared static across classes (that mismatch crashed v0.0.5).

static void hookContainerViewController(void) {
    if (!smContainerCls) return;

    // Data-level: drop hidden VCs before the items are built from them.
    __block IMP orig_setVCs = NULL;
    orig_setVCs = sptHookInstance(smContainerCls, @selector(setViewControllers:),
        ^void(id self, NSArray *viewControllers) {
            if (![viewControllers isKindOfClass:[NSArray class]] || viewControllers.count == 0) {
                ((void(*)(id, SEL, id))orig_setVCs)(self, @selector(setViewControllers:), viewControllers);
                return;
            }
            if (!smEnabled(kSMHideExtraTabs)) {
                ((void(*)(id, SEL, id))orig_setVCs)(self, @selector(setViewControllers:), viewControllers);
                return;
            }
            NSMutableArray *kept = [NSMutableArray arrayWithCapacity:viewControllers.count];
            BOOL droppedAny = NO;
            for (id vc in viewControllers) {
                SMHiddenKind kind = smHiddenKindForVC(vc);
                BOOL drop = kind != SMHiddenNone;
                if (drop) {
                    droppedAny = YES;
                    os_log(spotLog(), "SpotifyMod: filtering tab VC %@",
                           NSStringFromClass([vc class]));
                    continue;
                }
                [kept addObject:vc];
            }
            ((void(*)(id, SEL, id))orig_setVCs)(self, @selector(setViewControllers:),
                droppedAny ? kept : viewControllers);
        });

    // Post-layout trigger: the VC's view layout has fully completed here, so
    // mutating cell frames is safe.
    __block IMP orig_viewDidLayout = NULL;
    orig_viewDidLayout = sptHookInstance(smContainerCls, @selector(viewDidLayoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_viewDidLayout)(self, @selector(viewDidLayoutSubviews));
            UIView *v = [self valueForKey:@"view"];
            if (v) smApplyBarLayout(smBarRootForView(v), YES);
        });
}

static void hookElementInstall(void) {
    // Scan from the BAR ROOT of the installed element (never just the
    // element's own parent — that can't spread a bar).
    if (smElementCls) {
        __block IMP orig_move = NULL;
        orig_move = sptHookInstance(smElementCls, @selector(didMoveToWindow),
            ^void(id self) {
                ((void(*)(id, SEL))orig_move)(self, @selector(didMoveToWindow));
                UIView *el = self;
                if (!el.window) return;
                UIView *bar = smBarRootForView(el);
                dispatch_async(dispatch_get_main_queue(), ^{
                    smApplyBarLayout(bar, YES);
                });
            });

        // Re-assert the spread whenever the app re-positions ANY item.
        // layoutSubviews fires after every repositioning regardless of the
        // mechanism (manual frames, constraints, or collection layout), so
        // this wins every layout fight. Idempotent (only frames that differ
        // are written), so it converges instead of looping.
        __block IMP orig_elLayout = NULL;
        orig_elLayout = sptHookInstance(smElementCls, @selector(layoutSubviews),
            ^void(id self) {
                ((void(*)(id, SEL))orig_elLayout)(self, @selector(layoutSubviews));
                UIView *el = self;
                if (!el.window) return;
                smApplyBarLayout(smBarRootForView(el), NO);
            });
    }

    if (smCreateContentCls) {
        __block IMP orig_createMove = NULL;
        orig_createMove = sptHookInstance(smCreateContentCls, @selector(didMoveToWindow),
            ^void(id self) {
                ((void(*)(id, SEL))orig_createMove)(self, @selector(didMoveToWindow));
                UIView *cv = self;
                if (!cv.window) return;
                UIView *bar = smBarRootForView(cv);
                dispatch_async(dispatch_get_main_queue(), ^{
                    smApplyBarLayout(bar, YES);
                });
            });
    }
}

// Spread-only re-application right after the collection view's own layout:
// the collection re-positions cells on every layout pass, so we re-assert
// the spread immediately after it. No removal here (mutating the tree inside
// a collection layout pass is the risky path).
static void hookCollectionLayout(void) {
    if (!smTabsViewCls) return;
    __block IMP orig_layout = NULL;
    orig_layout = sptHookInstance(smTabsViewCls, @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_layout)(self, @selector(layoutSubviews));
            smApplyBarLayout(self, NO);
        });
}

static void fixTabBar(void) {
    smElementCls = NSClassFromString(@"_TtC23NavigationUI_TabBarImpl21TabBarItemElementView");
    smCreateContentCls = NSClassFromString(@"_TtC22CreateMenu_TabPageImpl24CreateMenuTabBarItemView");
    smCreateTabCls = NSClassFromString(@"_TtC29CreateMenu_CreateMenuPageImpl13CreateTabView");
    smContainerCls = NSClassFromString(@"_TtC23NavigationUI_TabBarImpl15TabBarContainer");
    smTabsViewCls = NSClassFromString(@"_TtCE14Encore_TabsKitO16EncoreFoundation6Encore8TabsView");
    smPremiumVCCls = NSClassFromString(@"_TtC40PremiumUpsell_PremiumDestinationPageImpl17PDPViewController");
    smCreateVCCls = NSClassFromString(@"_TtC29CreateMenu_CreateMenuPageImpl24CreateMenuViewController");

    if (!smContainerCls) {
        os_log(spotLog(), "SpotifyMod: tab bar container class missing - tab hiding unavailable");
        return;
    }
    hookContainerViewController();
    hookElementInstall();
    hookCollectionLayout();
}

// --- runtime hierarchy dump --------------------------------------------------
// One-shot diagnostic: logs the bar container and the ancestry of the first
// tab element (classes, frames, identifiers, labels). If the spread still
// misbehaves on device, these lines show exactly what the bar is made of.

static void smDumpView(UIView *v, const char *prefix) {
    if (!v) return;
    os_log(spotLog(), "SpotifyMod: %s %@ frame=%@ id=%@ label=%@", prefix,
           NSStringFromClass(v.class), NSStringFromCGRect(v.frame),
           v.accessibilityIdentifier ?: @"-", v.accessibilityLabel ?: @"-");
}

static void smDumpBarOnce(void) {
    UIWindow *window = [UIApplication sharedApplication].windows.firstObject;
    if (!window || !smElementCls) return;

    // find the first element and its bar root
    UIView *firstEl = nil;
    NSMutableArray<UIView *> *stack = [NSMutableArray arrayWithObject:window];
    while (stack.count && !firstEl) {
        UIView *v = stack.lastObject;
        [stack removeLastObject];
        for (UIView *sub in v.subviews) {
            if ([sub isKindOfClass:smElementCls]) { firstEl = sub; break; }
            [stack addObject:sub];
        }
    }
    if (!firstEl) {
        os_log(spotLog(), "SpotifyMod: dump: no tab elements found");
        return;
    }

    os_log(spotLog(), "SpotifyMod: --- tab bar hierarchy dump ---");
    UIView *v = firstEl;
    int depth = 0;
    while (v && depth < 14) {
        char buf[32];
        snprintf(buf, sizeof(buf), "[%d]", depth);
        smDumpView(v, buf);
        v = v.superview;
        depth++;
    }
    UIView *bar = smBarRootForView(firstEl);
    if (bar) {
        os_log(spotLog(), "SpotifyMod: bar %@ frame=%@ children=%lu",
               NSStringFromClass(bar.class), NSStringFromCGRect(bar.frame),
               (unsigned long)bar.subviews.count);
        for (UIView *c in bar.subviews) smDumpView(c, "   child");
    }
    os_log(spotLog(), "SpotifyMod: --- end dump ---");
}

// Delayed self-heal: the bar can install items after launch (network /
// account state). Scan the window every second for a while, applying from
// each element's bar root.
static void smScheduleSelfHeal(void) {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        smDumpBarOnce();
    });
    int delays[] = { 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60 };
    for (size_t i = 0; i < sizeof(delays) / sizeof(delays[0]); i++) {
        int delay = delays[i];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            UIWindow *window = [UIApplication sharedApplication].windows.firstObject;
            if (!window || !smElementCls) return;
            NSMutableSet<UIView *> *bars = [NSMutableSet set];
            NSMutableArray<UIView *> *stack = [NSMutableArray arrayWithObject:window];
            while (stack.count) {
                UIView *v = stack.lastObject;
                [stack removeLastObject];
                for (UIView *sub in v.subviews) {
                    if ([sub isKindOfClass:smElementCls]) {
                        UIView *bar = smBarRootForView(sub);
                        if (bar) [bars addObject:bar];
                    }
                    [stack addObject:sub];
                }
            }
            for (UIView *bar in bars) smApplyBarLayout(bar, YES);
        });
    }
}

// One-time migration from the v0.0.7 two-toggle layout.
static void smMigrateOldToggles(void) {
    NSUserDefaults *d = [NSUserDefaults standardUserDefaults];
    if ([d objectForKey:kSMHideExtraTabs] == nil) {
        BOOL old = [d boolForKey:@"SpotifyModHidePremiumTab"] || [d boolForKey:@"SpotifyModHideCreateTab"];
        [d setBool:old forKey:kSMHideExtraTabs];
    }
    [d removeObjectForKey:@"SpotifyModHidePremiumTab"];
    [d removeObjectForKey:@"SpotifyModHideCreateTab"];
}

void SpotifyTabBarFixInit(void) {
    smMigrateOldToggles();
    if (!smEnabled(kSMHideExtraTabs)) {
        os_log(spotLog(), "SpotifyMod: tab hiding disabled");
        return;
    }
    fixTabBar();
    smScheduleSelfHeal();
}
