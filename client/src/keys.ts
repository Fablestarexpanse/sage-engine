import type { KeyboardEvent } from "react";

/// Enter in a text field submits its form, and returns true when it did.
///
/// Browsers do this themselves on the keypress that follows, but not every input method sends
/// one (some automation and assistive tools send only keydown). Handling keydown here, and
/// cancelling the default, submits exactly once either way. Enter that ends an IME composition
/// is left alone.
export function submitsOnEnter(event: KeyboardEvent<HTMLElement>): boolean {
  const target = event.target;
  if (
    event.key !== "Enter" ||
    event.nativeEvent.isComposing ||
    event.shiftKey ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    !(target instanceof HTMLInputElement) ||
    target.type === "submit" ||
    !target.form
  ) {
    return false;
  }
  event.preventDefault();
  target.form.requestSubmit();
  return true;
}
