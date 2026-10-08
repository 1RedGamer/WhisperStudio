#import <Cocoa/Cocoa.h>

static NSTouchBarItemIdentifier const kTBItemStop     = @"com.whisperstudio.touchbar.stop";
static NSTouchBarItemIdentifier const kTBItemPause    = @"com.whisperstudio.touchbar.pause";
static NSTouchBarItemIdentifier const kTBItemStart    = @"com.whisperstudio.touchbar.start";
static NSTouchBarItemIdentifier const kTBItemProgress = @"com.whisperstudio.touchbar.progress";
static NSTouchBarItemIdentifier const kTBItemLabel    = @"com.whisperstudio.touchbar.label";

typedef void (*TouchBarActionCallback)(int action_id);
// action_id: 1=Start, 2=Pause/Resume, 3=Cancel

// ==============================================================================
// Custom Touch Bar Progress Bar (Matching UI Purple #818cf8 & Track #242428)
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
    NSRect bounds = self.bounds;
    CGFloat barH = 12.0;
    CGFloat barY = (bounds.size.height - barH) / 2.0;
    NSRect barRect = NSMakeRect(bounds.origin.x, barY, bounds.size.width, barH);
    CGFloat radius = 6.0;

    // Track background: #242428
    NSBezierPath *trackPath = [NSBezierPath bezierPathWithRoundedRect:barRect xRadius:radius yRadius:radius];
    [[NSColor colorWithRed:(0x24/255.0) green:(0x24/255.0) blue:(0x28/255.0) alpha:1.0] setFill];
    [trackPath fill];

    // Progress chunk: #818cf8 (smooth purple matching onscreen bar)
    if (_doubleValue > 0.0) {
        double clamped = fmin(100.0, fmax(0.0, _doubleValue));
        NSRect fillRect = barRect;
        fillRect.size.width = (barRect.size.width * clamped) / 100.0;
        if (fillRect.size.width > 0) {
            NSBezierPath *fillPath = [NSBezierPath bezierPathWithRoundedRect:fillRect xRadius:radius yRadius:radius];
            [[NSColor colorWithRed:(0x81/255.0) green:(0x8c/255.0) blue:(0xf8/255.0) alpha:1.0] setFill];
            [fillPath fill];
        }
    }
}

@end

// ==============================================================================
// Whisper Studio Touch Bar Controller
// ==============================================================================
@interface WhisperTouchBarController : NSObject <NSTouchBarDelegate>
@property (strong) NSTouchBar *touchBar;
@property (strong) NSButton *btnStop;
@property (strong) NSButton *btnPause;
@property (strong) NSButton *btnStart;
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
        _btnStop = [NSButton buttonWithTitle:[self titleStop] target:self action:@selector(handleStop:)];
        _btnStop.enabled = NO;
        _btnStop.bezelColor = [NSColor colorWithRed:0.25 green:0.25 blue:0.28 alpha:1.0];
        item.view = _btnStop;
        return item;
    } else if ([identifier isEqualToString:kTBItemPause]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _btnPause = [NSButton buttonWithTitle:[self titlePause] target:self action:@selector(handlePause:)];
        _btnPause.enabled = NO;
        _btnPause.bezelColor = [NSColor colorWithRed:0.25 green:0.25 blue:0.28 alpha:1.0];
        item.view = _btnPause;
        return item;
    } else if ([identifier isEqualToString:kTBItemStart]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _btnStart = [NSButton buttonWithTitle:[self titleStart] target:self action:@selector(handleStart:)];
        _btnStart.enabled = NO;
        _btnStart.bezelColor = [NSColor colorWithRed:0.25 green:0.25 blue:0.28 alpha:1.0];
        item.view = _btnStart;
        return item;
    } else if ([identifier isEqualToString:kTBItemProgress]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _progressBar = [[WhisperProgressBarView alloc] initWithFrame:NSMakeRect(0, 0, 130, 24)];
        _progressBar.doubleValue = 0.0;
        item.view = _progressBar;
        return item;
    } else if ([identifier isEqualToString:kTBItemLabel]) {
        NSCustomTouchBarItem *item = [[NSCustomTouchBarItem alloc] initWithIdentifier:identifier];
        _lblStatus = [NSTextField labelWithString:[self titleReady]];
        _lblStatus.font = [NSFont systemFontOfSize:11 weight:NSFontWeightMedium];
        _lblStatus.textColor = [NSColor secondaryLabelColor];
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
        // START button: enabled and green when idle with files loaded, otherwise dark gray
        if (self.btnStart) {
            BOOL shouldEnable = (!isRunning && canStart);
            self.btnStart.enabled = shouldEnable;
            self.btnStart.title = [self titleStart];
            if (shouldEnable) {
                self.btnStart.bezelColor = [NSColor colorWithRed:0.06 green:0.73 blue:0.51 alpha:1.0]; // #10b981 emerald
            } else {
                self.btnStart.bezelColor = [NSColor colorWithRed:0.25 green:0.25 blue:0.28 alpha:1.0]; // dark gray
            }
        }

        // PAUSE / RESUME button: active only during transcription
        if (self.btnPause) {
            self.btnPause.enabled = isRunning;
            if (isRunning) {
                if (isPaused) {
                    self.btnPause.title = [self titleResume];
                    self.btnPause.bezelColor = [NSColor colorWithRed:0.06 green:0.73 blue:0.51 alpha:1.0]; // #10b981 emerald
                } else {
                    self.btnPause.title = [self titlePause];
                    self.btnPause.bezelColor = [NSColor systemOrangeColor]; // orange
                }
            } else {
                self.btnPause.title = [self titlePause];
                self.btnPause.bezelColor = [NSColor colorWithRed:0.25 green:0.25 blue:0.28 alpha:1.0];
            }
        }

        // CANCEL button: active and red #ef4444 only during transcription
        if (self.btnStop) {
            self.btnStop.enabled = isRunning;
            self.btnStop.title = [self titleStop];
            if (isRunning) {
                self.btnStop.bezelColor = [NSColor colorWithRed:0.94 green:0.27 blue:0.27 alpha:1.0]; // #ef4444 red
            } else {
                self.btnStop.bezelColor = [NSColor colorWithRed:0.25 green:0.25 blue:0.28 alpha:1.0];
            }
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
