// FeedShorts.m — feed (G10) and Shorts (G11) toggles + the consolidated
// _ASDisplayView and YTInnerTubeCollectionViewController hooks (single hook
// per method across the whole dylib; AdBlock's ad filtering funnels through
// ytfFilterAdSections, this file's feed filtering through ytfFilterFeedSections).
//
// Ported from YouMod's Feed.x / Shorts.x / Sideloading.x (_ASDisplayView
// accessibility-identifier hiding). Every identifier and selector was
// verified against the 21.32.4 binary.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

@protocol YTFreedomFeedHooks <NSObject>
@optional
- (void)setSuggestions:(id)suggestions;
- (id)activeCache;
- (void)setChipFilterView:(id)view;
- (void)enableSubheaderBarWithView:(id)view;
- (BOOL)shouldAlwaysEnablePlayerBar;
- (BOOL)shouldEnablePlayerBarOnlyOnPause;
- (void)setHidden:(BOOL)hidden;
@end

// --- Shorts-shelf removal (YTUnShorts lineage) ------------------------------

NSArray *ytfFilterFeedSections(NSArray *array) {
    if (!IS_ENABLED(KHideShortsShelf)) return array;
    if (![array isKindOfClass:[NSArray class]]) return array;
    static Class shelfCls, itemSectionCls;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        shelfCls = NSClassFromString(@"YTIShelfRenderer");
        itemSectionCls = NSClassFromString(@"YTIItemSectionRenderer");
    });

    NSMutableArray *newArray = [array mutableCopy];
    NSIndexSet *removeIndexes = [newArray indexesOfObjectsPassingTest:
        ^BOOL(id sectionRenderer, NSUInteger idx, BOOL *stop) {
            if ([sectionRenderer isKindOfClass:shelfCls]) {
                id content = [sectionRenderer valueForKey:@"content"];
                id horizontalList = [content valueForKey:@"horizontalListRenderer"];
                NSMutableArray *itemsArray = [horizontalList valueForKey:@"itemsArray"];
                if ([itemsArray isKindOfClass:[NSMutableArray class]]) {
                    NSIndexSet *removeItems = [itemsArray indexesOfObjectsPassingTest:
                        ^BOOL(id item, NSUInteger i2, BOOL *s2) {
                            NSString *description = [[item valueForKey:@"elementRenderer"] description];
                            return [description containsString:@"shorts_video_cell"];
                        }];
                    return removeItems.count > 0;
                }
                return NO;
            }
            if ([sectionRenderer isKindOfClass:itemSectionCls]) {
                NSString *description = [sectionRenderer description];
                return [description containsString:@"shorts_shelf.eml"];
            }
            return NO;
        }];
    if (removeIndexes.count > 0) [newArray removeObjectsAtIndexes:removeIndexes];
    return newArray;
}

// --- consolidated YTInnerTubeCollectionViewController hook ------------------

