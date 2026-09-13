# EgisTec EH576 — suspend/resume synchronization

[Português](README.md) | **English**

A workaround for the **EgisTec EH576 (`1c7a:0576`)** fingerprint reader: stops `fprintd` before suspend, reauthorizes the USB device after resume, and blocks early daemon activation until that operation finishes.

This project **does not install or modify the driver**, PAM, enrolled fingerprints, power rules, or the system sleep mode. The driver is a separate project: [PHILIPPDEV5396/libfprint-egis0576](https://github.com/PHILIPPDEV5396/libfprint-egis0576). Enrollment and authentication must work before installing this workaround.

## Background and validation status

The reference solution was reported stable for several days on a **Lenovo IdeaPad Flex 5 14ITL05, Zorin OS 18.1, GNOME/GDM, s2idle**, across multiple suspend, lid-close/open, and fingerprint-unlock cycles. Symptoms included `Device was already claimed` and `Device 1c7a:0576 is already open`; manually restarting `fprintd` restored operation. The reported investigation identified a race between daemon activation and USB recovery.

The scripts in this repository were written from that report. **This packaged version received initial hardware validation on the reference laptop on 2026-09-13, with driver v0.4.3 (`5448ab7`).** With only the official driver hook, fingerprint unlock was not offered after suspend; after installing this package, the user confirmed it worked following menu suspend and lid-close/open. Long-term stability and failure paths still require hardware validation. v0.4.4 has not been tested. Automated tests use temporary files and mocked commands; they do not reproduce the USB kernel subsystem, systemd scheduling, D-Bus, or GDM. The driver commit used in the original validation, as reported by the reference system user, was [7849db90c37131b0662e7e17059caebfb9b277c7](https://github.com/PHILIPPDEV5396/libfprint-egis0576/commit/7849db90c37131b0662e7e17059caebfb9b277c7). This records the version used; it is not verification of the installed binary or a guarantee of compatibility with other commits.

A read-only inspection confirmed local settings and identified differences in the helper and additional hook copies: see the [reference system](docs/reference-system.en.md). An existing udev rule keeps `power/control=on`; this project does not manage that rule.

Preserved decisions:

- Do not run `systemctl restart fprintd` in `post`. That approach worsened GDM behavior and produced libusb warnings on the reference system.
- Keep normal D-Bus/GDM activation after the marker is removed.
- Stay on **s2idle**. Testing `deep` froze the reference laptop and required a forced power-off. The installer rejects other selected modes and does not change the mode.

## How it works

1. `pre suspend`: creates `/run/egis0576-fprintd-resume.pending`, then stops `fprintd.service` with a 15-second timeout. Marks the phase ready only if stopping succeeds.
2. `post suspend`: requires a completed `pre` phase, searches for exactly one `1c7a:0576` USB device for up to approximately 10 seconds, writes `0` to its `authorized` attribute, waits **1.5 seconds**, writes `1`, and removes the marker.
3. The drop-in adds `ExecStartPre=/usr/local/sbin/egis0576-fprintd-wait`. The helper waits while the marker exists; once it disappears, normal daemon startup can proceed.

Use of the `authorized` attribute follows the [kernel USB documentation](https://www.kernel.org/doc/html/latest/usb/authorization.html). The controller, hubs, and other USB devices are not reset.

Added safeguards include bounded stopping and waiting, rejection of multiple readers, retries when locating the USB device, and attempted reauthorization if an error occurs during the pause. On failure, the marker is retained and the helper **fails after approximately 30 seconds**, preventing daemon startup. The helper never removes the marker. Fingerprint authentication may remain unavailable until recovery; use your password.

The hook handles only `suspend`. Hibernation, hybrid sleep, and `suspend-then-hibernate` are unsupported. A hook failure must not be relied upon to cancel suspension. The marker is not a reader health check: successfully writing `authorized` does not guarantee firmware or driver readiness on every machine.

## Files

| Source | Installed destination |
| --- | --- |
| `systemd/system-sleep/50-egis0576-fp-resume.sh` | `/usr/lib/systemd/system-sleep/50-egis0576-fp-resume.sh` |
| `scripts/egis0576-fprintd-wait` | `/usr/local/sbin/egis0576-fprintd-wait` |
| `systemd/fprintd.service.d/10-egis0576-resume.conf` | `/etc/systemd/system/fprintd.service.d/10-egis0576-resume.conf` |

`install.sh` and `uninstall.sh` use the Python backend `lib/manage.py`. Installed scripts use only Bash, systemctl, and basic utilities. Diagnostics run from the project checkout and are not installed system-wide.

## Prerequisites and installation

Requires Linux with a running systemd instance, Bash, Python **3.8+**, GNU coreutils (`timeout`, `sleep`, `rm`), a loadable `fprintd.service`, and exactly one already-authorized EH576. `[s2idle]` must be selected in `/sys/power/mem_sleep`. Immutable distributions and systems with different hook locations require adaptation and are not targets of this version.

### Are additional downloads required?

The workaround is self-contained: there are **no pip/npm dependencies, submodules, or compilation steps**. Installation does not download anything and can run offline once the project and system prerequisites are available. Python code uses only the standard library.

The EH576-capable libfprint driver and `fprintd` must already be installed and working; they are separate prerequisites and are not bundled. If they already work on your system, this project does not require downloading or reinstalling them.

**ShellCheck is optional for local development**, not required to run the workaround. If unavailable, `scripts/check.sh` still runs Bash syntax checks and Python tests. The GitHub Actions workflow downloads its checkout action and installs ShellCheck through apt on the CI runner, so that workflow requires network access. Git is useful for version control but is not an installer dependency. The diagnostic script also uses standard system tools, including `journalctl`, `grep`, and `sha256sum`.

First verify enrollment and authentication with the driver, and confirm that you can log in with a **password**. Save your work and keep the machine awake throughout installation/uninstallation; do not perform these operations during a suspend cycle.

From the project directory:

```bash
./scripts/check.sh
sudo ./install.sh --check
sudo ./install.sh
```

`--check` runs preflight without installing files or reloading systemd. It requires root to check USB write access. Installation changes only the three files listed above, creates a backup record under `/var/lib/egis0576-resume`, uses a lock in `/run`, and runs `systemctl daemon-reload`. It does not start, stop, or restart the daemon during installation.

If the original solution already occupies the **three exact destinations**, review those files and use:

```bash
sudo ./install.sh --check --replace-existing
sudo ./install.sh --replace-existing
```

Previous contents, permissions, UID, and GID are preserved for restoration. ACLs, extended attributes, and custom SELinux labels are not preserved; installation targets the described Zorin environment. Symlinks at destinations or in ancestor directories are rejected.

The installer rejects an existing installation record, a pending marker, missing/ambiguous hardware, an unauthorized USB device, missing/masked `fprintd`, a mode other than s2idle, and some incompatible service customizations. It also searches other hooks and drop-ins for references to Egis/fprint/USB reset. **This is a heuristic, not an exhaustive compatibility check**: review `systemctl cat fprintd.service` and local hooks.

The [driver project](https://github.com/PHILIPPDEV5396/libfprint-egis0576) also provides suspend integration. A competing hook must be reviewed and manually disabled before installation. `--replace-existing` only authorizes replacing this project's three destinations; it does not bypass conflicts with other files. Do not remove the driver library to resolve a hook conflict.

## Hardware test: suspend → resume → lock → fingerprint

Test with no enrollment or fingerprint verification in progress. Record the kernel, distribution, driver version/commit, and desktop version.

1. Before the first suspend, verify normal authentication and password fallback. Check `cat /sys/power/mem_sleep` and `systemctl cat fprintd.service`.
2. Suspend using the desktop menu, resume, and confirm marker removal: `test ! -e /run/egis0576-fprintd-resume.pending` should return zero.
3. Lock the session through the desktop interface and unlock with your fingerprint. If resume already presents a locked screen, test there too; use your password if necessary.
4. Repeat at least five cycles. Also test locking **before** suspend, closing/opening the lid, and resuming on AC and battery power. Let each authentication attempt finish before repeating.
5. Capture `sudo ./scripts/diagnose.sh` after testing. Look for startup failures, a persistent marker, timeouts, and recurring claim/open errors. There should be no explicit daemon restart in `post`.
6. During a maintenance window, test uninstalling and confirm restoration of previous files. Reinstall if you want to keep using the workaround.

An inactive `fprintd` while idle does not, by itself, indicate a failure: activation is on demand. No automated workflow locks the screen, suspends the machine, or attempts user authentication.

## Diagnostics and troubleshooting

```bash
sudo ./scripts/diagnose.sh > diagnostics-local.txt 2>&1
```

Diagnostics are read-only: they show OS/kernel, sleep mode, relevant EH576 attributes, the marker, effective unit configuration, state, and current-boot logs. They do not read biometric templates or invoke clients that activate the reader. Review usernames, hostnames, and other personal information before sharing logs.

**Persistent marker or helper timeout:** log in with your password, capture diagnostics, and check `egis0576-resume` messages in the `systemd-suspend.service` journal. Do not delete the marker during recovery. Content `stopping` means `pre` did not finish; `ready` means stopping completed but recovery has not removed the marker. Neither value proves that the hook is still running.

After saving your work and collecting logs, **rebooting the computer** is the simplest recovery: `/run` is temporary and the device goes through normal initialization. This also lets you retry uninstalling if a pending marker was blocking it. If the problem recurs, uninstall and investigate the driver/USB before further testing. Automatic suspend shortly after boot may recreate the problem: keep the session awake during maintenance.

**Claim/open errors continue without a marker:** check for other hooks or drop-ins, record the driver version, and determine whether the problem exists before suspend. Manually restarting `fprintd` restored operation in the original investigation; this must not become an automatic restart in the `post` hook.

**Missing reader or failed reauthorization:** the hook keeps the startup gate closed. Check USB logs; do not change `authorized` for hubs or another USB ID. This implementation matches only `1c7a:0576`.

**Installation/uninstallation failure:** preserve `/var/lib/egis0576-resume/active.json` and the current files. The installer attempts automatic rollback if an exception occurs during installation. If rollback or reload also fails, the record remains for recovery. Once the cause is resolved, run `sudo ./uninstall.sh`: it accepts already-restored files and can resume an interrupted restoration. Abrupt interruption and storage failures may require manual recovery; backups do not guarantee protection against physical data loss.

## Uninstallation, rollback, and upgrades

```bash
sudo ./uninstall.sh
```

Uninstallation restores each destination's previous contents and basic metadata; it removes only files that did not previously exist. Created directories may remain empty. It reloads systemd without restarting the daemon. Therefore, if there was an earlier workaround, **it becomes installed again**.

JSON records contain original contents in Base64 and SHA-256 hashes of installed contents. They are saved with mode `0600`. After success, `active.json` is renamed with a UTC timestamp and an `uninstalled` or `rolled-back` suffix, preserving history. Do not delete this directory before uninstalling.

If an installed file's contents were locally modified or removed, uninstallation refuses to overwrite it unless it already matches its original state. Save your changes and restore the installed version's contents (or the original from backup) before retrying. There is no `--force` option to discard edits. Permission-only changes are not treated as content changes.

To upgrade, use the current version's uninstaller, then the new version's installer. There are no automatic updates or driver package management.

## Development

```bash
./scripts/check.sh
```

Runs `bash -n`, ShellCheck when available, and Python standard-library `unittest` tests. CI installs and requires ShellCheck. Tests modify copies of scripts to point to temporary files; production scripts do not accept environment variables that redirect privileged paths.

Coverage includes marker/stop ordering, the 1.5-second pause while USB is unauthorized, reauthorization, absence of start/restart in `post`, missing/duplicate readers, stop/pause failures, helper timeout, installation, backup, rollback, conflict rejection, and interrupted restoration. Passing these tests does not replace the hardware procedure above.

License: [MIT](LICENSE), covering only the original files of this workaround. No driver code is included. The driver's licensing terms remain separate.
