# dumb-n-honest (npx)

Run the [dumb-n-honest](https://github.com/yamancan/dumb-n-honest) private local benchmark with
one command:

```bash
npx dumb-n-honest
npx dumb-n-honest doctor
npx dumb-n-honest run --output-dir ./my-audit --no-png
```

With no arguments, the launcher runs the full audit with both providers and both language packs. It
writes to a new timestamped `dumb-n-honest-output-*` directory in the current working directory, so
existing results are never overwritten.

This package is a thin launcher with no npm dependencies. It:

1. finds a local Python 3.10+ interpreter,
2. downloads the official `dumb-n-honest` release from GitHub Releases,
3. verifies its SHA256 against a hash pinned in this package before every run,
4. extracts the verified archive to a fresh temporary directory,
5. runs the original Python scripts and removes the temporary directory afterward.

The launcher uses the network only to fetch a missing release archive. It never reads transcripts;
all parsing stays in the verified Python release. The audit itself runs offline, writes only
aggregates, and never publishes anything automatically.
Requires Node 18+ (for the launcher only) and Python 3.10+.

`DUMB_N_HONEST_VERSION` can select only a release whose SHA256 is pinned by the installed launcher.
