import { createContext } from "react";

export const GameCmdContext = createContext({
  sendCommand: () => {},
  /** Brings the in-game Skills / proficiencies panel to the front (and shows it if hidden). */
  focusProficienciesPanel: () => {},
});
