// Appearance.m — OLED theme + keyboard (G13), ported from YouMod's
// Apperence.x (uYouEnhanced OLEDTheme lineage) with the full
// YTCommonColorPalette surface set.
//
// OLED theme: every dark-mode palette surface returns pure black (or a
// slightly-raised black for secondary surfaces). The dark page style is
// palette.pageStyle == 1. NOTE: pageStyle is an NSNumber via KVC — read it
// with integerValue (casting the object pointer to NSInteger silently
// breaks every check; that was the original "OLED does nothing" bug).
//
// OLED keyboard: UIKit keyboard classes are repainted black in dark mode;
// UIKit/Texture classes are hooked via class_getInstanceMethod at runtime
// (no classlist needed) and missing methods no-op gracefully.

#import "YTFreedom.h"
#import <UIKit/UIKit.h>

static BOOL ytfIsDarkMode(void) {
    UIWindow *keyWindow = nil;
    for (UIWindow *window in [UIApplication sharedApplication].windows) {
        if (window.isKeyWindow) { keyWindow = window; break; }
    }
    if (!keyWindow) keyWindow = [UIApplication sharedApplication].windows.firstObject;
    return keyWindow.traitCollection.userInterfaceStyle == UIUserInterfaceStyleDark;
}

static NSInteger ytfPageStyle(id palette) {
    id value = [palette valueForKey:@"pageStyle"];
    return [value respondsToSelector:@selector(integerValue)] ? [value integerValue] : 0;
}

static void fixOLEDTheme(void) {
    if (!IS_ENABLED(KOLEDTheme)) return;

    // YTColor +black0..black4 -> pure black.
    Class ytColor = NSClassFromString(@"YTColor");
    for (int i = 0; i <= 4; i++) {
        SEL sel = NSSelectorFromString([NSString stringWithFormat:@"black%d", i]);
        Method m = class_getClassMethod(ytColor, sel);
        if (!m) continue;
        class_replaceMethod(object_getClass(ytColor), sel,
            imp_implementationWithBlock(^id(id cls) { return [UIColor blackColor]; }),
            method_getTypeEncoding(m));
    }

    // YTCommonColorPalette surfaces -> black for page style 1.
    // background3 is absent in 21.32.4 (guarded); the rest exist.
    NSArray *paletteSelectors = @[
        @"baseBackground", @"brandBackgroundSolid", @"brandBackgroundPrimary",
        @"brandBackgroundSecondary", @"raisedBackground", @"staticBrandBlack",
        @"generalBackgroundA", @"generalBackgroundB", @"menuBackground",
        @"background1", @"background2", @"background3",
    ];
    Class palette = NSClassFromString(@"YTCommonColorPalette");
    for (NSString *selName in paletteSelectors) {
        SEL sel = NSSelectorFromString(selName);
        Method m = class_getInstanceMethod(palette, sel);
        if (!m) continue;
        IMP orig = method_getImplementation(m);
        class_replaceMethod(palette, sel,
            imp_implementationWithBlock(^id(id self) {
                if (ytfPageStyle(self) == 1)
                    return [selName isEqualToString:@"brandBackgroundSecondary"]
                        ? [UIColor colorWithWhite:0 alpha:0.9] : (id)[UIColor blackColor];
                return ((id(*)(id, SEL))orig)(self, sel);
            }), method_getTypeEncoding(m));
    }
}

