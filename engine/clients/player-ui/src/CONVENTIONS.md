# player-ui source conventions

Two deliberate departures from the sibling apps (admin-ui, worldforge), kept
because churning them buys no behavior:

- **Named exports.** player-ui components use `export function Foo()` /
  `export const Foo` rather than `export default`. admin-ui and worldforge
  default-export. Match the file you are editing; do not convert either way.

- **`mud/` split files are numbered by extraction order, not by domain.**
  `FablestarClient.jsx` was split into `00-ctx` … `07-proficiencies-panel`
  when it outgrew one file; the numeric prefixes preserve the original
  reading order of the monolith (which is why `05-minimap` sits between the
  two panels files). The prefixes are not load-bearing — imports use full
  filenames — but a rename is deferred until the next time these files are
  restructured anyway.
