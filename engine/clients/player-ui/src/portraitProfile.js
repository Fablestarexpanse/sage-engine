/**
 * Expected player portrait output from ComfyUI (or uploads): nearly square RGBA PNG
 * with background removed so the figure composites on the UI.
 * @see config/comfyui.toml — match your workflow latent / save size to this profile.
 */
export const PORTRAIT_SIZE = { width: 1023, height: 1024 };

/** CSS aspect-ratio value (width / height) — ~1:1 */
export const PORTRAIT_ASPECT_RATIO_CSS = `${PORTRAIT_SIZE.width} / ${PORTRAIT_SIZE.height}`;
