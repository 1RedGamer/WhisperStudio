#import <Cocoa/Cocoa.h>

static NSTouchBarItemIdentifier const kTBItemStop     = @"com.whisperstudio.touchbar.stop";
static NSTouchBarItemIdentifier const kTBItemPause    = @"com.whisperstudio.touchbar.pause";
static NSTouchBarItemIdentifier const kTBItemStart    = @"com.whisperstudio.touchbar.start";
static NSTouchBarItemIdentifier const kTBItemProgress = @"com.whisperstudio.touchbar.progress";
static NSTouchBarItemIdentifier const kTBItemLabel    = @"com.whisperstudio.touchbar.label";

typedef void (*TouchBarActionCallback)(int action_id);
// action_id: 1=Start, 2=Pause/Resume, 3=Cancel

typedef NS_ENUM(NSInteger, WhisperTBButtonVariant) {
    WhisperTBButtonVariantCancel = 0,
    WhisperTBButtonVariantPause  = 1,
    WhisperTBButtonVariantStart  = 2
};

// ==============================================================================
// Golden Gate Studio Liquid Glass Touch Bar Capsule Button (/apple HIG)
// ==============================================================================
@interface WhisperLiquidTouchBarButton : NSButton
@property (nonatomic, assign) WhisperTBButtonVariant variant;
@property (nonatomic, assign) BOOL isPausedState;
- (instancetype)initWithTitle:(NSString *)title
                      variant:(WhisperTBButtonVariant)variant
                       target:(id)target
                       action:(SEL)action;
@end

@implementation WhisperLiquidTouchBarButton

- (instancetype)initWithTitle:(NSString *)title
                      variant:(WhisperTBButtonVariant)variant
                       target:(id)target
                       action:(SEL)action {
    self = [super initWithFrame:NSMakeRect(0, 0, 108, 30)];
    if (self) {
        _variant = variant;
        _isPausedState = NO;
        self.title = title;
        self.target = target;
        self.action = action;
        self.bordered = NO;
        self.bezelStyle = NSBezelStyleRegularSquare;
        self.wantsLayer = YES;
        [self. widthAnchor constraintEqualToConstant:108.0].active = YES;
        [self.heightAnchor constraintEqualToConstant:30.0].active = YES;
    }
    return self;
}

- (BOOL)isFlipped {
    return YES;
}

- (void)setTitle:(NSString *)title {
    [super setTitle:title];
    [self setNeedsDisplay:YES];
}

- (void)setEnabled:(BOOL)enabled {
    [super setEnabled:enabled];
    [self setNeedsDisplay:YES];
}

- (void)setIsPausedState:(BOOL)isPausedState {
    _isPausedState = isPausedState;
    [self setNeedsDisplay:YES];
}

