// AdBlock.m — player + feed + Shorts ad removal (port of YouMod Ads.x,
// built for exactly 21.32.4; all classes/selectors verified in the binary).
//
// Covers every layer of the modern ads pipeline:
//   - data:    YTPlayerResponse +playerAdsArray/+adSlotsArray (empty),
//              YTIClientMdxGlobalConfig +enableSkippableAd
//   - playback: YTLocalPlaybackController createAdsPlaybackCoordinator -> nil,
//              MDXSessionImpl adPlaying: no-op, adapter backstops
//   - request: YTAdsInnerTubeContextDecorator / YTAccountScopedAdsInnerTube-
//              ContextDecorator decorateContext: -> orig(nil),
//              YTAdShieldUtils spamSignalsDictionary* -> {}
//   - feed:    YTInnerTubeCollectionViewController section filtering by
//              YTIElementRenderer ad detection; _ASDisplayView hiding of
//              in-player ad overlays; product-in-video overlay dropped;
//              Shorts ad reels filtered via isAdVideo.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

// Selectors on YouTube classes not declared in any SDK header; presence is
// guarded with respondsToSelector: before each call.
@protocol YTFreedomAdHooks <NSObject>
@optional
- (BOOL)hasCompatibilityOptions;
- (id)compatibilityOptions;
- (BOOL)hasAdLoggingData;
- (NSString *)overlayIdentifier;
- (BOOL)isAdVideo;
@end

static NSArray<NSString *> *ytAdStrings(void) {
    return @[
        @"brand_promo",
        @"carousel_footered_layout",
        @"carousel_headered_layout",
        @"eml.expandable_metadata",
        @"feed_ad_metadata",
        @"full_width_portrait_image_layout",
        @"full_width_square_image_layout",
        @"landscape_image_wide_button_layout",
        @"post_shelf",
        @"product_carousel",
        @"product_engagement_panel",
        @"product_item",
        @"shopping_carousel",
        @"shopping_item_card_list",
        @"statement_banner",
        @"square_image_layout",
        @"text_image_button_layout",
        @"text_search_ad",
        @"video_display_full_layout",
        @"video_display_full_buttoned_layout",
    ];
}

static BOOL isAdElementRenderer(id elementRenderer) {
    if (!elementRenderer) return NO;
    id<YTFreedomAdHooks> renderer = elementRenderer;
    if ([renderer respondsToSelector:@selector(hasCompatibilityOptions)]
        && [renderer hasCompatibilityOptions]) {
        id<YTFreedomAdHooks> compat = [renderer compatibilityOptions];
        if (compat && [compat respondsToSelector:@selector(hasAdLoggingData)]
            && [compat hasAdLoggingData]) {
            return YES;
        }
    }
    NSString *description = [elementRenderer description];
    for (NSString *adStr in ytAdStrings()) {
        if ([description containsString:adStr]) return YES;
    }
    return NO;
}

// Drop ad sections/cards from a collection view's section-renderer array.
// Owned by FeedShorts.m's consolidated YTInnerTubeCollectionViewController
// hook (ytfConfigureCollectionView) — exported here.
NSArray *ytfFilterAdSections(NSArray *array) {
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
                            return isAdElementRenderer([item valueForKey:@"elementRenderer"]);
                        }];
                    if (removeItems.count > 0) [itemsArray removeObjectsAtIndexes:removeItems];
                }
            }
            if (![sectionRenderer isKindOfClass:itemSectionCls])
                return NO;
            NSMutableArray *contentsArray = [sectionRenderer valueForKey:@"contentsArray"];
            if (![contentsArray isKindOfClass:[NSMutableArray class]])
                return NO;
            if (contentsArray.count > 1) {
                NSIndexSet *removeContents = [contentsArray indexesOfObjectsPassingTest:
                    ^BOOL(id item, NSUInteger i2, BOOL *s2) {
                        return isAdElementRenderer([item valueForKey:@"elementRenderer"]);
                    }];
                if (removeContents.count > 0) [contentsArray removeObjectsAtIndexes:removeContents];
            }
            id firstObject = [contentsArray firstObject];
            return isAdElementRenderer([firstObject valueForKey:@"elementRenderer"]);
        }];
    if (removeIndexes.count > 0) [newArray removeObjectsAtIndexes:removeIndexes];
    return newArray;
}

// Feed-section ad filtering lives in FeedShorts.m's consolidated
// YTInnerTubeCollectionViewController hook (ytfConfigureCollectionView),
// which calls ytfFilterAdSections above. Nothing else to hook here.
static void fixFeedAds(void) {}

