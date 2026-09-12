#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Defensive file installer. No driver, PAM, sleep-mode or service-start changes."""
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent.parent
FILES = {
    'systemd/system-sleep/50-egis0576-fp-resume.sh': ('/usr/lib/systemd/system-sleep/50-egis0576-fp-resume.sh', 0o755),
    'scripts/egis0576-fprintd-wait': ('/usr/local/sbin/egis0576-fprintd-wait', 0o755),
    'systemd/fprintd.service.d/10-egis0576-resume.conf': ('/etc/systemd/system/fprintd.service.d/10-egis0576-resume.conf', 0o644),
}
STATE = '/var/lib/egis0576-resume'
MARKER = '/run/egis0576-fprintd-resume.pending'


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Manager:
    # root is only injectable by unit tests, never through CLI or environment.
    def __init__(self, root=Path('/')):
        self.root = Path(root)
        self.state = self.path(STATE)
        self.record = self.state / 'active.json'

    def path(self, absolute):
        return self.root / absolute.lstrip('/')

    def safe(self, path):
        for part in [path, *path.parents]:
            if part.is_symlink():
                raise RuntimeError(f'Refusing symlink: {part}')
            if part == self.root:
                break
        if path.exists() and not path.is_file():
            raise RuntimeError(f'Not a regular file: {path}')

    def write(self, path, data, mode=0o600, uid=None, gid=None):
        self.safe(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.egis0576-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), mode)
                if uid is not None:
                    os.fchown(stream.fileno(), uid, gid)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def reload(self):
        subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=30)

    def snapshot(self, path):
        self.safe(path)
        if not path.exists():
            return None
        info = path.stat()
        return {'data': base64.b64encode(path.read_bytes()).decode(),
                'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}

    def restore(self, entry):
        target = self.path(entry['target'])
        self.safe(target)
        old = entry['before']
        if old is None:
            target.unlink(missing_ok=True)
        else:
            self.write(target, base64.b64decode(old['data']), old['mode'], old['uid'], old['gid'])

    def preflight(self, replace):
        if self.path(MARKER).exists():
            raise RuntimeError('Resume marker exists. Resolve pending recovery before installation.')
        if self.record.exists():
            raise RuntimeError('Installation/transaction already recorded; uninstall first (also for upgrades).')
        for cmd in ('bash', 'systemctl', 'timeout', 'sleep', 'rm'):
            if not shutil.which(cmd):
                raise RuntimeError(f'Missing command: {cmd}')
        if not self.path('/run/systemd/system').is_dir():
            raise RuntimeError('A running systemd system is required.')
        props = subprocess.check_output(
            ['systemctl', 'show', 'fprintd.service', '-p', 'LoadState', '-p', 'User',
             '-p', 'DynamicUser', '-p', 'RootDirectory', '-p', 'RootImage'], text=True, timeout=15)
        values = dict(line.split('=', 1) for line in props.splitlines() if '=' in line)
        if values.get('LoadState') != 'loaded':
            raise RuntimeError('fprintd.service is missing, masked or not loadable.')
        if (values.get('User', '') not in ('', 'root') or values.get('DynamicUser') == 'yes'
                or values.get('RootDirectory') or values.get('RootImage')):
            raise RuntimeError('Unsupported fprintd service isolation/user configuration.')
        mode = self.path('/sys/power/mem_sleep').read_text()
        if '[s2idle]' not in mode:
            raise RuntimeError('s2idle must already be selected; installer never changes sleep mode.')
        devices = []
        for device in self.path('/sys/bus/usb/devices').glob('*'):
            try:
                if ((device / 'idVendor').read_text().strip() == '1c7a'
                        and (device / 'idProduct').read_text().strip() == '0576'):
                    devices.append(device)
            except FileNotFoundError:
                continue
        if len(devices) != 1:
            raise RuntimeError(f'Exactly one EH576 1c7a:0576 required; found {len(devices)}.')
        if not os.access(devices[0] / 'authorized', os.W_OK):
            raise RuntimeError('USB authorized attribute is not writable.')
        if (devices[0] / 'authorized').read_text().strip() != '1':
            raise RuntimeError('EH576 is currently unauthorized; resolve USB state first.')
        power = devices[0] / 'power/control'
        if not power.exists() or power.read_text().strip() != 'on':
            print('WARNING: USB power/control is not on; this differs from the reference system. '
                  'Review USB autosuspend separately. No power setting was changed.', file=sys.stderr)
        owned = {self.path(target) for target, _ in FILES.values()}
        for target in owned:
            self.safe(target)
            if target.exists() and not replace:
                raise RuntimeError(f'Existing file: {target}. Review it, then use --replace-existing to back it up.')
        # Conservative heuristic, not a proof of absence of conflicts. /lib may alias /usr/lib.
        conflicts = set()
        for folder in ('/usr/lib/systemd/system-sleep', '/lib/systemd/system-sleep',
                       '/etc/systemd/system-sleep', '/usr/local/lib/systemd/system-sleep',
                       '/etc/systemd/system/fprintd.service.d', '/run/systemd/system/fprintd.service.d',
                       '/usr/lib/systemd/system/fprintd.service.d'):
            for candidate in self.path(folder).glob('*'):
                if not candidate.is_file() or candidate.resolve() in {p.resolve() for p in owned}:
                    continue
                content = candidate.read_text(errors='replace')
                if re.search(r'egis|0576|fprint|authorized|usbreset', candidate.name + '\n' + content, re.I):
                    conflicts.add(str(candidate))
        if self.path('/etc/systemd/system/fprintd.service').exists():
            conflicts.add('/etc/systemd/system/fprintd.service (full service override)')
        if conflicts:
            raise RuntimeError('Potential conflicting configuration; review/remove manually:\n' + '\n'.join(sorted(conflicts)))
        for source in FILES:
            if not (REPO / source).is_file():
                raise RuntimeError(f'Missing project file: {source}')

    def install(self, replace=False, check=False):
        self.preflight(replace)
        if check:
            print('Preflight passed. No files installed. Driver functionality must be checked separately.')
            return
        entries = []
        for source, (target, mode) in FILES.items():
            data = (REPO / source).read_bytes()
            entries.append({'source': source, 'target': target, 'mode': mode,
                            'installed_sha256': digest(data), 'before': self.snapshot(self.path(target))})
        record = {'version': 1, 'phase': 'installing', 'files': entries}
        self.write(self.record, json.dumps(record, indent=2).encode())
        try:
            for entry in entries:
                self.write(self.path(entry['target']), (REPO / entry['source']).read_bytes(), entry['mode'])
            self.reload()
            record['phase'] = 'installed'
            self.write(self.record, json.dumps(record, indent=2).encode())
        except BaseException:
            # If rollback also fails, retain active.json for manual recovery/uninstall.
            for entry in reversed(entries):
                self.restore(entry)
            self.reload()
            self.archive('rolled-back')
            raise
        print(f'Installed. Original files and metadata saved in {self.record}. No daemon started/restarted.')

    def archive(self, suffix):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        os.replace(self.record, self.state / f'{stamp}-{suffix}.json')

    def uninstall(self):
        if self.path(MARKER).exists():
            raise RuntimeError('Resume marker exists. Resolve pending recovery before uninstalling.')
        self.safe(self.record)
        if not self.record.exists():
            raise RuntimeError('No active backup/installation record. Nothing removed.')
        record = json.loads(self.record.read_text())
        expected = {target for target, _ in FILES.values()}
        entries = record['files']
        if record.get('version') != 1 or {e['target'] for e in entries} != expected or len(entries) != len(expected):
            raise RuntimeError('Invalid backup manifest; refusing restoration.')
        for entry in entries:
            target = self.path(entry['target'])
            self.safe(target)
            before = entry['before']
            original = base64.b64decode(before['data']) if before else None
            current = target.read_bytes() if target.exists() else None
            # Accept an already restored file (interrupted rollback/uninstall).
            if current != original and (current is None or digest(current) != entry['installed_sha256']):
                raise RuntimeError(f'Locally modified/missing file: {target}. Preserve edits and resolve manually before retrying.')
        # Each step is restartable; keep the record until restoration AND reload succeed.
        for entry in reversed(entries):
            self.restore(entry)
        self.reload()
        self.archive('uninstalled')
        print(f'Original files restored; backups retained in {self.state}. No daemon restarted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall'))
    parser.add_argument('--check', action='store_true', help='installation preflight only')
    parser.add_argument('--replace-existing', action='store_true', help='back up and replace the three exact destination files')
    args = parser.parse_args()
    if args.action == 'uninstall' and (args.check or args.replace_existing):
        parser.error('installation options cannot be used with uninstall')
    if os.geteuid() != 0:
        parser.error('run with sudo/root; --check also requires root to check USB writability')
    manager = Manager()
    try:
        # Lock concurrent installer/uninstaller processes. No lock is needed for read-only preflight.
        if args.check:
            manager.install(args.replace_existing, check=True)
            return
        lock = manager.path('/run/egis0576-resume-install.lock')
        manager.safe(lock)
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.action == 'install':
                manager.install(args.replace_existing)
            else:
                manager.uninstall()
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
