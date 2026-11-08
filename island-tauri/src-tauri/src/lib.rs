//! Yobi island window (Tauri 2).
//!
//! Python (electron_island.py) owns every decision; this process only shows what Python sends
//! and reports clicks back. Same contract as the Electron island: a 127.0.0.1 socket, a one-time
//! token, one JSON message per line.
//!
//! The window is click-through until the cursor rests on the island for a moment (DWELL), so a
//! quick pass or a click on a browser tab underneath goes straight through.

use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, State, WebviewWindow};

const W: f64 = 580.0;
const H: f64 = 640.0; // room for the panel with music and your day; transparent and click-through
const DWELL: Duration = Duration::from_millis(250);

/// Where the island is drawn inside the window (CSS px), reported by the frontend.
#[derive(Deserialize, Clone, Copy, Debug)]
struct Rect {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}

#[derive(Default)]
struct Shared {
    writer: Mutex<Option<TcpStream>>,
    reader: Mutex<Option<TcpStream>>,
    rect: Mutex<Option<Rect>>,
    ignoring: Mutex<bool>,
    /// the window that had the keyboard before the island took it (the shortcut, writing to Yobi)
    before: Mutex<usize>,
    /// which screen the island sits on: "primary", "cursor", or a screen's number ("1", "2"…)
    display: Mutex<String>,
    /// where on that screen: "top" (centred under the top edge), or a strip on the "right" / "left" edge
    edge: Mutex<String>,
    /// the work area it was last placed on, so it only moves when that changes
    placed: Mutex<Option<(i32, i32, u32, u32)>>,
}

type Ctx = Arc<Shared>;

// ── commands the frontend calls ─────────────────────────────────────────

/// A message for Python. Anything without a string `t` is dropped.
#[tauri::command]
fn send(ctx: State<Ctx>, msg: Value) {
    if msg.get("t").and_then(Value::as_str).is_none() {
        return;
    }
    if let Some(s) = ctx.writer.lock().unwrap().as_mut() {
        let _ = writeln!(s, "{msg}");
    }
}

/// The frontend is listening: start delivering Python's messages.
#[tauri::command]
fn ready(app: AppHandle, ctx: State<Ctx>) {
    if let Some(stream) = ctx.reader.lock().unwrap().take() {
        thread::spawn(move || read_python(app, stream));
    }
}

/// true while the pointer is on the island (or a panel is open): the window takes input.
#[tauri::command]
fn interactive(window: WebviewWindow, ctx: State<Ctx>, on: bool) {
    set_ignore(&window, &ctx, !on);
}

#[tauri::command]
fn rect(ctx: State<Ctx>, r: Rect) {
    if [r.x, r.y, r.w, r.h].iter().all(|v| v.is_finite()) {
        *ctx.rect.lock().unwrap() = Some(r);
    }
}

/// on: the island takes the keyboard. off: it goes back to the app you were in.
#[tauri::command]
fn focus(window: WebviewWindow, ctx: State<Ctx>, on: bool) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, IsWindow, SetForegroundWindow};
    let me = window.hwnd().map(|h| h.0 as usize).unwrap_or(0);
    let mut before = ctx.before.lock().unwrap();
    if on {
        let fg = unsafe { GetForegroundWindow() } as usize;
        if fg != 0 && fg != me {
            *before = fg;
        }
        let _ = window.set_focus();
    } else if *before != 0 {
        let fg = unsafe { GetForegroundWindow() } as usize;
        // only if the island still has it: never pull the user away from where they clicked
        if fg == me && unsafe { IsWindow(*before as _) } != 0 {
            unsafe { SetForegroundWindow(*before as _) };
        }
        *before = 0;
    }
}

/// A file's (or an app's) icon as Explorer shows it, as a PNG data URL; "" when there's none.
#[tauri::command]
fn file_icon(path: String) -> String {
    use base64::Engine;
    icon_png(&path)
        .map(|png| format!("data:image/png;base64,{}", base64::engine::general_purpose::STANDARD.encode(png)))
        .unwrap_or_default()
}

/// Drag a shelf file out of the island into another app (Explorer, a chat, an email…).
#[tauri::command]
fn drag_out(window: WebviewWindow, path: String) {
    let file = std::path::PathBuf::from(&path);
    if !file.is_absolute() || !file.exists() {
        return;
    }
    let image = drag::Image::Raw(icon_png(&path).unwrap_or_default());
    let w = window.clone();
    // OLE drag and drop must run on the window's own thread
    let _ = window.run_on_main_thread(move || {
        let _ = drag::start_drag(&w, drag::DragItem::Files(vec![file]), image, |_, _| {}, drag::Options::default());
    });
}

