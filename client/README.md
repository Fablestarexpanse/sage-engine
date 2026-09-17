# SAGE browser client

The player client for `sage.protocol/1`, embedded into the `sage` binary at build time. See [ADR 0022](../docs/adr/0022-browser-client.md).

```bash
pnpm --dir client install
pnpm --dir client test
pnpm --dir client build
```

Then rebuild `sage`, and `sage run <world> --listen 127.0.0.1:4700` serves the client at `http://127.0.0.1:4700/`.

To work on the client with hot reload, run `sage run` with `--listen 127.0.0.1:4700`, then `pnpm --dir client dev`. The Vite dev server proxies `/ws` to that port.
