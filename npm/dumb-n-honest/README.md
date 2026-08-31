# dumb-n-honest (npx)

Run the [dumb-n-honest](https://github.com/yamancan/dumb-n-honest) private local benchmark with
one command:

```bash
npx dumb-n-honest doctor
npx dumb-n-honest run --output-dir ./my-audit --no-png
```

This package is a thin, dependency-free launcher. It:

1. finds a local Python 3.10+ interpreter,
2. downloads the official `dumb-n-honest` release from GitHub Releases,
3. verifies its SHA256 against a hash pinned in this package before executing anything,
4. extracts it under `~/.dumbandhonest/versions/<version>/` and runs the original Python scripts.

The launcher never reads transcripts itself; all parsing stays in the audited Python release.
The audit runs offline, writes only aggregates, and never publishes anything automatically.
Requires Node 18+ (for the launcher only) and Python 3.10+.

Set `DUMB_N_HONEST_VERSION` to use another release.
