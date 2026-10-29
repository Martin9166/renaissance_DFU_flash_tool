import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dfu_flash
from src.constants import UENV_TEMPLATE
from src.flash import dfu_download
from src.parse import FLASH_MEDIA, get_command, get_repartition_env, parse_cfg_file


class RepartitionTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            name: {
                "path": f"{name}.ext4", "addr": "0x0",
                "media": FLASH_MEDIA.EMMC, "attrs": f"part,0,{number}",
            }
            for number, name in enumerate(("rootfs_a", "rootfs_b", "data"), 1)
        }
        self.sizes = {"rootfs_a.ext4": 2 * 1024 ** 3,
                      "rootfs_b.ext4": 1024 ** 3, "data.ext4": 513}
        self.size_patch = patch("src.parse.os.path.getsize",
                                side_effect=lambda path: self.sizes[path]
                                if path in self.sizes else Path(path).stat().st_size)
        self.size_patch.start()
        self.addCleanup(self.size_patch.stop)

    def test_layout_and_capacity_checks(self):
        env = get_repartition_env(self.config)
        self.assertIn("name=rootfs_a,start=1MiB,size=2GiB,uuid=", env)
        self.assertIn("name=rootfs_b,size=2GiB,uuid=", env)
        self.assertIn("name=data,size=-,uuid=", env)
        self.assertIn("gpt write mmc 0 ${emmc_layout} && mmc rescan && "
                      "gpt verify mmc 0 ${emmc_layout}", env)
        for number, blocks in ((1, "0x400000"), (2, "0x200000"), (3, "0x2")):
            self.assertIn(f"part size mmc 0 {number} emmc_part_blocks && "
                          f"test 0x${{emmc_part_blocks}} -ge {blocks}", env)
        uuids = [field.split("=", 1)[1] for field in
                 env.splitlines()[0].split("=", 1)[1].replace(",", ";").split(";")
                 if field.startswith(("uuid=", "uuid_disk="))]
        self.assertEqual(len(set(uuids)), 4)

    def test_existing_command_is_unchanged_without_flag(self):
        self.assertEqual(
            get_command(self.config, False),
            'setenv dfu_alt_info "rootfs_a part 0 1;rootfs_b part 0 2;data part 0 3";'
            'dfu 0 mmc 0;',
        )

    def test_fixed_partition_image_boundaries(self):
        get_repartition_env(self.config)
        for name in ("rootfs_a.ext4", "rootfs_b.ext4"):
            with self.subTest(name=name):
                original = self.sizes[name]
                self.sizes[name] = 2 * 1024 ** 3
                get_repartition_env(self.config)
                self.sizes[name] += 1
                with self.assertRaisesRegex(ValueError, "exceeds 2 GiB"):
                    get_repartition_env(self.config)
                self.sizes[name] = original

    def test_missing_duplicate_empty_and_invalid_targets(self):
        cases = [
            ("missing", lambda c: c.pop("data")),
            ("duplicate", lambda c: c.update(copy=dict(c["rootfs_b"]))),
            ("wrong hardware partition",
             lambda c: c["rootfs_b"].update(attrs="part,1,2")),
            ("wrong partition", lambda c: c["rootfs_b"].update(attrs="part,0,4")),
            ("raw UDA", lambda c: c["rootfs_b"].update(attrs="raw,0,-")),
            ("offset", lambda c: c["rootfs_b"].update(addr="0x200")),
            ("media", lambda c: c["rootfs_b"].update(media=FLASH_MEDIA.NOR)),
        ]
        for name, change in cases:
            with self.subTest(name=name):
                config = {key: dict(value) for key, value in self.config.items()}
                change(config)
                with self.assertRaises(ValueError):
                    get_repartition_env(config)
        self.sizes["data.ext4"] = 0
        with self.assertRaisesRegex(ValueError, "empty"):
            get_repartition_env(self.config)

    def test_boot0_raw_entries_are_preserved(self):
        self.config["tiboot3"] = {
            "path": "tiboot3.bin", "addr": "0x0",
            "media": FLASH_MEDIA.EMMC, "attrs": "raw,1,-",
        }
        self.sizes["tiboot3.bin"] = 513
        get_repartition_env(self.config)
        self.assertIn("tiboot3 raw 0x0 0x2 mmcpart 1",
                      get_command(self.config, False, True))

    def test_boot0_configuration_precedes_dfu_and_gates_failures(self):
        self.config["tiboot3"] = {
            "path": "tiboot3.bin", "addr": "0x0",
            "media": FLASH_MEDIA.EMMC, "attrs": "raw,1,-",
        }
        self.sizes["tiboot3.bin"] = 513
        for repartition in (False, True):
            command = get_command(self.config, True, repartition)
            subprocess.run(["sh", "-n", "-c", command], check=True)
            for failure in ("partconf", "bootbus", "none"):
                with self.subTest(repartition=repartition, failure=failure):
                    stubs = (
                        'run() { return 0; }; setenv() { :; }; '
                        f'mmc() {{ echo "MMC $*"; [ "$1" != "{failure}" ]; }}; '
                        'dfu() { echo DFU_STARTED; }; '
                        'mw() { :; }; reset() { echo RESET_CALLED; }; '
                    )
                    result = subprocess.run(["sh", "-c", stubs + command],
                                            check=True, capture_output=True, text=True)
                    self.assertEqual("DFU_STARTED" in result.stdout, failure == "none")
                    self.assertEqual("RESET_CALLED" in result.stdout, failure == "none")
                    self.assertEqual("ERROR:" in result.stdout, failure != "none")
                    if failure == "none":
                        self.assertIn(
                            "MMC dev 0 0\nMMC partconf 0 1 1 1\n"
                            "MMC bootbus 0 2 0 0\nMMC dev 0 0\nDFU_STARTED",
                            result.stdout,
                        )

    def test_non_boot0_targets_do_not_change_boot_configuration(self):
        for media, attrs in ((FLASH_MEDIA.EMMC, "raw,2,-"),
                             (FLASH_MEDIA.NOR, None)):
            with self.subTest(media=media, attrs=attrs):
                config = {"image": dict(self.config["rootfs_a"],
                                        media=media, attrs=attrs)}
                command = get_command(config, False)
                self.assertNotIn("mmc partconf", command)
                self.assertNotIn("mmc bootbus", command)

    def test_generated_shell_syntax_and_failure_gates(self):
        env = get_repartition_env(self.config)
        for line in env.splitlines()[1:]:
            subprocess.run(["sh", "-n", "-c", line.split("=", 1)[1]], check=True)
        command = get_command(self.config, True, True)
        subprocess.run(["sh", "-n", "-c", command], check=True)
        for failure in ("emmc_prepare", "emmc_check", "none"):
            with self.subTest(failure=failure):
                stubs = (
                    f'run() {{ [ "$1" != "{failure}" ]; }}; '
                    'setenv() { :; }; '
                    'dfu() { echo DFU_STARTED; }; '
                    'mw() { :; }; reset() { echo RESET_CALLED; }; '
                )
                result = subprocess.run(["sh", "-c", stubs + command],
                                        check=True, capture_output=True, text=True)
                self.assertEqual("DFU_STARTED" in result.stdout, failure == "none")
                self.assertEqual("RESET_CALLED" in result.stdout, failure == "none")
                self.assertEqual("ERROR:" in result.stdout, failure != "none")
        text = env + UENV_TEMPLATE.format(command) + "\0"
        self.assertTrue(text.endswith("\n\0"))

    def test_environment_commands_fit_local_command_buffer(self):
        env = get_repartition_env(self.config)
        command = get_command(self.config, True, True)
        for line in (env + UENV_TEMPLATE.format(command)).splitlines():
            self.assertLess(len(line), 1024)

    def test_dry_run_generates_env_without_usb(self):
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory) / "test" / "hsfs"
            device.mkdir(parents=True)
            for name in ("tiboot3.bin", "tispl.bin", "u-boot.img"):
                (device / name).touch()
            with patch.object(dfu_flash, "BIN_DIR_PATH", Path(directory)), \
                 patch.object(dfu_flash, "parse_cfg_file", return_value=self.config), \
                 patch.object(dfu_flash, "dfu_main") as flash, \
                 patch("sys.argv", ["dfu_flash.py", "-d", "test", "-t", "hsfs",
                                    "--repartition-emmc", "--dry-run"]):
                (device / "flash-files.cfg").touch()
                dfu_flash.main()
            flash.assert_not_called()
            text = (device / "uEnv.txt").read_bytes()
            self.assertIn(b"emmc_prepare=", text)
            self.assertIn(b"user_commands=if run emmc_prepare", text)
            self.assertTrue(text.endswith(b"\n\0"))

    def test_example_configuration_maps_three_partitions(self):
        example = (Path(__file__).resolve().parents[1] /
                   "bin/am62xx-evm/hsfs/flash-three-partitions.cfg")
        with patch("src.parse.os.path.exists", return_value=True):
            config = parse_cfg_file(example)
        self.assertEqual([entry["attrs"] for entry in config.values()],
                         ["raw,1,-"] * 3 + ["part,0,1", "part,0,2", "part,0,3"])
        self.assertEqual(list(config)[-3:], ["rootfs_a", "rootfs_b", "data"])


class DownloadTests(unittest.TestCase):
    @patch("src.flash.wait_for_dfu_enumeration", return_value=True)
    @patch("src.flash.subprocess.run")
    def test_progress_does_not_hide_final_failure(self, run, wait):
        for code, output, expected in ((0, b"100%", True),
                                       (1, b"100%", False),
                                       (0, b"50%", False)):
            with self.subTest(code=code, output=output):
                run.return_value = SimpleNamespace(
                    returncode=code, stdout=output, stderr=b"")
                self.assertEqual(dfu_download("test", "rootfs", "rootfs.ext4"), expected)


if __name__ == "__main__":
    unittest.main()