- (void)drawRect:(NSRect)dirtyRect {
    NSGraphicsContext *ctx = [NSGraphicsContext currentContext];
    [ctx saveGraphicsState];

    NSRect b = self.bounds;
    BOOL pressed = self.isEnabled && self.cell.isHighlighted;

    // Instant tactile compression on touch-down (/apple §1: Respond on pointer-down)
    if (pressed) {
        NSAffineTransform *tx = [NSAffineTransform transform];
        [tx translateXBy:NSMidX(b) yBy:NSMidY(b)];
        [tx scaleXBy:0.96 yBy:0.96];
        [tx translateXBy:-NSMidX(b) yBy:-NSMidY(b)];
        [tx concat];
    }

    NSRect pillRect = NSInsetRect(b, 1.0, 1.0);
    CGFloat radius = pillRect.size.height / 2.0;
    NSBezierPath *pillPath = [NSBezierPath bezierPathWithRoundedRect:pillRect xRadius:radius yRadius:radius];

    NSColor *topColor = nil;
    NSColor *botColor = nil;
    NSColor *rimTopColor = nil;
    NSColor *rimBotColor = nil;
    NSColor *textColor = nil;

    WhisperTBButtonVariant effVariant = _variant;
    if (effVariant == WhisperTBButtonVariantPause && _isPausedState) {
        effVariant = WhisperTBButtonVariantStart;
    }

    if (!self.isEnabled) {
        // Recessed Dark Frosted Glass
        topColor = [NSColor colorWithRed:(38.0/255.0) green:(38.0/255.0) blue:(46.0/255.0) alpha:0.78];
        botColor = [NSColor colorWithRed:(24.0/255.0) green:(24.0/255.0) blue:(31.0/255.0) alpha:0.78];
        rimTopColor = [NSColor colorWithWhite:1.0 alpha:0.14];
        rimBotColor = [NSColor colorWithWhite:1.0 alpha:0.06];
        textColor = [NSColor colorWithRed:(235.0/255.0) green:(235.0/255.0) blue:(245.0/255.0) alpha:0.36];
    } else if (effVariant == WhisperTBButtonVariantStart) {
        // Emerald Liquid Glass (#34d399 -> #059669)
        topColor = pressed
            ? [NSColor colorWithRed:(74.0/255.0) green:(225.0/255.0) blue:(170.0/255.0) alpha:0.96]
            : [NSColor colorWithRed:(52.0/255.0) green:(211.0/255.0) blue:(153.0/255.0) alpha:0.92];
        botColor = [NSColor colorWithRed:(5.0/255.0) green:(150.0/255.0) blue:(105.0/255.0) alpha:0.90];
        rimTopColor = [NSColor colorWithWhite:1.0 alpha:0.52];
        rimBotColor = [NSColor colorWithWhite:1.0 alpha:0.16];
        textColor = [NSColor whiteColor];
    } else if (effVariant == WhisperTBButtonVariantPause) {
        // Warm Amber Liquid Glass (#fbbf24 -> #b45309)
        topColor = pressed
            ? [NSColor colorWithRed:(253.0/255.0) green:(206.0/255.0) blue:(68.0/255.0) alpha:0.96]
            : [NSColor colorWithRed:(245.0/255.0) green:(158.0/255.0) blue:(11.0/255.0) alpha:0.92];
        botColor = [NSColor colorWithRed:(180.0/255.0) green:(83.0/255.0) blue:(9.0/255.0) alpha:0.90];
        rimTopColor = [NSColor colorWithWhite:1.0 alpha:0.48];
        rimBotColor = [NSColor colorWithWhite:1.0 alpha:0.15];
        textColor = [NSColor whiteColor];
    } else {
        // Coral Red Liquid Glass (#f87171 -> #dc2626)
        topColor = pressed
            ? [NSColor colorWithRed:(252.0/255.0) green:(140.0/255.0) blue:(140.0/255.0) alpha:0.96]
            : [NSColor colorWithRed:(248.0/255.0) green:(113.0/255.0) blue:(113.0/255.0) alpha:0.92];
        botColor = [NSColor colorWithRed:(220.0/255.0) green:(38.0/255.0) blue:(38.0/255.0) alpha:0.90];
        rimTopColor = [NSColor colorWithWhite:1.0 alpha:0.48];
        rimBotColor = [NSColor colorWithWhite:1.0 alpha:0.15];
        textColor = [NSColor whiteColor];
    }

    // 1. Vertical Liquid Glass Fill (isFlipped=YES -> -90.0 draws topColor at top, botColor at bottom)
    NSGradient *fillGrad = [[NSGradient alloc] initWithStartingColor:topColor endingColor:botColor];
    [fillGrad drawInBezierPath:pillPath angle:90.0];

    // 2. Contour-Following Specular Rim (top bright -> bottom subtle)
    [ctx saveGraphicsState];
    NSRect outerRimRect = pillRect;
    NSRect innerRimRect = NSInsetRect(pillRect, 1.15, 1.15);
    NSBezierPath *rimRing = [NSBezierPath bezierPathWithRoundedRect:outerRimRect xRadius:radius yRadius:radius];
    NSBezierPath *innerCut = [NSBezierPath bezierPathWithRoundedRect:innerRimRect xRadius:fmax(1.0, radius - 1.15) yRadius:fmax(1.0, radius - 1.15)];
    [rimRing appendBezierPath:[innerCut bezierPathByReversingPath]];
    [rimRing addClip];
    NSGradient *rimGrad = [[NSGradient alloc] initWithStartingColor:rimTopColor endingColor:rimBotColor];
    [rimGrad drawInRect:outerRimRect angle:90.0];
    [ctx restoreGraphicsState];

    // 3. Crisp Centered Label
    NSFont *font = [NSFont systemFontOfSize:12.0 weight:self.isEnabled ? NSFontWeightBold : NSFontWeightSemibold];
    NSMutableParagraphStyle *pStyle = [[NSMutableParagraphStyle alloc] init];
    pStyle.alignment = NSTextAlignmentCenter;
    NSDictionary *attrs = @{
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: textColor,
        NSParagraphStyleAttributeName: pStyle
    };
    NSSize txtSize = [self.title sizeWithAttributes:attrs];
    NSRect txtRect = NSMakeRect(
        pillRect.origin.x,
        pillRect.origin.y + (pillRect.size.height - txtSize.height) / 2.0 - 0.5,
        pillRect.size.width,
        txtSize.height
    );
    [self.title drawInRect:txtRect withAttributes:attrs];

    [ctx restoreGraphicsState];
}

