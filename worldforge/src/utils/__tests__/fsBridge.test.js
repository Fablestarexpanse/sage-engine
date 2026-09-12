import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock the Tauri IPC boundary so the bridge's invoke contracts are testable
// without a running Tauri shell.
const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...args) => invoke(...args) }));

import * as fs from "../fsBridge.js";

beforeEach(() => invoke.mockReset());

describe("fsBridge invoke contracts", () => {
  it("readYaml parses the file content returned by read_file", async () => {
    invoke.mockResolvedValueOnce("id: z1:a\nname: A\n");
    const doc = await fs.readYaml("/w/zones/z1/rooms/a.yaml");
    expect(invoke).toHaveBeenCalledWith("read_file", { path: "/w/zones/z1/rooms/a.yaml" });
    expect(doc).toEqual({ id: "z1:a", name: "A" });
  });

  it("writeYaml serializes and sends content to write_file", async () => {
    invoke.mockResolvedValueOnce(undefined);
    await fs.writeYaml("/w/x.yaml", { id: "z1:a", exits: {} });
    const [cmd, args] = invoke.mock.calls[0];
    expect(cmd).toBe("write_file");
    expect(args.path).toBe("/w/x.yaml");
    expect(args.content).toContain("id:");
    // round-trip: what we wrote parses back to the same doc
    const yaml = await import("js-yaml");
    expect(yaml.load(args.content)).toEqual({ id: "z1:a", exits: {} });
  });

  it("propagates Rust-side errors to the caller (throw-and-caller-catches contract)", async () => {
    invoke.mockRejectedValueOnce("write failed: disk full");
    await expect(fs.writeText("/w/x.txt", "hi")).rejects.toBe("write failed: disk full");
  });

  it("pathExists and deleteFile pass the path through untouched", async () => {
    invoke.mockResolvedValueOnce(true);
    await fs.pathExists("/w/zone.yaml");
    expect(invoke).toHaveBeenCalledWith("path_exists", { path: "/w/zone.yaml" });
    invoke.mockResolvedValueOnce(undefined);
    await fs.deleteFile("/w/zone.yaml");
    expect(invoke).toHaveBeenCalledWith("delete_file", { path: "/w/zone.yaml" });
  });
});