// Settings tables and dialogs render with a grey system background that the
// palette hooks don't reach — repaint them for a consistent OLED look.
static void fixOLEDSurfaces(void) {
    if (!IS_ENABLED(KOLEDTheme)) return;

    // UITableViewCell's private system background (used by settings rows).
    Class cellCls = [UITableViewCell class];
    Method mCell = class_getInstanceMethod(cellCls, sel_registerName("_layoutSystemBackgroundView"));
    if (mCell) {
        class_replaceMethod(cellCls, sel_registerName("_layoutSystemBackgroundView"),
            imp_implementationWithBlock(^void(id self) {
                id systemBackground = [self valueForKey:@"_systemBackgroundView"];
                id colorView = [systemBackground valueForKey:@"_colorView"];
                if (colorView) [colorView setBackgroundColor:[UIColor blackColor]];
            }), method_getTypeEncoding(mCell));
    }

    // Google dialogs.
    static IMP orig_dialogBackground;
    orig_dialogBackground = ytfHookInstance(NSClassFromString(@"GOODialogView"),
        @selector(setBackgroundColor:),
        ^void(id self, UIColor *color) {
            ((void(*)(id, SEL, id))orig_dialogBackground)(
                self, @selector(setBackgroundColor:), [UIColor blackColor]);
        });
    (void)orig_dialogBackground;

    // Texture collection/scroll views: clear so the black palette shows.
    static IMP orig_collectionDidMove;
    orig_collectionDidMove = ytfHookInstance(NSClassFromString(@"ASCollectionView"),
        @selector(didMoveToWindow),
        ^void(id self) {
            ((void(*)(id, SEL))orig_collectionDidMove)(self, @selector(didMoveToWindow));
            if (ytfIsDarkMode()) {
                [(UIView *)self setBackgroundColor:[UIColor clearColor]];
                [[(UIView *)self superview] setBackgroundColor:[UIColor blackColor]];
            }
        });
    (void)orig_collectionDidMove;

    static IMP orig_scrollDidMove;
    orig_scrollDidMove = ytfHookInstance(NSClassFromString(@"ASScrollView"),
        @selector(didMoveToWindow),
        ^void(id self) {
            ((void(*)(id, SEL))orig_scrollDidMove)(self, @selector(didMoveToWindow));
            if (ytfIsDarkMode())
                [(UIView *)self setBackgroundColor:[UIColor clearColor]];
        });
    (void)orig_scrollDidMove;
}

static void fixOLEDKeyboard(void) {
    if (!IS_ENABLED(KOLEDKeyboard)) return;

    // UIKeyboard: repaint on layer display.
    static IMP orig_keyboardDisplayLayer;
    orig_keyboardDisplayLayer = ytfHookInstance(NSClassFromString(@"UIKeyboard"),
        @selector(displayLayer:),
        ^void(id self, id layer) {
            ((void(*)(id, SEL, id))orig_keyboardDisplayLayer)(self, @selector(displayLayer:), layer);
            [(UIView *)self setBackgroundColor:ytfIsDarkMode() ? [UIColor blackColor] : [UIColor clearColor]];
        });
    (void)orig_keyboardDisplayLayer;

    // Prediction bar.
    static IMP orig_currentTextSuggestions;
    orig_currentTextSuggestions = ytfHookInstance(NSClassFromString(@"UIPredictionViewController"),
        @selector(_currentTextSuggestions),
        ^id(id self) {
            [((UIViewController *)self).view setBackgroundColor:ytfIsDarkMode() ? [UIColor blackColor] : [UIColor clearColor]];
            return ((id(*)(id, SEL))orig_currentTextSuggestions)(self, @selector(_currentTextSuggestions));
        });
    (void)orig_currentTextSuggestions;

    // Keyboard dock.
    static IMP orig_dockLayout;
    orig_dockLayout = ytfHookInstance(NSClassFromString(@"UIKeyboardDockView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_dockLayout)(self, @selector(layoutSubviews));
            [(UIView *)self setBackgroundColor:ytfIsDarkMode() ? [UIColor blackColor] : [UIColor clearColor]];
        });
    (void)orig_dockLayout;

    // Emoji search / autofill panels (UIInputView subclass check).
    static IMP orig_inputViewLayout;
    orig_inputViewLayout = ytfHookInstance(NSClassFromString(@"UIInputView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_inputViewLayout)(self, @selector(layoutSubviews));
            if ([self isKindOfClass:NSClassFromString(@"TUIEmojiSearchInputView")]
                || [self isKindOfClass:NSClassFromString(@"_SFAutoFillInputView")]) {
                [(UIView *)self setBackgroundColor:ytfIsDarkMode() ? [UIColor blackColor] : [UIColor clearColor]];
            }
        });
    (void)orig_inputViewLayout;

    // Keyboard visual-effect view.
    static IMP orig_kbEffectsLayout;
    orig_kbEffectsLayout = ytfHookInstance(NSClassFromString(@"UIKBVisualEffectView"),
        @selector(layoutSubviews),
        ^void(id self) {
            ((void(*)(id, SEL))orig_kbEffectsLayout)(self, @selector(layoutSubviews));
            if (ytfIsDarkMode()) {
                [self setValue:nil forKey:@"backgroundEffects"];
                [(UIView *)self setBackgroundColor:[UIColor blackColor]];
            }
        });
    (void)orig_kbEffectsLayout;
}

void YTFreedomAppearanceInit(void) {
    fixOLEDTheme();
    fixOLEDSurfaces();
    fixOLEDKeyboard();
}
