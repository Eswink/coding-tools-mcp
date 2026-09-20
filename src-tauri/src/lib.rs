#![cfg_attr(target_os = "windows", allow(linker_messages))]

mod actions;
mod app_state;
mod auth;
mod bootstrap;
mod commands;
mod data;
mod error;
pub mod harness;
mod health;
#[cfg(target_os = "linux")]
mod linux_session_bus;
#[cfg(target_os = "linux")]
mod linux_secret_service;
mod mcp;
mod platform;
mod runtime;
mod secret;
mod settings;
pub mod tools;
mod tunnel;
mod update;
mod workspace;

use app_state::AppState;
use commands::{
    chat_authorization_control, chat_authorization_inbox, refresh_session_control, check_app_update, get_environment_diagnostics, get_startup_status, retry_startup, create_workspace, delete_frp_profile, delete_workspace,
    get_actions_runtime_status, get_app_settings, get_download_config, get_frp_snippet,
    get_last_workspace_id, get_proxy, get_runtime_status, get_shared_secret, get_webview_memory_sample,
    pause_mcp_execution, resume_mcp_execution,
    get_workspace_secret, hide_to_tray, install_software, list_frp_profiles, list_software,
    list_workspaces, open_url, open_workspace_directory, quit_app, read_workspace_logs, control_exec_tasks,
    recreate_ui_webview, regenerate_shared_secret, regenerate_workspace_secret,
    restart_actions_runtime, restart_runtime, restart_tunnel, run_health_checks, save_frp_profile,
    set_download_config, set_last_workspace, set_proxy, set_shared_secret, set_workspace_secret,
    show_main_window, start_actions_runtime, start_runtime, start_tunnel, stop_actions_runtime,
    stop_runtime, stop_tunnel, test_tunnel, uninstall_software, update_workspace,
};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, WindowEvent};
use std::sync::atomic::{AtomicBool, Ordering};

#[cfg(target_os = "windows")]
fn signal_existing_instance() -> bool {
    use windows::core::w;
    use windows::Win32::Foundation::{CloseHandle, HANDLE, GetLastError, ERROR_ALREADY_EXISTS};
    use windows::Win32::System::Threading::{
        CreateEventW, CreateMutexW, OpenEventW, SetEvent, EVENT_MODIFY_STATE,
    };

    let Ok(mutex) = (unsafe {
        CreateMutexW(
            None,
            false,
            w!("Local\\CodingToolsMcpDesktop-SingleInstance"),
        )
    }) else {
        eprintln!("创建应用单实例锁失败，为避免误清理其他实例的 frpc，本次启动已取消");
        return false;
    };
    if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
        let _ = unsafe { CloseHandle(mutex) };
        if let Ok(event) = unsafe {
            OpenEventW(
                EVENT_MODIFY_STATE,
                false,
                w!("Local\\CodingToolsMcpDesktop-ShowWindow"),
            )
        } {
            let _ = unsafe { SetEvent(event) };
            let _ = unsafe { CloseHandle(event) };
        }
        return false;
    }

    // Keep mutex handle for process lifetime (do not CloseHandle).
    let _ = INSTANCE_MUTEX.set(mutex.0 as usize);

    let Ok(event) = (unsafe {
        CreateEventW(
            None,
            false,
            false,
            w!("Local\\CodingToolsMcpDesktop-ShowWindow"),
        )
    }) else {
        return true;
    };
    // Pass the handle as usize so the waiter thread is Send (HANDLE is !Send).
    let event_bits = event.0 as usize;
    std::thread::spawn(move || {
        use windows::Win32::System::Threading::{WaitForSingleObject, INFINITE};
        let event = HANDLE(event_bits as *mut std::ffi::c_void);
        loop {
            let _ = unsafe { WaitForSingleObject(event, INFINITE) };
            if let Some(app) = SHOW_APP_HANDLE.get() {
                let _ = commands::window_chrome::show_main_window(app.clone());
            }
        }
    });
    true
}

#[cfg(target_os = "windows")]
static SHOW_APP_HANDLE: std::sync::OnceLock<tauri::AppHandle> = std::sync::OnceLock::new();

#[cfg(target_os = "windows")]
static INSTANCE_MUTEX: std::sync::OnceLock<usize> = std::sync::OnceLock::new();

#[cfg(target_os = "windows")]
fn acquire_single_instance() -> bool {
    signal_existing_instance()
}

#[cfg(not(target_os = "windows"))]
fn acquire_single_instance() -> bool {
    true
}

fn setup_tray(app: &tauri::App) -> tauri::Result<()> {
    let show_i = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let approvals_i = MenuItem::with_id(app, "chat-approvals", "待审批聊天", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_i, &approvals_i, &quit_i])?;

    let mut builder = TrayIconBuilder::with_id("main-tray")
        .menu(&menu)
        .tooltip("Coding Tools MCP")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => {
                let _ = commands::window_chrome::show_main_window(app.clone());
            }
            "chat-approvals" => commands::chat_notifications::open_inbox(app),
            "quit" => {
                commands::window_chrome::arm_allow_exit();
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let _ = commands::window_chrome::show_main_window(tray.app_handle().clone());
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}

