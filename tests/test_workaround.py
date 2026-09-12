# SPDX-License-Identifier: MIT
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage', REPO / 'lib/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.marker = self.root / 'pending'
        self.usb = self.root / 'usb'
        self.usb.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'events'
        self.fake('systemctl', 'printf "systemctl %s marker=%s\\n" "$*" "$(test -f "$MARKER_TEST" && echo present)" >> "$EVENTS"\nexit "${STOP_FAIL:-0}"')
        self.fake('sleep', 'printf "sleep %s\\n" "$*" >> "$EVENTS"\nif [ "${CLEAR_MARKER:-0}" = 1 ]; then /bin/rm -f "$MARKER_TEST"; fi\nexit "${SLEEP_FAIL:-0}"')
        self.env = dict(os.environ, EVENTS=str(self.log), MARKER_TEST=str(self.marker))

    def fake(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def device(self, name='1-4', product='0576'):
        device = self.usb / name
        device.mkdir()
        (device / 'idVendor').write_text('1c7a\n')
        (device / 'idProduct').write_text(product + '\n')
        (device / 'authorized').write_text('1\n')
        return device

    def run_script(self, source, *args, **env):
        # Transform copies only: installed scripts cannot redirect privileged paths via environment.
        content = (REPO / source).read_text().replace(
            'PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'PATH={self.bin}:/usr/bin:/bin')
        content = content.replace('/run/egis0576-fprintd-resume.pending', str(self.marker))
        content = content.replace('/sys/bus/usb/devices', str(self.usb))
        script = self.root / 'script'
        script.write_text(content)
        return subprocess.run(['bash', str(script), *args], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=5)

    def hook(self, phase, action='suspend', **env):
        return self.run_script('systemd/system-sleep/50-egis0576-fp-resume.sh', phase, action, **env)

    def test_pre_creates_marker_before_stop(self):
        self.assertEqual(self.hook('pre').returncode, 0)
        self.assertTrue(self.marker.exists())
        self.assertIn('stop fprintd.service marker=present', self.log.read_text())

    def test_stop_failure_retains_gate(self):
        self.assertNotEqual(self.hook('pre', STOP_FAIL='1').returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_post_after_failed_stop_refuses_reset(self):
        device = self.device()
        self.hook('pre', STOP_FAIL='1')
        self.assertNotEqual(self.hook('post').returncode, 0)
        self.assertEqual((device / 'authorized').read_text(), '1\n')
        self.assertNotIn('sleep', self.log.read_text())

    def test_post_reauthorizes_then_releases_without_start(self):
        device = self.device()
        other = self.device('1-5', '1234')
        self.marker.write_text('ready\n')
        self.fake('sleep', 'test "$(cat "$USB_AUTH")" = 0 || exit 9\ntest -f "$MARKER_TEST" || exit 8\nprintf "sleep %s\\n" "$*" >> "$EVENTS"')
        result = self.hook('post', USB_AUTH=str(device / 'authorized'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertEqual((device / 'authorized').read_text(), '1\n')
        self.assertEqual((other / 'authorized').read_text(), '1\n')
        self.assertEqual(self.log.read_text(), 'sleep 1.5\n')

    def test_interrupted_reset_reauthorizes_and_keeps_gate(self):
        device = self.device()
        self.marker.write_text('ready\n')
        self.assertNotEqual(self.hook('post', SLEEP_FAIL='1').returncode, 0)
        self.assertEqual((device / 'authorized').read_text(), '1\n')
        self.assertTrue(self.marker.exists())

    def test_missing_device_keeps_gate(self):
        self.marker.write_text('ready\n')
        self.assertNotEqual(self.hook('post').returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_ambiguous_device_is_not_reset(self):
        a, b = self.device(), self.device('1-5')
        self.marker.write_text('ready\n')
        self.assertNotEqual(self.hook('post').returncode, 0)
        self.assertTrue(self.marker.exists())
        self.assertEqual((a / 'authorized').read_text(), (b / 'authorized').read_text())
        self.assertFalse(self.log.exists())

    def test_post_without_pre_refuses_reset(self):
        self.device()
        self.assertNotEqual(self.hook('post').returncode, 0)
        self.assertFalse(self.log.exists())

    def test_hibernate_is_noop(self):
        self.assertEqual(self.hook('pre', 'hibernate').returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.log.exists())

    def test_helper_without_marker(self):
        self.assertEqual(self.run_script('scripts/egis0576-fprintd-wait').returncode, 0)
        self.assertFalse(self.log.exists())

    def test_helper_timeout_fails_closed(self):
        self.marker.write_text('ready\n')
        result = self.run_script('scripts/egis0576-fprintd-wait')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.marker.exists())
        self.assertIn('30s', result.stderr)

    def test_helper_released_on_marker_removal(self):
        self.marker.write_text('ready\n')
        result = self.run_script('scripts/egis0576-fprintd-wait', CLEAR_MARKER='1')
        self.assertEqual(result.returncode, 0)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = manage.Manager(self.root)
        self.reload = patch.object(self.manager, 'reload').start()
        self.addCleanup(patch.stopall)
        patch.object(manage.subprocess, 'check_output', return_value='LoadState=loaded\nUser=\nDynamicUser=no\n').start()
        self.put('/sys/power/mem_sleep', '[s2idle] deep')
        self.put('/sys/bus/usb/devices/1-4/idVendor', '1c7a')
        self.put('/sys/bus/usb/devices/1-4/idProduct', '0576')
        self.put('/sys/bus/usb/devices/1-4/authorized', '1')
        self.put('/sys/bus/usb/devices/1-4/power/control', 'on')
        self.manager.path('/run/systemd/system').mkdir(parents=True)
        self.target = self.manager.path(next(iter(manage.FILES.values()))[0])

    def put(self, path, content):
        file = self.manager.path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        return file

    def test_check_writes_nothing(self):
        self.manager.install(check=True)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.manager.state.exists())
        self.reload.assert_not_called()

    def test_install_uninstall(self):
        self.manager.install()
        self.assertTrue(self.target.exists())
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o755)
        self.manager.uninstall()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.manager.record.exists())
        self.assertEqual(len(list(self.manager.state.glob('*-uninstalled.json'))), 1)

    def test_backup_restores_original_content_and_mode(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text('old hook\n')
        self.target.chmod(0o700)
        with self.assertRaisesRegex(RuntimeError, 'Existing file'):
            self.manager.install()
        self.manager.install(replace=True)
        self.manager.uninstall()
        self.assertEqual(self.target.read_text(), 'old hook\n')
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o700)

    def test_modified_install_is_not_overwritten(self):
        self.manager.install()
        self.target.write_text('local edits')
        with self.assertRaisesRegex(RuntimeError, 'modified'):
            self.manager.uninstall()
        self.assertEqual(self.target.read_text(), 'local edits')
        self.assertTrue(self.manager.record.exists())

    def test_failed_reload_rolls_back(self):
        self.reload.side_effect = [RuntimeError('reload failed'), None]
        with self.assertRaisesRegex(RuntimeError, 'reload failed'):
            self.manager.install()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.manager.record.exists())

    def test_failed_write_restores_all_originals(self):
        original = self.manager.write
        calls = 0
        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('disk full')
            return original(*args, **kwargs)
        with patch.object(self.manager, 'write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.manager.install()
        self.assertFalse(self.target.exists())
        self.assertFalse(self.manager.record.exists())

    def test_uninstall_can_resume_after_reload_failure(self):
        self.manager.install()
        self.reload.side_effect = RuntimeError('reload failed')
        with self.assertRaises(RuntimeError):
            self.manager.uninstall()
        self.assertTrue(self.manager.record.exists())
        self.reload.side_effect = None
        self.manager.uninstall()
        self.assertFalse(self.manager.record.exists())

    def test_missing_hardware_refused(self):
        self.put('/sys/bus/usb/devices/1-4/idProduct', '9999')
        with self.assertRaisesRegex(RuntimeError, 'found 0'):
            self.manager.install()
        self.assertFalse(self.manager.record.exists())

    def test_multiple_hardware_refused(self):
        self.put('/sys/bus/usb/devices/1-5/idVendor', '1c7a')
        self.put('/sys/bus/usb/devices/1-5/idProduct', '0576')
        with self.assertRaisesRegex(RuntimeError, 'found 2'):
            self.manager.install()

    def test_unprivileged_service_refused(self):
        with patch.object(manage.subprocess, 'check_output', return_value='LoadState=loaded\nUser=fprint\n'):
            with self.assertRaisesRegex(RuntimeError, 'isolation/user'):
                self.manager.install()

    def test_executable_backup_hook_refused(self):
        backup = self.put('/usr/lib/systemd/system-sleep/50-egis0576-fp-resume.sh.debug', '# fprintd')
        backup.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, 'conflicting'):
            self.manager.install(replace=True)

    def test_deep_refused(self):
        self.put('/sys/power/mem_sleep', 's2idle [deep]')
        with self.assertRaisesRegex(RuntimeError, 's2idle'):
            self.manager.install()

    def test_other_hook_refused_even_with_replace(self):
        self.put('/usr/lib/systemd/system-sleep/other', '# reset egis0576')
        with self.assertRaisesRegex(RuntimeError, 'conflicting'):
            self.manager.install(replace=True)

    def test_symlink_refused(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.root / 'outside')
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            self.manager.install(replace=True)

    def test_pending_resume_refused(self):
        self.put(manage.MARKER, '')
        with self.assertRaisesRegex(RuntimeError, 'marker'):
            self.manager.install()

    def test_second_install_refused(self):
        self.manager.install()
        with self.assertRaisesRegex(RuntimeError, 'already recorded'):
            self.manager.install()


if __name__ == '__main__':
    unittest.main()
