import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ThemeProvider } from "../../ThemeContext.jsx";
import ExtensionBlocks from "../ExtensionBlocks.jsx";

const here = dirname(fileURLToPath(import.meta.url));
const rivermoot = JSON.parse(readFileSync(resolve(here, "../../../../../../worlds/rivermoot/content.schema.json"), "utf8"));
const render = (props) => renderToStaticMarkup(<ThemeProvider><ExtensionBlocks onChange={() => {}} {...props} /></ThemeProvider>);

describe("ExtensionBlocks", () => {
  it("renders a present block as a form and offers the absent ones", () => {
    const html = render({
      worldSchema: rivermoot,
      kind: "room",
      doc: { id: "town:market", shop: { name: "the market stalls", sells: [{ template: "bread_loaf", price: 1 }] } },
    });
    expect(html).toContain("Remove shop");
    expect(html).toContain("+ Add lodging");
    expect(html).toContain("+ Add hazards");
    expect(html).toContain("Price *");
    expect(html).toContain('value="bread_loaf"');
    expect(html).toContain("plugin: shop");
  });

  it("offers world choices for a field and explains folders without a schema", () => {
    const html = render({ worldSchema: rivermoot, kind: "item", doc: { slot: "hand" }, choices: { slot: ["hand", "body"] } });
    expect(html).toContain("<select");
    expect(html).toContain(">body</option>");
    expect(render({ worldSchema: null, kind: "room", doc: {} })).toContain("no content.schema.json");
  });
});