static BOOL sectionRenderersIvarExists(Class cls) {
    static void *key = &key;
    NSNumber *cached = objc_getAssociatedObject(cls, key);
    if (cached) return cached.boolValue;
    BOOL found = NO;
    unsigned int count = 0;
    Ivar *ivars = class_copyIvarList(cls, &count);
    for (unsigned int i = 0; i < count; i++) {
        if (!strcmp(ivar_getName(ivars[i]), "_sectionRenderers")) { found = YES; break; }
    }
    free(ivars);
    objc_setAssociatedObject(cls, key, @(found), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return found;
}

void ytfConfigureCollectionView(void) {
    Class collectionVC = NSClassFromString(@"YTInnerTubeCollectionViewController");

    static IMP orig_displaySections;
    orig_displaySections = ytfHookInstance(collectionVC,
        @selector(displaySectionsWithReloadingSectionControllerByRenderer:),
        ^void(id self, id renderer) {
            if (sectionRenderersIvarExists([self class])) {
                NSMutableArray *sections = [self valueForKey:@"_sectionRenderers"];
                if ([sections isKindOfClass:[NSArray class]]) {
                    NSArray *filtered = ytfFilterFeedSections(ytfFilterAdSections(sections));
                    [self setValue:filtered forKey:@"_sectionRenderers"];
                }
            }
            ((void(*)(id, SEL, id))orig_displaySections)(
                self, @selector(displaySectionsWithReloadingSectionControllerByRenderer:), renderer);
        });
    (void)orig_displaySections;

    static IMP orig_addSections;
    orig_addSections = ytfHookInstance(collectionVC,
        @selector(addSectionsFromArray:),
        ^void(id self, NSArray *array) {
            ((void(*)(id, SEL, id))orig_addSections)(
                self, @selector(addSectionsFromArray:),
                ytfFilterFeedSections(ytfFilterAdSections(array)));
        });
    (void)orig_addSections;
}

// --- consolidated _ASDisplayView hook: element hiding by accessibility id ---

void ytfConfigureASDisplayView(void) {
    static IMP orig_didMoveToWindow;
    orig_didMoveToWindow = ytfHookInstance(NSClassFromString(@"_ASDisplayView"),
        @selector(didMoveToWindow),
        ^void(id self) {
            ((void(*)(id, SEL))orig_didMoveToWindow)(self, @selector(didMoveToWindow));
            UIView *view = (UIView *)self;
            NSString *aid = view.accessibilityIdentifier;

            // Ads (AdBlock).
            if ([aid isEqualToString:@"eml.expandable_metadata.vpp"]) {
                [view removeFromSuperview];
                return;
            }
            if ([aid hasPrefix:@"eml.ad_layout."]) {
                view.hidden = YES;
                return;
            }

            // Feed / player buttons.
            if ((IS_ENABLED(KHideGenMusicShelf) && [aid isEqualToString:@"feed_nudge.view"])
                || (IS_ENABLED(KHideFeedPost) && [aid isEqualToString:@"id.ui.backstage.original_post"])
                || (IS_ENABLED(KHideLikeButton) && [aid isEqualToString:@"id.video.like.button"])
                || (IS_ENABLED(KHideDisLikeButton) && [aid isEqualToString:@"id.video.dislike.button"])
                || (IS_ENABLED(KHideShareButton) && [aid isEqualToString:@"id.video.share.button"])
                || (IS_ENABLED(KHideDownloadButton) && [aid isEqualToString:@"id.ui.add_to.offline.button"])
                || (IS_ENABLED(KHideClipButton) && [aid isEqualToString:@"clip_button.eml"])
                || (IS_ENABLED(KHideRemixButton) && [aid isEqualToString:@"id.video.remix.button"])
                || (IS_ENABLED(KHideSaveButton) && [aid isEqualToString:@"id.video.add_to.button"])
                || (IS_ENABLED(KHideSubButton) && [aid isEqualToString:@"eml.animated_subscribe_button"])
                || (IS_ENABLED(KHideShoppingButton) && [aid isEqualToString:@"eml.header_store_button"])
                || (IS_ENABLED(KHideMemberButton) && [aid isEqualToString:@"id.sponsor_button"])
                // Shorts buttons.
                || (IS_ENABLED(KHideShortsLikeButton) && [aid isEqualToString:@"id.reel_like_button"])
                || (IS_ENABLED(KHideShortsDisLikeButton) && [aid isEqualToString:@"id.reel_dislike_button"])
                || (IS_ENABLED(KHideShortsCommentButton) && [aid isEqualToString:@"id.reel_comment_button"])
                || (IS_ENABLED(KHideShortsShareButton) && [aid isEqualToString:@"id.reel_share_button"])
                || (IS_ENABLED(KHideShortsRemixButton) && [aid isEqualToString:@"id.reel_remix_button"])
                || (IS_ENABLED(KHideShortsMetaButton) && [aid isEqualToString:@"id.reel_pivot_button"])
                || (IS_ENABLED(KHideShortsProducts) && [aid isEqualToString:@"product_sticker.main_target"])
                || (IS_ENABLED(KHideShortsProducts) && [aid isEqualToString:@"product_sticker.secondary_target"])
                || (IS_ENABLED(KHideShortsRecbar) && [aid isEqualToString:@"id.elements.components.suggested_action"])
                || (IS_ENABLED(KHideShortsCommit) && [aid isEqualToString:@"eml.shorts-disclosures"])
                || (IS_ENABLED(KHideShortsSubscriptButton) && [aid isEqualToString:@"id.ui.shorts_paused_state.subscriptions_button"])
                || (IS_ENABLED(KHideShortsLiveButton) && [aid isEqualToString:@"id.ui.shorts_paused_state.live_button"])
                || (IS_ENABLED(KHideShortsLensButton) && [aid isEqualToString:@"id.ui.shorts_paused_state.lens_button"])
                || (IS_ENABLED(KHideShortsTrendsButton) && [aid isEqualToString:@"id.ui.shorts_paused_state.trends_button"])
                || (IS_ENABLED(KHideShortsToVideo) && [aid isEqualToString:@"id.reel_multi_format_link"])) {
                view.hidden = YES;
            }
        });
    (void)orig_didMoveToWindow;
}

// --- Watch-page action bar (both slim variants) -----------------------------
// The like/dislike/share/save/download row between the title and comments is
// rendered by YTSlimVideoDetailsActionView (a plain UIView — the old
// _ASDisplayView id-hook never saw it). The button's accessibility id is
// assigned in updateAccessibilityIdentifier; hide there (and on
// didMoveToWindow as a backstop) so both the slim and scrollable renderer
// variants are covered.
static BOOL ytfWatchActionBarHidden(NSString *aid) {
    if (!aid) return NO;
    if (IS_ENABLED(KHideLikeButton) && [aid isEqualToString:@"id.video.like.button"]) return YES;
    if (IS_ENABLED(KHideDisLikeButton) && [aid isEqualToString:@"id.video.dislike.button"]) return YES;
    if (IS_ENABLED(KHideShareButton) && [aid isEqualToString:@"id.video.share.button"]) return YES;
    if (IS_ENABLED(KHideSaveButton) && [aid isEqualToString:@"id.video.add_to.button"]) return YES;
    if (IS_ENABLED(KHideDownloadButton) && [aid isEqualToString:@"id.ui.add_to.offline.button"]) return YES;
    return NO;
}

static void fixWatchActionBar(void) {
    static IMP orig_updateAID;
    orig_updateAID = ytfHookInstance(NSClassFromString(@"YTSlimVideoDetailsActionView"),
        @selector(updateAccessibilityIdentifier),
        ^void(id self) {
            ((void(*)(id, SEL))orig_updateAID)(self, @selector(updateAccessibilityIdentifier));
            if (ytfWatchActionBarHidden([(UIView *)self accessibilityIdentifier]))
                ((UIView *)self).hidden = YES;
        });
    (void)orig_updateAID;
    static IMP orig_didMove;
    orig_didMove = ytfHookInstance(NSClassFromString(@"YTSlimVideoDetailsActionView"),
        @selector(didMoveToWindow),
        ^void(id self) {
            ((void(*)(id, SEL))orig_didMove)(self, @selector(didMoveToWindow));
            if (ytfWatchActionBarHidden([(UIView *)self accessibilityIdentifier]))
                ((UIView *)self).hidden = YES;
        });
    (void)orig_didMove;
}

// --- G10: feed --------------------------------------------------------------

static void fixFeed(void) {
    // Hide subbar (channel filter chips).
    static IMP orig_setChipFilterView;
    orig_setChipFilterView = ytfHookInstance(NSClassFromString(@"YTMySubsFilterHeaderView"),
        @selector(setChipFilterView:),
        ^void(id self, id view) {
            if (!IS_ENABLED(KHideSubbar))
                ((void(*)(id, SEL, id))orig_setChipFilterView)(self, @selector(setChipFilterView:), view);
        });
    (void)orig_setChipFilterView;

    static IMP orig_enableSubheaderBar;
    orig_enableSubheaderBar = ytfHookInstance(NSClassFromString(@"YTHeaderContentComboView"),
        @selector(enableSubheaderBarWithView:),
        ^void(id self, id view) {
            if (!IS_ENABLED(KHideSubbar))
                ((void(*)(id, SEL, id))orig_enableSubheaderBar)(self, @selector(enableSubheaderBarWithView:), view);
        });
    (void)orig_enableSubheaderBar;

    static IMP orig_chipLayout;
    orig_chipLayout = ytfHookInstance(NSClassFromString(@"YTChipCloudCell"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_chipLayout)(self, @selector(layoutSubviews));
            if (IS_ENABLED(KHideSubbar) && [(UIView *)self superview])
                [(UIView *)self removeFromSuperview];
        });
    (void)orig_chipLayout;

    // Search: voice search + history/suggestions.
    static IMP orig_searchViewDidLoad;
    orig_searchViewDidLoad = ytfHookInstance(NSClassFromString(@"YTSearchViewController"),
        @selector(viewDidLoad),
        ^void(id self) {
            ((void(*)(id, SEL))orig_searchViewDidLoad)(self, @selector(viewDidLoad));
            if (IS_ENABLED(KHideVoiceSearch))
                [self setValue:@NO forKey:@"_isVoiceSearchAllowed"];
        });
    (void)orig_searchViewDidLoad;

    static IMP orig_setSuggestions;
    orig_setSuggestions = ytfHookInstance(NSClassFromString(@"YTSearchViewController"),
        @selector(setSuggestions:),
        ^void(id self, id suggestions) {
            if (!IS_ENABLED(KHideSearchHis))
                ((void(*)(id, SEL, id))orig_setSuggestions)(self, @selector(setSuggestions:), suggestions);
        });
    (void)orig_setSuggestions;

    static IMP orig_activeCache;
    orig_activeCache = ytfHookInstance(NSClassFromString(@"YTPersonalizedSuggestionsCacheProvider"),
        @selector(activeCache),
        ^id(id self) {
            return IS_ENABLED(KHideSearchHis) ? nil
                : ((id(*)(id, SEL))orig_activeCache)(self, @selector(activeCache));
        });
    (void)orig_activeCache;
}

