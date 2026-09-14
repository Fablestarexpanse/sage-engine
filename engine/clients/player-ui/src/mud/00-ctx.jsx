import { createContext } from "react";

export const GameCmdContext = createContext({
  sendCommand: () => {},
});
