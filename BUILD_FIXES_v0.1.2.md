# Build fixes in v0.1.2

## Root cause of the v0.1.1 failure

The Windows embeddable Python distribution contains `python312._pth`.
When this file exists, Python runs in isolated path mode and ignores `PYTHONPATH`.
The v0.1.1 build script tried to expose `app/src` by setting `PYTHONPATH`, so the
staged runtime could import third-party packages but not `xiaozhi_agent`.

## Fix

`stage_runtime.ps1` now writes both of these paths directly into `python312._pth`:

- `Lib\site-packages`
- `..\app\src`

and enables `import site`.

The workflow now verifies the exact embedded search path before trying the application import.
The installer smoke test repeats the same verification after a real silent install.
No build or smoke-test step relies on `PYTHONPATH` anymore.

## Previous Windows SQLite cleanup fix retained

The v0.1.1 `TaskCenter.close()` / self-check cleanup fix is retained, so the temporary
`tasks.db` is explicitly closed before its temporary directory is removed.