fn icon_png(path: &str) -> Option<Vec<u8>> {
    use windows_sys::Win32::UI::Shell::{SHGetFileInfoW, SHFILEINFOW, SHGFI_ICON, SHGFI_LARGEICON};
    use windows_sys::Win32::UI::WindowsAndMessaging::DestroyIcon;
    if !std::path::Path::new(path).exists() {
        return None;
    }
    let wide: Vec<u16> = path.encode_utf16().chain(Some(0)).collect();
    let mut info: SHFILEINFOW = unsafe { std::mem::zeroed() };
    let ok = unsafe {
        SHGetFileInfoW(wide.as_ptr(), 0, &mut info, std::mem::size_of::<SHFILEINFOW>() as u32, SHGFI_ICON | SHGFI_LARGEICON)
    };
    if ok == 0 || info.hIcon.is_null() {
        return None;
    }
    let png = unsafe { hicon_png(info.hIcon) };
    unsafe { DestroyIcon(info.hIcon) };
    png
}

/// HICON → RGBA → PNG. Old-style icons have no alpha in the colour bitmap: the mask gives it.
unsafe fn hicon_png(icon: windows_sys::Win32::UI::WindowsAndMessaging::HICON) -> Option<Vec<u8>> {
    use std::mem::{size_of, zeroed};
    use windows_sys::Win32::Graphics::Gdi::*;
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetIconInfo, ICONINFO};
    let mut ii: ICONINFO = zeroed();
    if GetIconInfo(icon, &mut ii) == 0 {
        return None;
    }
    let cleanup = |ii: &ICONINFO| {
        if !ii.hbmColor.is_null() { DeleteObject(ii.hbmColor as _); }
        if !ii.hbmMask.is_null() { DeleteObject(ii.hbmMask as _); }
    };
    if ii.hbmColor.is_null() {
        cleanup(&ii);
        return None;
    }
    let mut bm: BITMAP = zeroed();
    GetObjectW(ii.hbmColor as _, size_of::<BITMAP>() as i32, &mut bm as *mut _ as _);
    let (w, h) = (bm.bmWidth, bm.bmHeight);
    if w <= 0 || h <= 0 || w > 256 || h > 256 {
        cleanup(&ii);
        return None;
    }
    let mut bi: BITMAPINFO = zeroed();
    bi.bmiHeader.biSize = size_of::<BITMAPINFOHEADER>() as u32;
    bi.bmiHeader.biWidth = w;
    bi.bmiHeader.biHeight = -h; // top-down
    bi.bmiHeader.biPlanes = 1;
    bi.bmiHeader.biBitCount = 32;
    bi.bmiHeader.biCompression = BI_RGB;
    let n = (w * h) as usize;
    let mut px = vec![0u8; n * 4];
    let dc = GetDC(std::ptr::null_mut());
    GetDIBits(dc, ii.hbmColor, 0, h as u32, px.as_mut_ptr() as _, &mut bi, DIB_RGB_COLORS);
    if px.chunks(4).all(|p| p[3] == 0) {
        let mut mask = vec![0u8; n * 4];
        GetDIBits(dc, ii.hbmMask, 0, h as u32, mask.as_mut_ptr() as _, &mut bi, DIB_RGB_COLORS);
        for i in 0..n {
            px[i * 4 + 3] = if mask[i * 4] == 0 { 255 } else { 0 };
        }
    }
    ReleaseDC(std::ptr::null_mut(), dc);
    cleanup(&ii);
    for p in px.chunks_mut(4) {
        p.swap(0, 2); // BGRA → RGBA
    }
    let mut out = Vec::new();
    {
        let mut enc = png::Encoder::new(&mut out, w as u32, h as u32);
        enc.set_color(png::ColorType::Rgba);
        enc.set_depth(png::BitDepth::Eight);
        let mut writer = enc.write_header().ok()?;
        writer.write_image_data(&px).ok()?;
    }
    Some(out)
}

// ── the window ──────────────────────────────────────────────────────────

fn set_ignore(window: &WebviewWindow, ctx: &Ctx, on: bool) {
    let mut ig = ctx.ignoring.lock().unwrap();
    if *ig != on {
        *ig = on;
        let _ = window.set_ignore_cursor_events(on);
    }
}