static void fixPlayerResponseAds(void) {
    Class playerResponse = NSClassFromString(@"YTPlayerResponse");
    ytfAddInstanceMethod(playerResponse, sel_registerName("playerAdsArray"),
                         ^id(id self) { return [NSMutableArray array]; }, "@@:");
    ytfAddInstanceMethod(playerResponse, sel_registerName("adSlotsArray"),
                         ^id(id self) { return [NSMutableArray array]; }, "@@:");
    ytfAddInstanceMethod(NSClassFromString(@"YTIClientMdxGlobalConfig"),
                         sel_registerName("enableSkippableAd"),
                         ^BOOL(id self) { return YES; }, "B@:");

    static IMP orig_createAdsPlaybackCoordinator;
    orig_createAdsPlaybackCoordinator = ytfHookInstance(
        NSClassFromString(@"YTLocalPlaybackController"),
        @selector(createAdsPlaybackCoordinator),
        ^id(id self) { return nil; });
    (void)orig_createAdsPlaybackCoordinator;

    static IMP orig_spamSignals, orig_spamSignalsNoIDFA;
    orig_spamSignals = ytfHookClass(NSClassFromString(@"YTAdShieldUtils"),
        @selector(spamSignalsDictionary), ^id(id cls) { return @{}; });
    orig_spamSignalsNoIDFA = ytfHookClass(NSClassFromString(@"YTAdShieldUtils"),
        @selector(spamSignalsDictionaryWithoutIDFA), ^id(id cls) { return @{}; });
    (void)orig_spamSignals;
    (void)orig_spamSignalsNoIDFA;

    static IMP orig_decorateContext;
    orig_decorateContext = ytfHookInstance(
        NSClassFromString(@"YTAdsInnerTubeContextDecorator"),
        @selector(decorateContext:),
        ^void(id self, id context) {
            ((void(*)(id, SEL, id))orig_decorateContext)(self, @selector(decorateContext:), nil);
        });
    (void)orig_decorateContext;

    static IMP orig_decorateContextScoped;
    orig_decorateContextScoped = ytfHookInstance(
        NSClassFromString(@"YTAccountScopedAdsInnerTubeContextDecorator"),
        @selector(decorateContext:),
        ^void(id self, id context) {
            ((void(*)(id, SEL, id))orig_decorateContextScoped)(self, @selector(decorateContext:), nil);
        });
    (void)orig_decorateContextScoped;

    static IMP orig_adPlaying;
    orig_adPlaying = ytfHookInstance(NSClassFromString(@"MDXSessionImpl"),
        @selector(adPlaying:), ^void(id self, id ad) {});
    (void)orig_adPlaying;

    // Ad-break backstops (first iteration, kept).
    ytfHookInstance(NSClassFromString(@"YTAdBreakResponseReceivedOpportunityAdapterV2"),
                    sel_registerName("didReceiveAdBreakResponse:fromAdBreakSlot:"),
                    ^void(id self, id response, id slot) {
                        os_log(ytfLog(), "YTFreedom: dropped ad-break response (%@, slot=%@)",
                               response, slot);
                    });
    ytfHookInstance(NSClassFromString(@"YTAdBreakRendererAdapter"),
                    sel_registerName("createAds"),
                    ^id(id self) {
                        os_log(ytfLog(), "YTFreedom: createAds -> empty");
                        return @[];
                    });
}

// Strongest feed/watch-next ad killer (YTLite's YTIElementRenderer elementData
// hook): any element carrying ad-logging compatibility data renders nothing;
// any element whose description matches a known ad layout renders empty.
// Complements the section-level filtering in ytfFilterAdSections.
static void fixElementDataAds(void) {
    static IMP orig_elementData;
    orig_elementData = ytfHookInstance(NSClassFromString(@"YTIElementRenderer"),
        @selector(elementData),
        ^id(id self) {
            id<YTFreedomAdHooks> renderer = self;
            if ([renderer respondsToSelector:@selector(hasCompatibilityOptions)]
                && [renderer hasCompatibilityOptions]) {
                id<YTFreedomAdHooks> compat = [renderer compatibilityOptions];
                if (compat && [compat respondsToSelector:@selector(hasAdLoggingData)]
                    && [compat hasAdLoggingData]) {
                    return nil;
                }
            }
            NSString *description = [self description];
            for (NSString *adStr in ytAdStrings()) {
                if ([description containsString:adStr])
                    return [NSData data];
            }
            return ((id(*)(id, SEL))orig_elementData)(self, @selector(elementData));
        });
    (void)orig_elementData;
}

static void fixReelAds(void) {
    static BOOL (^isAdReel)(id) = ^BOOL(id model) {
        if (!model || ![model respondsToSelector:@selector(isAdVideo)]) return NO;
        return [(id<YTFreedomAdHooks>)model isAdVideo] == YES;
    };

    static IMP orig_setReels;
    orig_setReels = ytfHookInstance(NSClassFromString(@"YTReelDataSource"),
        @selector(setReels:),
        ^void(id self, id reels) {
            if ([reels respondsToSelector:@selector(indexesOfObjectsPassingTest:)]) {
                NSIndexSet *remove = [reels indexesOfObjectsPassingTest:
                    ^BOOL(id obj, NSUInteger idx, BOOL *stop) { return isAdReel(obj); }];
                if (remove.count > 0) [reels removeObjectsAtIndexes:remove];
            }
            ((void(*)(id, SEL, id))orig_setReels)(self, @selector(setReels:), reels);
        });
    (void)orig_setReels;

    static IMP orig_insertContentModel;
    orig_insertContentModel = ytfHookInstance(NSClassFromString(@"YTReelDataSource"),
        @selector(insertContentModel:atIndex:),
        ^void(id self, id model, NSInteger index) {
            if (isAdReel(model)) return;
            ((void(*)(id, SEL, id, NSInteger))orig_insertContentModel)(
                self, @selector(insertContentModel:atIndex:), model, index);
        });
    (void)orig_insertContentModel;
}

void YTFreedomAdBlockInit(void) {
    fixPlayerResponseAds();
    fixElementDataAds();
    fixFeedAds();
    fixReelAds();
}