// --- G11: Shorts ------------------------------------------------------------

static void fixShorts(void) {
    // Enable the Shorts quality picker.
    NSArray *qualityConfigs = @[
        @"enableOmitAdvancedMenuInShortsVideoQualityPicker",
        @"enableShortsVideoQualityPicker",
        @"iosEnableImmersiveLivePlayerVideoQuality",
        @"iosEnableShortsPlayerVideoQuality",
        @"iosEnableShortsPlayerVideoQualityRestartVideo",
        @"iosEnableSimplerTitleInShortsVideoQualityPicker",
    ];
    Class hotConfig = NSClassFromString(@"YTHotConfig");
    for (NSString *selName in qualityConfigs) {
        SEL sel = NSSelectorFromString(selName);
        Method m = class_getInstanceMethod(hotConfig, sel);
        if (!m) continue;
        IMP orig = method_getImplementation(m);
        class_replaceMethod(hotConfig, sel,
            imp_implementationWithBlock(^BOOL(id self) {
                return IS_ENABLED(KEnablesShortsQuality) ? YES
                    : ((BOOL(*)(id, SEL))orig)(self, sel);
            }), method_getTypeEncoding(m));
    }

    // Always show the Shorts seekbar / player bar.
    NSArray *playerBarClasses = @[
        NSClassFromString(@"YTShortsPlayerViewController"),
        NSClassFromString(@"YTReelPlayerViewController"),
    ];
    for (Class cls in playerBarClasses) {
        if (!cls) continue;
        Method mAlways = class_getInstanceMethod(cls, sel_registerName("shouldAlwaysEnablePlayerBar"));
        if (mAlways) {
            IMP origAlways = method_getImplementation(mAlways);
            class_replaceMethod(cls, sel_registerName("shouldAlwaysEnablePlayerBar"),
                imp_implementationWithBlock(^BOOL(id self) {
                    return IS_ENABLED(KShowShortsSeekbar) ? YES
                        : ((BOOL(*)(id, SEL))origAlways)(self, sel_registerName("shouldAlwaysEnablePlayerBar"));
                }), method_getTypeEncoding(mAlways));
        }
        Method mPause = class_getInstanceMethod(cls, sel_registerName("shouldEnablePlayerBarOnlyOnPause"));
        if (mPause) {
            IMP origPause = method_getImplementation(mPause);
            class_replaceMethod(cls, sel_registerName("shouldEnablePlayerBarOnlyOnPause"),
                imp_implementationWithBlock(^BOOL(id self) {
                    return IS_ENABLED(KShowShortsSeekbar) ? NO
                        : ((BOOL(*)(id, SEL))origPause)(self, sel_registerName("shouldEnablePlayerBarOnlyOnPause"));
                }), method_getTypeEncoding(mPause));
        }
    }

    static IMP orig_iosEnableVideoPlayerScrubber;
    orig_iosEnableVideoPlayerScrubber = ytfHookInstance(NSClassFromString(@"YTColdConfig"),
        @selector(iosEnableVideoPlayerScrubber),
        ^BOOL(id self) {
            return IS_ENABLED(KShowShortsSeekbar) ? YES
                : ((BOOL(*)(id, SEL))orig_iosEnableVideoPlayerScrubber)(
                    self, @selector(iosEnableVideoPlayerScrubber));
        });
    (void)orig_iosEnableVideoPlayerScrubber;

    // New-IPA Shorts UX: playback speed from the ⋯ menu, inline playback on
    // the home Shorts shelf.
    Class coldConfig = NSClassFromString(@"YTColdConfig");
    ytfHookConfigBool(coldConfig,
        @selector(shortsConsumptionClientGlobalConfigIosEnableShortsPlaybackSpeedFromMenu),
        ^BOOL { return IS_ENABLED(KShortsPlaybackSpeed); });
    ytfHookConfigBool(coldConfig, @selector(iosEnableInlinePlaybackOnShortsShelf),
        ^BOOL { return IS_ENABLED(KInlineShortsPlayback); });

    // Diagnostic (research aid for the "Shorts has no dislike button"
    // report): the Shorts action rail is server-driven — the client renders
    // whatever button entries the renderer's actionBarButtonsArray contains.
    // Log them so the device log shows whether the server sent a dislike
    // entry (icon 42?/aid id.reel_dislike_button) or omitted it entirely.
    static IMP orig_setActionBarElementRenderer;
    orig_setActionBarElementRenderer = ytfHookInstance(
        NSClassFromString(@"YTReelWatchPlaybackOverlayView"),
        @selector(setActionBarElementRenderer:),
        ^void(id self, id renderer) {
            ((void(*)(id, SEL, id))orig_setActionBarElementRenderer)(
                self, @selector(setActionBarElementRenderer:), renderer);
            NSArray *buttons = [renderer valueForKey:@"actionBarButtonsArray"];
            NSMutableArray *summary = [NSMutableArray array];
            for (id button in buttons) {
                NSString *aid = [button valueForKey:@"accessibilityIdentifier"];
                [summary addObject:[NSString stringWithFormat:@"icon=%@ aid=%@",
                                    [button valueForKey:@"iconType"], aid]];
            }
            os_log(ytfLog(), "YTFreedom: reel action bar buttons from server: %@", summary);
        });
    (void)orig_setActionBarElementRenderer;
}

void YTFreedomFeedShortsInit(void) {
    ytfConfigureASDisplayView();
    ytfConfigureCollectionView();
    fixFeed();
    fixShorts();
    fixWatchActionBar();
}
