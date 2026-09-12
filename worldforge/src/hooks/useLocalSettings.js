import { useEffect, useState } from "react";

function read(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    if (typeof fallback === "boolean") return v === "true" || v === "1";
    if (typeof fallback === "number") return Number(v) || fallback;
    return v;
  } catch {
    return fallback;
  }
}

export function useLocalSettings() {
  const [nexusUrl, setNexusUrl] = useState(() => read("worldforge_nexus_url", "http://localhost:8001"));
  const [nexusToken, setNexusToken] = useState(() => read("worldforge_nexus_token", ""));
  const [llmModel, setLlmModel] = useState(() => read("worldforge_llm_model", ""));
  const [autoSaveNavigate, setAutoSaveNavigate] = useState(() => read("worldforge_autosave_nav", true));
  const [showYamlIds, setShowYamlIds] = useState(() => read("worldforge_show_yaml_ids", false));
  const [defaultRoomType, setDefaultRoomType] = useState(() => read("worldforge_default_room_type", "chamber"));
  const [snapGridW, setSnapGridW] = useState(() => read("worldforge_snap_w", 220));
  const [snapGridH, setSnapGridH] = useState(() => read("worldforge_snap_h", 140));
  const [connectionDebugLog, setConnectionDebugLog] = useState(() => read("worldforge_connection_debug", false));
  const [showDevTools, setShowDevTools] = useState(() => read("worldforge_show_dev_tools", false));

  useEffect(() => {
    localStorage.setItem("worldforge_nexus_url", nexusUrl);
  }, [nexusUrl]);
  useEffect(() => {
    localStorage.setItem("worldforge_nexus_token", nexusToken);
  }, [nexusToken]);
  useEffect(() => {
    localStorage.setItem("worldforge_llm_model", llmModel);
  }, [llmModel]);
  useEffect(() => {
    localStorage.setItem("worldforge_autosave_nav", String(autoSaveNavigate));
  }, [autoSaveNavigate]);
  useEffect(() => {
    localStorage.setItem("worldforge_show_yaml_ids", String(showYamlIds));
  }, [showYamlIds]);
  useEffect(() => {
    localStorage.setItem("worldforge_default_room_type", defaultRoomType);
  }, [defaultRoomType]);
  useEffect(() => {
    localStorage.setItem("worldforge_snap_w", String(snapGridW));
  }, [snapGridW]);
  useEffect(() => {
    localStorage.setItem("worldforge_snap_h", String(snapGridH));
  }, [snapGridH]);
  useEffect(() => {
    localStorage.setItem("worldforge_connection_debug", String(connectionDebugLog));
  }, [connectionDebugLog]);
  useEffect(() => {
    localStorage.setItem("worldforge_show_dev_tools", String(showDevTools));
  }, [showDevTools]);

  return {
    nexusUrl,
    setNexusUrl,
    nexusToken,
    setNexusToken,
    llmModel,
    setLlmModel,
    autoSaveNavigate,
    setAutoSaveNavigate,
    showYamlIds,
    setShowYamlIds,
    defaultRoomType,
    setDefaultRoomType,
    snapGridW,
    setSnapGridW,
    snapGridH,
    setSnapGridH,
    connectionDebugLog,
    setConnectionDebugLog,
    showDevTools,
    setShowDevTools,
  };
}

export function readSnapEnabled() {
  return read("worldforge_snap_enabled", false);
}

export function writeSnapEnabled(v) {
  localStorage.setItem("worldforge_snap_enabled", String(v));
}
