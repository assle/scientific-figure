---
status: accepted
---

# Keep connection testing explicit and delivery scope-aware

The Configuration app performs no Provider request while opening, editing, or
saving a draft. A user-initiated Connection test runs one minimum-capability
request in a background worker using the in-memory Provider/Model draft and an
optional temporary credential. Vision routes are preferred; a generation-only
test requires an explicit cost confirmation. The test uses a deterministic
one-pixel image and removes its temporary directory on every completion path.

The global installer includes the GUI extra and creates a marked
`scientific-figure` launcher only in the global scope. Project installs do not
create a global launcher. An existing unmarked same-name file blocks
installation rather than being overwritten. Uninstall preserves user config
and credentials by default; explicit config removal first deletes only the
`credential_id` entries listed in that config and retains the config if secure
cleanup fails.

## Rejected alternatives

- Automatic startup probes — rejected because opening a configuration window
  must never incur Provider cost or perform network I/O.
- Reusing a saved ProviderRouter for the test — rejected because it could read
  stale YAML or persist a temporary credential; the test receives explicit
  draft data instead.
- Overwriting any existing `scientific-figure` executable — rejected because a
  user's unrelated command must not be destroyed.
- Deleting all Keyring entries on uninstall — rejected because the tool can
  only safely remove credentials explicitly referenced by its own config.