/// The screen the settings chose: the primary one, the one with the mouse, or a numbered one.
fn target_monitor(window: &WebviewWindow, pref: &str) -> Option<tauri::Monitor> {
    if pref == "cursor" {
        if let Ok(c) = window.cursor_position() {
            if let Ok(Some(m)) = window.monitor_from_point(c.x, c.y) {
                return Some(m);
            }
        }
    } else if let Ok(n) = pref.parse::<usize>() {
        if let Some(m) = window.available_monitors().ok().and_then(|v| v.into_iter().nth(n.wrapping_sub(1))) {
            return Some(m);
        }
    }
    window.primary_monitor().ok().flatten()
}

/// Top centre of the chosen screen's work area, or the middle of its right or left edge
/// (off-screen for tests: YOBI_ISLAND_OFFSCREEN).
/// Moves only when that work area changes: a new choice, the mouse on another screen,
/// a screen plugged in or out, the taskbar moved.
fn place(window: &WebviewWindow, ctx: &Shared) {
    if std::env::var("YOBI_ISLAND_OFFSCREEN").is_ok() {
        let _ = window.set_size(LogicalSize::new(W, H));
        let _ = window.set_position(PhysicalPosition::new(-4000, -4000));
        return;
    }
    let pref = ctx.display.lock().unwrap().clone();
    let Some(m) = target_monitor(window, &pref) else { return };
    let area = m.work_area();
    let key = (area.position.x, area.position.y, area.size.width, area.size.height);
    let mut placed = ctx.placed.lock().unwrap();
    if *placed == Some(key) {
        return;
    }
    *placed = Some(key);
    let width = (W * m.scale_factor()).round() as i32;
    let height = (H * m.scale_factor()).round() as i32;
    let (ax, ay, aw, ah) = (area.position.x, area.position.y, area.size.width as i32, area.size.height as i32);
    let at = match ctx.edge.lock().unwrap().as_str() {
        "right" => PhysicalPosition::new(ax + aw - width, ay + (ah - height) / 2),
        "left" => PhysicalPosition::new(ax, ay + (ah - height) / 2),
        _ => PhysicalPosition::new(ax + (aw - width) / 2, ay),
    };
    // move first, then size (in that screen's scale), then settle the position
    let _ = window.set_position(at);
    let _ = window.set_size(LogicalSize::new(W, H));
    let _ = window.set_position(at);
}

/// The settings chose a screen for the island.
#[tauri::command]
fn display(window: WebviewWindow, ctx: State<Ctx>, pref: String) {
    *ctx.display.lock().unwrap() = pref;
    *ctx.placed.lock().unwrap() = None;
    place(&window, &ctx);
}

/// The settings put the island at the top or on a side edge.
#[tauri::command]
fn edge(window: WebviewWindow, ctx: State<Ctx>, edge: String) {
    *ctx.edge.lock().unwrap() = edge;
    *ctx.placed.lock().unwrap() = None;
    place(&window, &ctx);
}

#[derive(serde::Serialize)]
struct Screen {
    id: String,
    n: usize,
    w: u32,
    h: u32,
    scale: f64,
    primary: bool,
}

/// The screens, for the settings' list (sizes in logical pixels, like Windows shows them).
#[tauri::command]
fn displays(window: WebviewWindow) -> Vec<Screen> {
    let primary = window.primary_monitor().ok().flatten().map(|m| *m.position());
    window
        .available_monitors()
        .unwrap_or_default()
        .iter()
        .enumerate()
        .map(|(i, m)| {
            let s = m.scale_factor();
            Screen {
                id: (i + 1).to_string(),
                n: i + 1,
                w: (m.size().width as f64 / s).round() as u32,
                h: (m.size().height as f64 / s).round() as u32,
                scale: s,
                primary: Some(*m.position()) == primary,
            }
        })
        .collect()
}

/// The settings window: one at a time, brought to the front if it's already open.
/// (async: building a window from a sync command can deadlock on Windows)
#[tauri::command]
async fn open_settings(app: AppHandle) {
    if let Some(w) = app.get_webview_window("settings") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
        return;
    }
    let _ = tauri::WebviewWindowBuilder::new(&app, "settings", tauri::WebviewUrl::App("index.html".into()))
        .title("إعدادات يوبي")
        .inner_size(900.0, 640.0)
        .min_inner_size(700.0, 480.0)
        .center()
        .theme(Some(tauri::Theme::Dark))
        .initialization_script("window.__YOBI_SETTINGS__ = true;")
        .build();
}

