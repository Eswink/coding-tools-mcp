//! Global local-only approval inbox; notifications never make authorization decisions.
use serde_json::{json,Value};
use tauri::{AppHandle,Emitter,Manager,State};
use tauri_plugin_notification::NotificationExt;
use crate::{app_state::AppState,error::{AppError,AppResult}};

fn inbox(state:&AppState)->AppResult<Value> {
    // Drop the configuration lock before touching the authorizer or executor registry.
    let profiles=state.with_workspaces(|s|Ok(s.list().iter().map(|p|(p.id.clone(),p.name.clone(),p.auth.oauth_enabled())).collect::<Vec<_>>()))?;
    let service=crate::auth::chat::service();let mut pending=Vec::new();let mut revision=0;
    for (id,name,oauth) in profiles {
        let snapshot=service.snapshot(&id);revision=revision.max(snapshot["revision"].as_u64().unwrap_or(0));
        if !oauth {continue;}
        for grant in snapshot["records"].as_array().into_iter().flatten().filter(|g|g["status"]=="pending") {
            if pending.len()>=256{return Err(AppError::Message("待审批列表达到容量上限，请逐个工作区处理".into()));}
            pending.push(json!({"workspaceId":id,"workspaceName":name,"grant":grant,"exclusive":snapshot["exclusive"]}));
        }
    }
    pending.sort_by_key(|p|(p["grant"]["created_at"].as_u64().unwrap_or(0),p["grant"]["id"].as_str().unwrap_or("").to_owned()));
    Ok(json!({"revision":revision,"now":crate::auth::chat::unix_now(),"pending":pending}))
}
#[tauri::command]
pub async fn chat_authorization_inbox(app:AppHandle)->AppResult<Value> {
    tauri::async_runtime::spawn_blocking(move||inbox(&app.state::<AppState>())).await
        .map_err(|_|AppError::Message("本机授权列表读取失败".into()))?
}
#[tauri::command]
pub async fn refresh_session_control(state:State<'_,AppState>,id:String,action:String)->AppResult<Value> {
    state.with_workspaces(|s|s.get(&id).map(|_|()).ok_or_else(||AppError::Message("工作区不存在".into())))?;
    tauri::async_runtime::spawn_blocking(move||{
        let root=crate::auth::oauth_refresh::storage_root(&id).map_err(AppError::Message)?.join("refresh");
        let store=crate::auth::oauth_refresh::RefreshStore::shared(root);
        match action.as_str(){"status"=>(),"revoke_all"=>store.revoke_all().map_err(|_|AppError::Message("刷新会话撤销失败；未报告成功".into()))?,
            _=>return Err(AppError::Message("未知刷新会话操作".into()))}
        store.snapshot().map_err(|_|AppError::Message("刷新会话存储不可用；原文件已保留".into()))
    }).await.map_err(|_|AppError::Message("刷新会话管理失败".into()))?
}
/// Menu fallback is reliable even where desktop notification-click callbacks are unavailable.
pub(crate) fn open_inbox(app:&AppHandle) {
    let _=super::window_chrome::show_main_window(app.clone());
    let _=app.emit("chat-authorization-open",json!({}));
}
fn update_tray(app:&AppHandle,count:usize) {
    let handle=app.clone();
    let _=app.run_on_main_thread(move||{
        if let Some(tray)=handle.tray_by_id("main-tray") {
            let text=if count==0{"Coding Tools MCP".to_owned()}else{format!("Coding Tools MCP — {count} 个聊天待审批")};
            let _=tray.set_tooltip(Some(text));
            if let Some(icon)=handle.default_window_icon() {
                let mut rgba=icon.rgba().to_vec();let (w,h)=(icon.width() as usize,icon.height() as usize);
                if count>0&&w>0&&h>0 {
                    let r=(w.min(h)/6).max(1);let (cx,cy)=(w.saturating_sub(r+1),r.min(h.saturating_sub(1)));
                    for y in 0..h {for x in 0..w {
                        let (dx,dy)=(x as isize-cx as isize,y as isize-cy as isize);
                        if dx*dx+dy*dy<=(r*r) as isize {let i=4*(y*w+x);rgba[i..i+4].copy_from_slice(&[220,55,65,255]);}
                    }}
                }
                let _=tray.set_icon(Some(tauri::image::Image::new_owned(rgba,w as u32,h as u32)));
            }
        }
    });
}
pub(crate) fn start(app:AppHandle) {
    let mut receiver=crate::auth::chat::service().subscribe();
    tauri::async_runtime::spawn(async move {
        let mut timer=tokio::time::interval(std::time::Duration::from_secs(5));
        let mut last=Value::Null;
        loop {
            let event=tokio::select! {
                event=receiver.recv()=>match event {Ok(e)=>Some(e),Err(tokio::sync::broadcast::error::RecvError::Lagged(_))=>None,Err(_)=>break},
                _=timer.tick()=>None,
            };
            let handle=app.clone();
            let snapshot=match tauri::async_runtime::spawn_blocking(move||inbox(&handle.state::<AppState>())).await {
                Ok(Ok(s))=>s,_=>{let _=app.emit("chat-authorization-unavailable",json!({}));continue;}
            };
            let pending=snapshot["pending"].as_array().expect("local pending array");
            let signature=json!({"revision":snapshot["revision"],"pending":pending.iter().map(|p|&p["grant"]["id"]).collect::<Vec<_>>()});
            if last!=signature {last=signature;update_tray(&app,pending.len());let _=app.emit("chat-authorization-changed",json!({"revision":snapshot["revision"]}));}
            if let Some(event)=event.filter(|e|e.kind=="pending") {
                let still_pending=pending.iter().any(|p|p["workspaceId"]==event.profile&&p["grant"]["id"].as_str()==event.request_id.as_deref());
                let foreground=app.webview_windows().values().any(|w|w.is_visible().unwrap_or(false)&&w.is_focused().unwrap_or(false));
                if still_pending&&!foreground {
                    let handle=app.clone();
                    // No credentials, session identifier, file path, or approval action in a lock-screen notification.
                    let _=tauri::async_runtime::spawn_blocking(move||handle.notification().builder()
                        .title("ChatGPT 聊天待审批").body("有新的工作区访问请求。请打开托盘的“待审批聊天”，核对会话指纹和权限。")
                        .show()).await;
                }
            }
        }
    });
}
