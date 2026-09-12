#!/bin/bash
# SPDX-License-Identifier: MIT
# Read-only: does not invoke fprintd clients, change USB state or restart services.
set -u
PATH=/usr/sbin:/usr/bin:/sbin:/bin
printf '\n== OS and kernel ==\n'
cat /etc/os-release
uname -r
printf '\n== Sleep mode (brackets indicate selected mode) ==\n'
cat /sys/power/mem_sleep 2>/dev/null || true
printf '\n== EH576 ==\n'
found=0
for device in /sys/bus/usb/devices/*; do
    [[ -r $device/idVendor && -r $device/idProduct ]] || continue
    [[ $(< "$device/idVendor") == 1c7a && $(< "$device/idProduct") == 0576 ]] || continue
    found=1
    printf 'USB path: %s\n' "${device##*/}"
    for attr in authorized power/control power/runtime_status; do
        printf '%s: ' "$attr"
        cat "$device/$attr" 2>/dev/null || true
    done
done
(( found )) || printf 'EH576 not found\n'
printf '\n== Sleep hooks (including executable backup copies) ==\n'
for folder in /usr/lib/systemd/system-sleep /etc/systemd/system-sleep /usr/local/lib/systemd/system-sleep; do
    [[ -d $folder ]] || continue
    ls -l -- "$folder"
done
printf '\n== Local EH576 udev rules ==\n'
for rule in /etc/udev/rules.d/*.rules; do
    [[ -r $rule ]] || continue
    grep -nEi 'egis|0576' "$rule" /dev/null || true
done
printf '\n== Pending recovery ==\n'
stat /run/egis0576-fprintd-resume.pending 2>/dev/null || true
printf '\n== Effective fprintd unit ==\n'
systemctl cat fprintd.service || true
systemctl show fprintd.service -p LoadState -p ActiveState -p SubState -p Result || true
printf '\n== Current boot: fprintd and suspend logs ==\n'
journalctl -b --no-pager -n 150 -u fprintd.service -u systemd-suspend.service || true
printf '\n== Installed workaround files ==\n'
sha256sum /usr/lib/systemd/system-sleep/50-egis0576-fp-resume.sh \
    /usr/local/sbin/egis0576-fprintd-wait \
    /etc/systemd/system/fprintd.service.d/10-egis0576-resume.conf 2>/dev/null || true
printf '\nReview logs for usernames, hostnames and other personal information before sharing.\n'