@end

// ==============================================================================
// Custom Touch Bar Liquid Glass Progress Bar (Matching Onscreen WhisperProgressBar)
// ==============================================================================
@interface WhisperProgressBarView : NSView
@property (nonatomic, assign) double doubleValue;
- (void)setDoubleValue:(double)val;
@end

@implementation WhisperProgressBarView

- (instancetype)initWithFrame:(NSRect)frameRect {
    self = [super initWithFrame:frameRect];
    if (self) {
        _doubleValue = 0.0;
        self.wantsLayer = YES;
    }
    return self;
}

- (void)setDoubleValue:(double)val {
    _doubleValue = val;
    [self setNeedsDisplay:YES];
}

- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    NSGraphicsContext *ctx = [NSGraphicsContext currentContext];
    [ctx saveGraphicsState];

    NSRect bounds = self.bounds;
    CGFloat barH = 12.0;
    CGFloat barY = (bounds.size.height - barH) / 2.0;
    NSRect barRect = NSMakeRect(bounds.origin.x + 1.0, barY, bounds.size.width - 2.0, barH);
    CGFloat radius = barH / 2.0;

    // 1. Recessed Dark Glass Track (#0e0e13)
    NSBezierPath *trackPath = [NSBezierPath bezierPathWithRoundedRect:barRect xRadius:radius yRadius:radius];
    [[NSColor colorWithRed:(14.0/255.0) green:(14.0/255.0) blue:(19.0/255.0) alpha:0.95] setFill];
    [trackPath fill];

    // 2. Clipped Indigo-Violet Liquid Glass Fill (#6366f1 -> #818cf8 -> #a5b4fc)
    if (_doubleValue > 0.0) {
        double clamped = fmin(100.0, fmax(0.0, _doubleValue));
        CGFloat fillW = (barRect.size.width * clamped) / 100.0;
        if (fillW > 1.0) {
            [ctx saveGraphicsState];
            [trackPath addClip];

            NSRect fillRect = NSMakeRect(barRect.origin.x, barRect.origin.y, fillW, barRect.size.height);
            NSBezierPath *fillPath = [NSBezierPath bezierPathWithRoundedRect:fillRect xRadius:radius yRadius:radius];
            [fillPath addClip];

            NSColor *c1 = [NSColor colorWithRed:(99.0/255.0)  green:(102.0/255.0) blue:(241.0/255.0) alpha:1.0];
            NSColor *c2 = [NSColor colorWithRed:(129.0/255.0) green:(140.0/255.0) blue:(248.0/255.0) alpha:1.0];
            NSColor *c3 = [NSColor colorWithRed:(165.0/255.0) green:(180.0/255.0) blue:(252.0/255.0) alpha:1.0];
            NSGradient *progGrad = [[NSGradient alloc] initWithColors:@[c1, c2, c3]];
            [progGrad drawInBezierPath:fillPath angle:0.0];

            // Subtle top specular sheen clipped cleanly to fillPath
            NSRect sheenRect = NSMakeRect(fillRect.origin.x, fillRect.origin.y + barH * 0.5, fillRect.size.width, barH * 0.5);
            [[NSColor colorWithWhite:1.0 alpha:0.18] setFill];
            NSRectFillUsingOperation(sheenRect, NSCompositingOperationSourceOver);

            [ctx restoreGraphicsState];
        }
    }

    // 3. Subtle Glass Rim on Track
    [[NSColor colorWithWhite:1.0 alpha:0.14] setStroke];
    trackPath.lineWidth = 1.0;
    [trackPath stroke];

    [ctx restoreGraphicsState];
}

