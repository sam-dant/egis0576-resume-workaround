# Reference system inspection

[Português](reference-system.md) | **English** · [README](../README.en.md)

Read-only inspection performed while preparing the project. These findings describe the observed configuration; they do not certify that the new scripts have been run on this hardware.

| Item | Observed |
| --- | --- |
| Distribution | Zorin OS 18.1 |
| Running kernel | `7.0.0-31-generic` |
| systemd | `255.4-1ubuntu8.17` |
| Sleep mode | `[s2idle] deep` (s2idle selected) |
| Reader | `1c7a:0576`, USB path `3-8` at inspection time |
| USB | `authorized=1`, `power/control=on`, `power/runtime_status=active` |
| Local rule | `/etc/udev/rules.d/60-egis0576-fp-nosuspend.rules` forces `power/control=on` on the add event for this VID/PID |
| Service | `Type=dbus`, `BusName=net.reactivated.Fprint` |
| Drop-in | `10-egis0576-resume.conf` adds the helper through `ExecStartPre` |
| Marker | Absent at inspection time |

The inspected kernel and GRUB command lines did not contain `mem_sleep_default=deep`. This does not establish how s2idle was originally selected or guarantee the selected mode on another boot. The installer checks the active mode and does not edit GRUB.

## Driver commit used in validation

The user reported that the original validation used commit [7849db90c37131b0662e7e17059caebfb9b277c7](https://github.com/PHILIPPDEV5396/libfprint-egis0576/commit/7849db90c37131b0662e7e17059caebfb9b277c7) of `PHILIPPDEV5396/libfprint-egis0576`. This information was supplied by the user, not extracted from the binary during inspection. The workaround does not download, modify, or automatically pin this driver version.

## Differences between the existing code and this package

The installed hook creates an empty marker, stops fprintd, deauthorizes USB, waits 1.5 seconds, reauthorizes it, and removes the marker. It does not restart the daemon in `post`. It uses `set +e`, handles `pre/post` without filtering the second argument, and removes the marker even if it cannot find the reader. It includes debug logging.

The installed helper waits 150 times for 0.1 seconds, then returns success **even if the marker remains**. The new helper waits up to 120 times for 0.25 seconds and fails if recovery remains pending. This policy change, filtering for `suspend`, and error safeguards must be included in hardware validation of the new version. The package is not a byte-for-byte copy of the configuration in use.

Three additional files, all with mode `0755`, exist in the hook directory:

- `50-egis0576-fp-resume.sh.bak`
- `50-egis0576-fp-resume.sh.before-sync`
- `50-egis0576-fp-resume.sh.debug`

They contain alternative reader recovery implementations. Do not assume that a backup extension disables an executable in that directory. The installer conservatively treats them as potential conflicts requiring review. Before installing the new version, preserve these copies outside hook directories; the project does not move them automatically. The inspection did not establish which copies ran during previous suspends.

## USB autosuspend is a separate setting

`s2idle` is the system sleep mode; `power/control=on` disables idle autosuspend for this USB device. These are distinct settings. This project does not install or remove the observed udev rule. A system with `power/control=auto` differs from the reference system and should be investigated accordingly. Comments in an old rule do not establish the version or protocol of the currently loaded driver.

No system files were modified, no services were restarted, and no suspension or authentication was triggered during inspection.
