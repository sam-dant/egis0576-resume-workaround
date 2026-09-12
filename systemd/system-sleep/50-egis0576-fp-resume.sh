#!/bin/bash
# SPDX-License-Identifier: MIT
# systemd calls sleep hooks with: pre|post suspend|hibernate|hybrid-sleep|suspend-then-hibernate.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
MARKER=/run/egis0576-fprintd-resume.pending
USB_ROOT=/sys/bus/usb/devices
log() { printf 'egis0576-resume: %s\n' "$*" >&2; }

# This project has only been validated with ordinary suspend (s2idle).
[[ ${2:-} == suspend ]] || exit 0
case ${1:-} in
    pre)
        umask 077
        printf 'stopping\n' > "$MARKER"
        # Bound the hook; failure leaves the gate closed for diagnosis.
        timeout 15s systemctl stop fprintd.service || {
            log 'Failed to stop fprintd; marker retained. See troubleshooting.'
            exit 1
        }
        printf 'ready\n' > "$MARKER"
        ;;
    post)
        [[ -f $MARKER ]] || { log 'No pre marker; refusing an unsynchronized USB reset.'; exit 1; }
        [[ $(< "$MARKER") == ready ]] || {
            log 'Pre phase did not finish stopping fprintd; refusing USB reset. Marker retained.'
            exit 1
        }
        device=
        # A USB device may not yet be visible immediately after resume.
        for ((attempt=0; attempt<20; attempt++)); do
            matches=()
            for candidate in "$USB_ROOT"/*; do
                [[ -r $candidate/idVendor && -r $candidate/idProduct ]] || continue
                [[ $(< "$candidate/idVendor") == 1c7a && $(< "$candidate/idProduct") == 0576 ]] || continue
                matches+=("$candidate")
            done
            if (( ${#matches[@]} == 1 )); then
                device=${matches[0]}
                break
            elif (( ${#matches[@]} > 1 )); then
                log 'Multiple EH576 devices; refusing ambiguous reset. Marker retained.'
                exit 1
            fi
            sleep 0.5
        done
        [[ -n $device && -w $device/authorized ]] || {
            log 'EH576 or writable authorized attribute missing. Marker retained.'
            exit 1
        }
        disabled=0
        recover() {
            status=$?
            trap - EXIT
            if (( disabled )); then
                printf '1\n' > "$device/authorized" || log "Recovery failed: $device/authorized"
            fi
            if (( status != 0 )); then log 'Recovery incomplete; marker retained. See troubleshooting.'; fi
            exit "$status"
        }
        trap recover EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        # Set first so even a failing write triggers a best-effort reauthorization.
        disabled=1
        printf '0\n' > "$device/authorized"
        sleep 1.5
        printf '1\n' > "$device/authorized"
        disabled=0
        rm -f -- "$MARKER"
        log "Reauthorized ${device##*/}; D-Bus activation released."
        ;;
    *) exit 0 ;;
esac