/// Click-through windows get no mouse events, so watch the cursor directly.
fn watch_cursor(app: AppHandle, ctx: Ctx) {
    thread::spawn(move || {
        let mut since: Option<Instant> = None;
        let mut tick: u32 = 0;
        loop {
            thread::sleep(Duration::from_millis(50));
            let Some(window) = app.get_webview_window("island") else { return };
            tick = tick.wrapping_add(1);
            if tick % 20 == 0 {
                place(&window, &ctx); // once a second: follow the mouse's screen, screens coming and going
            }
            let rect = *ctx.rect.lock().unwrap();
            let ignoring = *ctx.ignoring.lock().unwrap();
            let (Some(r), true) = (rect, ignoring) else {
                since = None;
                continue;
            };
            let (Ok(cursor), Ok(pos), Ok(scale)) =
                (app.cursor_position(), window.outer_position(), window.scale_factor())
            else {
                continue;
            };
            let x = (cursor.x - pos.x as f64) / scale;
            let y = (cursor.y - pos.y as f64) / scale;
            let pad = 4.0;
            let inside = x >= r.x - pad && x <= r.x + r.w + pad && y >= (if r.y > 0.0 { r.y - pad } else { -2.0 }) && y <= r.y + r.h + pad;
            if !inside {
                since = None;
                continue;
            }
            let start = *since.get_or_insert_with(Instant::now);
            if start.elapsed() >= DWELL {
                since = None;
                set_ignore(&window, &ctx, false);
            }
        }
    });
}

// ── Python ──────────────────────────────────────────────────────────────

/// Connect and say hello now (Python is waiting); messages flow once the frontend is ready.
fn connect(ctx: &Ctx) -> bool {
    let (Ok(port), Ok(token)) = (std::env::var("YOBI_ISLAND_PORT"), std::env::var("YOBI_ISLAND_TOKEN")) else {
        eprintln!("Start the island from agent.py (YOBI_ISLAND_PORT / YOBI_ISLAND_TOKEN are missing).");
        return false;
    };
    let Ok(port) = port.parse::<u16>() else { return false };
    let Ok(mut stream) = TcpStream::connect(("127.0.0.1", port)) else { return false };
    let _ = stream.set_nodelay(true);
    if writeln!(stream, "{}", json!({ "t": "hello", "token": token })).is_err() {
        return false;
    }
    let reader = stream.try_clone().ok();
    *ctx.writer.lock().unwrap() = Some(stream);
    *ctx.reader.lock().unwrap() = reader;
    true
}

fn read_python(app: AppHandle, stream: TcpStream) {
    for line in BufReader::new(stream).lines() {
        let Ok(line) = line else { break };
        let Ok(msg) = serde_json::from_str::<Value>(&line) else { continue };
        if msg.get("t").and_then(Value::as_str) == Some("quit") {
            break;
        }
        let _ = app.emit("yobi", msg); // the island, and the settings window when it's open
    }
    // Python is gone (or said quit): nothing left to show.
    app.exit(0);
}

pub fn run() {
    let ctx: Ctx = Arc::new(Shared::default());
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(ctx.clone())
        .invoke_handler(tauri::generate_handler![send, ready, interactive, rect, focus, file_icon, drag_out, display, edge, displays, open_settings])
        .setup(move |app| {
            let window = app.get_webview_window("island").expect("island window");
            *ctx.display.lock().unwrap() = "primary".into();
            *ctx.edge.lock().unwrap() = "top".into();
            place(&window, &ctx);
            window.set_always_on_top(true)?;
            set_ignore(&window, &ctx, true);
            // YOBI_ISLAND_DEV=1 runs the window alone, for working on the design
            if !connect(&ctx) && std::env::var("YOBI_ISLAND_DEV").is_err() {
                app.handle().exit(2);
                return Ok(());
            }
            watch_cursor(app.handle().clone(), ctx.clone());
            window.show()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the Yobi island");
}

#[cfg(test)]
mod tests {
    #[test]
    fn explorer_has_a_png_icon() {
        let png = super::icon_png(r"C:\Windows\explorer.exe").expect("an icon");
        assert_eq!(&png[..8], b"\x89PNG\r\n\x1a\n");
        assert!(super::icon_png(r"C:\no\such\file.txt").is_none());
    }
}
