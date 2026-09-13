mod commands;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                use tauri::Manager;
                if let Some(w) = app.get_webview_window("main") {
                    w.open_devtools();
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_exe_path,
            commands::get_env_var,
            commands::read_file,
            commands::write_file,
            commands::delete_file,
            commands::list_dir,
            commands::path_exists,
            commands::create_dir,
            commands::remove_dir_all,
            commands::copy_file,
            commands::write_binary_file,
            commands::read_binary_file,
            commands::pick_folder,
            commands::pick_save_path,
            commands::pick_image_file,
            commands::pick_open_file,
            commands::export_bundle,
            commands::export_bundle_with_root,
            commands::list_zip_entries,
            commands::import_bundle,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