static READY_SERVICES_STARTED: AtomicBool = AtomicBool::new(false);

pub(crate) fn start_ready_services(app: &tauri::AppHandle) {
    if bootstrap::safe_mode() || READY_SERVICES_STARTED.swap(true, Ordering::SeqCst) {
        return;
    }
    tunnel::ensure_frp_health_loop();
    commands::chat_notifications::start(app.clone());
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(target_os = "linux")]
    linux_session_bus::prepare_secure_storage_bus();
    bootstrap::install_panic_marker();
    bootstrap::record("process-start");
    let startup_mode = bootstrap::startup_mode();
    if startup_mode.diagnose_startup {
        let diagnostics = commands::environment_diagnostics_snapshot("not_loaded", false, false);
        if let Ok(json) = serde_json::to_string(&diagnostics) {
            use std::io::Write;
            let mut stdout = std::io::stdout().lock();
            let _ = writeln!(stdout, "startup-diagnostics={json}");
            let _ = stdout.flush();
        }
        bootstrap::record("diagnostics-complete");
        return;
    }
    if !acquire_single_instance() {
        return;
    }
    let mut builder = tauri::Builder::default().plugin(tauri_plugin_dialog::init());
    if !startup_mode.safe_mode {
        builder = builder.plugin(tauri_plugin_notification::init());
    }
    builder
        .setup(move |app| {
            bootstrap::record("tauri-setup");
            let state = AppState::new().expect("failed to create app state wrapper");
            let ready = state.is_ready();
            app.manage(state);
            bootstrap::record(if ready { "app-state-ready" } else { "app-state-locked" });

            if startup_mode.safe_mode {
                bootstrap::record("tray-skipped-safe-mode");
            } else if setup_tray(app).is_ok() {
                bootstrap::record("tray-ready");
            } else {
                // Tray availability is optional on Linux desktops. A missing
                // AppIndicator/StatusNotifier implementation must not kill the GUI.
                bootstrap::record("tray-degraded");
            }
            if startup_mode.safe_mode {
                bootstrap::record("background-skipped-safe-mode");
            } else if ready {
                start_ready_services(app.handle());
                bootstrap::record("background-ready");
            } else {
                bootstrap::record("background-deferred");
            }
            #[cfg(target_os = "windows")]
            {
                let _ = SHOW_APP_HANDLE.set(app.handle().clone());
            }
            bootstrap::record("setup-complete");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_workspaces,
            create_workspace,
            update_workspace,
            open_workspace_directory,
            open_url,
            check_app_update,
            get_startup_status,
            get_environment_diagnostics,
            retry_startup,
            delete_workspace,
            start_runtime,
            stop_runtime,
            get_runtime_status,
            pause_mcp_execution,
            resume_mcp_execution,
            start_actions_runtime,
            stop_actions_runtime,
            get_actions_runtime_status,
            restart_runtime,
            restart_actions_runtime,
            get_frp_snippet,
            start_tunnel,
            stop_tunnel,
            run_health_checks,
            get_workspace_secret,
            set_workspace_secret,
            regenerate_workspace_secret,
            get_shared_secret,
            set_shared_secret,
            regenerate_shared_secret,
            read_workspace_logs,
            control_exec_tasks,
            chat_authorization_control,
            chat_authorization_inbox,
            refresh_session_control,
            list_frp_profiles,
            save_frp_profile,
            delete_frp_profile,
            get_app_settings,
            restart_tunnel,
            test_tunnel,
            set_last_workspace,
            get_last_workspace_id,
            list_software,
            install_software,
            uninstall_software,
            get_download_config,
            set_download_config,
            get_proxy,
            set_proxy,
            get_webview_memory_sample,
            recreate_ui_webview,
            hide_to_tray,
            show_main_window,
            quit_app,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| match event {
            tauri::RunEvent::ExitRequested { api, .. } => {
                // While recreating the UI WebView we temporarily destroy the main
                // window; without prevent_exit Tauri would quit the whole process
                // and take MCP/FRP down with it (0.1.30 regression).
                if commands::ui_memory::should_prevent_exit() {
                    api.prevent_exit();
                }
            }
            tauri::RunEvent::WindowEvent { label, event, .. } => {
                if label != "main" {
                    return;
                }
                if let WindowEvent::CloseRequested { api, .. } = event {
                    if commands::window_chrome::should_intercept_close() {
                        api.prevent_close();
                        let _ = app_handle.emit("close-requested", ());
                    }
                }
            }
            _ => {}
        });
}
