// Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("failed to run HcpXmlWorkflowChat Windows client");
}