@end

// ==============================================================================
// Whisper Studio Touch Bar Controller
// ==============================================================================
@interface WhisperTouchBarController : NSObject <NSTouchBarDelegate>
@property (strong) NSTouchBar *touchBar;
@property (strong) WhisperLiquidTouchBarButton *btnStop;
@property (strong) WhisperLiquidTouchBarButton *btnPause;
@property (strong) WhisperLiquidTouchBarButton *btnStart;
@property (strong) WhisperProgressBarView *progressBar;
@property (strong) NSTextField *lblStatus;
@property (assign) TouchBarActionCallback callback;

@property (assign) int currentLang; // 0=Italian, 1=English
@property (assign) BOOL isRunning;
@property (assign) BOOL isPaused;
@property (assign) BOOL canStart;

- (void)setLanguage:(int)langCode;
- (void)updateProgress:(double)perc statusText:(NSString *)txt;
- (void)updateStateWithRunning:(BOOL)isRunning isPaused:(BOOL)isPaused canStart:(BOOL)canStart;
@end

@implementation WhisperTouchBarController

- (instancetype)initWithCallback:(TouchBarActionCallback)cb {
    self = [super init];
    if (self) {
        _callback = cb;
        _currentLang = 0; // default Italian
        _isRunning = NO;
        _isPaused = NO;
        _canStart = NO;
        [self setupTouchBar];
    }
    return self;
}

- (void)setupTouchBar {
    _touchBar = [[NSTouchBar alloc] init];
    _touchBar.delegate = self;
    // Layout matching onscreen interface: Cancel (left), Pause (center), Start (right)
    _touchBar.defaultItemIdentifiers = @[
        kTBItemStop,
        kTBItemPause,
        kTBItemStart,
        kTBItemProgress,
        kTBItemLabel
    ];
}

- (NSString *)titleStop {
    return (_currentLang == 0) ? @"■ Annulla" : @"■ Cancel";
}

- (NSString *)titlePause {
    return (_currentLang == 0) ? @"⏸️ Pausa" : @"⏸️ Pause";
}

- (NSString *)titleResume {
    return (_currentLang == 0) ? @"▶️ Riprendi" : @"▶️ Resume";
}

- (NSString *)titleStart {
    return (_currentLang == 0) ? @"🚀 Avvia" : @"🚀 Start";
}

- (NSString *)titleReady {
    return (_currentLang == 0) ? @"Pronto" : @"Ready";
}

- (nullable NSTouchBarItem *)touchBar:(NSTouchBar *)touchBar makeItemForIdentifier:(NSTouchBarItemIdentifier)identifier {
    if ([identifier isEqualToString:kTBItemStop]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _btnStop = [[WhisperLiquidTouchBarButton alloc] initWithTitle:[self titleStop]
                                                              variant:WhisperTBButtonVariantCancel
                                                               target:self
                                                               action:@selector(handleStop:)];
        _btnStop.enabled = NO;
        item.view = _btnStop;
        return item;
    } else if ([identifier isEqualToString:kTBItemPause]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _btnPause = [[WhisperLiquidTouchBarButton alloc] initWithTitle:[self titlePause]
                                                               variant:WhisperTBButtonVariantPause
                                                                target:self
                                                                action:@selector(handlePause:)];
        _btnPause.enabled = NO;
        item.view = _btnPause;
        return item;
    } else if ([identifier isEqualToString:kTBItemStart]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _btnStart = [[WhisperLiquidTouchBarButton alloc] initWithTitle:[self titleStart]
                                                               variant:WhisperTBButtonVariantStart
                                                                target:self
                                                                action:@selector(handleStart:)];
        _btnStart.enabled = NO;
        item.view = _btnStart;
        return item;
    } else if ([identifier isEqualToString:kTBItemProgress]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _progressBar = [[WhisperProgressBarView alloc] initWithFrame:NSMakeRect(0, 0, 136, 26)];
        _progressBar.doubleValue = 0.0;
        item.view = _progressBar;
        return item;
    } else if ([identifier isEqualToString:kTBItemLabel]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _lblStatus = [NSTextField labelWithString:[self titleReady]];
        _lblStatus.font = [NSFont systemFontOfSize:11.5 weight:NSFontWeightSemibold];
        _lblStatus.textColor = [NSColor colorWithRed:(235.0/255.0) green:(235.0/255.0) blue:(245.0/255.0) alpha:0.78];
        item.view = _lblStatus;
        return item;
    }
    return nil;
}

