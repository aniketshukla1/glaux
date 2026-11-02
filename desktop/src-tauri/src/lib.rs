use std::net::TcpStream;
use std::process::Command;
use std::time::Duration;

/// The locally-served dashboard the window connects to.
const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 8000;

/// True if something is already listening on the backend port.
fn backend_listening() -> bool {
    TcpStream::connect_timeout(
        &format!("{BACKEND_HOST}:{BACKEND_PORT}").parse().unwrap(),
        Duration::from_millis(300),
    )
    .is_ok()
}

/// Best-effort: start the backend daemon if it isn't already running. Uses a
/// login shell so the user's PATH (and the venv that holds `glaux`) is in
/// scope. Any failure is non-fatal — the loading shell shows a friendly hint
/// and keeps polling, so the window still opens.
fn ensure_backend() {
    if backend_listening() {
        return;
    }
    let _ = Command::new("sh").arg("-lc").arg("glaux up").spawn();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            // Kick the backend off in the background so the window can paint the
            // loading shell immediately; the shell redirects once it's healthy.
            std::thread::spawn(ensure_backend);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
