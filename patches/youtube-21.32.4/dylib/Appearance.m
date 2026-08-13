// Appearance.m — OLED theme (G13), ported from YouMod's Apperence.x
// (uYouEnhanced OLEDTheme + dayanch96 OledKeyboard lineage).
//
// OLED theme: YTColor's blackN palette and YTCommonColorPalette surfaces
// return pure black for the dark page style (1).
// OLED keyboard: UIKit keyboard classes are repainted black in dark mode.
// UIKit classes are hooked via class_getInstanceMethod at runtime — no
// classlist needed, and missing methods no-op gracefully.

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
    NSArray *paletteSelectors = @[
        @"baseBackground", @"brandBackgroundSolid", @"brandBackgroundPrimary",
        @"brandBackgroundSecondary", @"raisedBackground", @"staticBrandBlack",
        @"generalBackgroundA",
    ];
    Class palette = NSClassFromString(@"YTCommonColorPalette");
    for (NSString *selName in paletteSelectors) {
        SEL sel = NSSelectorFromString(selName);
        Method m = class_getInstanceMethod(palette, sel);
        if (!m) continue;
        IMP orig = method_getImplementation(m);
        class_replaceMethod(palette, sel,
            imp_implementationWithBlock(^id(id self) {
                NSInteger pageStyle = [self respondsToSelector:@selector(pageStyle)]
                    ? (NSInteger)[self valueForKey:@"pageStyle"] : 0;
                if (pageStyle == 1)
                    return [selName isEqualToString:@"brandBackgroundSecondary"]
                        ? [UIColor colorWithWhite:0 alpha:0.9] : (id)[UIColor blackColor];
                return ((id(*)(id, SEL))orig)(self, sel);
            }), method_getTypeEncoding(m));
    }
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
    fixOLEDKeyboard();
}