- (void)handleStart:(id)sender {
    if (_callback) _callback(1);
}

- (void)handlePause:(id)sender {
    if (_callback) _callback(2);
}

- (void)handleStop:(id)sender {
    if (_callback) _callback(3);
}

- (void)setLanguage:(int)langCode {
    _currentLang = langCode;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.btnStop) self.btnStop.title = [self titleStop];
        if (self.btnStart) self.btnStart.title = [self titleStart];
        if (self.btnPause) {
            self.btnPause.title = (self.isRunning && self.isPaused) ? [self titleResume] : [self titlePause];
        }
        if (!self.isRunning && self.lblStatus) {
            self.lblStatus.stringValue = [self titleReady];
        }
    });
}

- (void)updateProgress:(double)perc statusText:(NSString *)txt {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.progressBar) {
            self.progressBar.doubleValue = perc;
        }
        if (self.lblStatus && txt) {
            self.lblStatus.stringValue = txt;
        }
    });
}

- (void)updateStateWithRunning:(BOOL)isRunning isPaused:(BOOL)isPaused canStart:(BOOL)canStart {
    _isRunning = isRunning;
    _isPaused = isPaused;
    _canStart = canStart;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.btnStart) {
            BOOL shouldEnable = (!isRunning && canStart);
            self.btnStart.enabled = shouldEnable;
            self.btnStart.title = [self titleStart];
            [self.btnStart setNeedsDisplay:YES];
        }

        if (self.btnPause) {
            self.btnPause.enabled = isRunning;
            self.btnPause.isPausedState = (isRunning && isPaused);
            self.btnPause.title = (isRunning && isPaused) ? [self titleResume] : [self titlePause];
            [self.btnPause setNeedsDisplay:YES];
        }

        if (self.btnStop) {
            self.btnStop.enabled = isRunning;
            self.btnStop.title = [self titleStop];
            [self.btnStop setNeedsDisplay:YES];
        }
    });
}

@end

static WhisperTouchBarController *g_controller = nil;

void attach_touchbar_to_window(void *nsview_ptr, TouchBarActionCallback cb) {
    if (!g_controller) {
        g_controller = [[WhisperTouchBarController alloc] initWithCallback:cb];
    }
    dispatch_async(dispatch_get_main_queue(), ^{
        NSView *view = (__bridge NSView *)nsview_ptr;
        NSWindow *win = [view window];
        if (!win) {
            win = [NSApp keyWindow] ?: [[NSApp windows] firstObject];
        }
        if (win) {
            [win setTouchBar:g_controller.touchBar];
        }
        if ([NSApp respondsToSelector:@selector(setTouchBar:)]) {
            [NSApp setTouchBar:g_controller.touchBar];
        }
    });
}

void update_touchbar_progress(double perc, const char *status_cstr) {
    if (g_controller) {
        NSString *str = status_cstr ? [NSString stringWithUTF8String:status_cstr] : @"";
        [g_controller updateProgress:perc statusText:str];
    }
}

void update_touchbar_state(int is_running, int is_paused, int can_start) {
    if (g_controller) {
        [g_controller updateStateWithRunning:(is_running != 0) isPaused:(is_paused != 0) canStart:(can_start != 0)];
    }
}

void set_touchbar_language(int lang_code) {
    if (g_controller) {
        [g_controller setLanguage:lang_code];
    }
}
