## Introduction

Flash Writer is a tool used to flash binaries to the on-board memory. This application
note provides instructions on how to use flash writer tool for flashing. Flash
writer script will use USB DFU to boot the board and then flash the binaries to
on board memory. Tool also supports flashing multiple boards via DFU simultaneously.
It can be used for Sitara MPU devices such as AM64x, AM62x, AM62A.

## Requirements

* Board to be flashed
* Linux or Windows Development PC that can access serial console.
* Type C USB cable (depends on board)
* [Python][1] (3.10+)
* [DFU-Util][2] installed on host (0.11+)
* USB hub to connect multiple boards (Optional)
* UART to read the logs from the EVM (Optional)

## Flow of flashing

* Host PC is connected to boards via USB Type C (or other depending on board)
* After script is run, it will detect the devices connected to host. Script
  will send the bootloader binaries ( tiboot3.bin, tispl.bin and u-boot.img )
  from host PC to boards for USB DFU boot.
* After the boards are booted, Script will now send uEnv.txt file from host PC
  to boards.
* Environment variables on boards is set using uEnv.txt and boards is now ready
  for flashing. Script can now flash files from host PC to boards.

## Directory Structure

```
.
├── bin
│   ├── am62axx-evm
│   │   ├── gp
│   │   ├── hs
│   │   └── hsfs
│   ├── am62xx-evm
│   │   ├── gp
│   │   ├── hs
│   │   └── hsfs
│   └── am64xx-evm
│       ├── gp
│       ├── hs
│       └── hsfs
├── logs
├── src
│   ├── constants.py
│   ├── flash.py
│   ├── logger.py
│   └── parse.py
├── .gitignore
├── dfu_flash.py
├── LICENSE
└── README.md
```

* bin - Contains boot binaries used to boot the board via USB DFU, also config
  files for GP, HS and HS-SE.
* src - other required python modules for tool.
* dfu_flash.py - main python script that is to be run.
* logs - Contains saved logs of flash script.

## Get DFU-Util on Host PC

### Linux

* Install dfu-util

```
sudo apt-get install dfu-util
```

### Windows

* Download the [dfu-util-0.9-win64.zip][3] file from the dfu-util release site
  to get the executable files for dfu-util. Place them in a directory
  ex. C:\Program Files\dfu-util and then "edit the environment variables" to add
  this path.
* Download Zadig installer from the [Zadig website][4].
* Put the device in DFU mode. Then run the Zadig_2.2.exe file (or whatever version
  you downloaded).
* In the item that's highlighted, select libusbK using the tiny arrows. Then click
  the Install Driver button. For more information about libusbK, see their wiki.

## Steps to perform flashing

### Building Bootloader Binaries for USB DFU boot (custom board)

* For flashing and using the script, one need to override the bootcmd command to
  receive the environment variable text file after DFU boot and flash the
  binaries/images.
* DFU boot binaries for TI boards are already present in bin directory.
  For flashing to custom board custom board(s), generate the boot binaries
  and place them inside the /bin/<your board></your>/<type></type> folder.
* Following change needs to be done to a53 defconfig file in uboot. Ex. am62x_evm_a53_defconfig/
  am64x_evm_a53_defconfig/am62ax_evm_a53_defconfig file are located at path.

```
<U-boot source>/configs/
```

* Add or update the CONFIG_BOOTCOMMAND

```
CONFIG_BOOTCOMMAND="setenv dfu_alt_info_flashenv uEnv.txt ram 0x82000000 0x10000000; setenv dfu_alt_info ${dfu_alt_info_flashenv}; if dfu 0 ram 0; then if env import -t 0x82000000; then run user_commands; else echo ERROR: environment import failed; fi; else echo ERROR: environment download failed; fi;"
```

* It will enable script to send uEnv.txt file, import the environment variables
  from the uEnv.txt file and run user_commands after DFU boot. The user_commands
  variable is defined in the uEnv.txt file and the value assigned will be based
  on the flashing memory.
* Generated `uEnv.txt` files are NUL-terminated so text import can determine the
  end without relying on `${filesize}`, which RAM DFU does not reliably set.
  The import address must match the RAM DFU target address. The guarded boot
  command above requires rebuilding the USB DFU U-Boot binary; changing this
  host script alone does not change an existing binary's boot command.
* If you have saved environment variables in your board (or saved during earlier boot),
  u-boot takes the environment variables which will override the bootcmd which
  will cause the flashing to fail. To make u-boot not to take the saved environment
  variables you can do following changes in same config file.

```
Add below line.
CONFIG_ENV_IS_NOWHERE=y
 
Remove below line if present
CONFIG_ENV_IS_IN_MMC=y
 
Also add below line to decrease boot delay to 0
CONFIG_BOOTDELAY=0
```

* Now build u-boot. You can also use top level Makefile in SDK by running
  following commands on the terminal from the top-level of the SDK.

```
$ make u-boot_clean
$ make u-boot
```

* DFU boot binaries are required for flashing. These DFU binaries once booted on
  the board listens for the images to be flashed over USB DFU. Go to the
  respective directory `bin/${device}/${type}` and copy paste the DFU boot
  binaries (`tiboot3.bin`, `tispl.bin`, `u-boot.img`).

_Note: The prebuilt DFU boot binaries are provided for each device and type.
 These can be used for TI boards as it is. For custom boards, one may need to
 generate custom binaries. Create a custom device folder in the bin directory
 and use that as the argument for --device._

### Connections

* Power off the EVM and set up the boot mode switches to boot from DFU.

Ex.

```
AM64X EVM SW2[1:8] = 11001010 and SW3[1:8] = 00000000
AM62X EVM SW1[1:8] = 11001010 and SW2[1:8] = 00000000
```

* Connect board to PC via USB Type C (depend on board).
* Power on the board.
* Optionally you can also connect host pc to board via UART to read the console logs.

### Preparing the Flash Configuration file

- Go to the directory `bin/${device}/${type}` according to the device and the type.
- Edit the configuration file `flash-files.cfg` to list the commands for each of the files to be flashed.
- For each config line, prepare the following three arguments separated by space:
  - Edit the path using `--file=${path}`
  - Edit the operation using `--operation=${flash-nor|flash-emmc|flash-nand}`.
  - The operations `flash-nor` is used to flash the SPI NOR.
  - The operations `flash-nand` is used to flash the SPI NAND.
  - The operations `flash-emmc` is used to flash the eMMC.
  - Edit the offset using `--offset=${hex_address}`.

_Note: A default configuration file for Processor SDK images is provided for each device and type._

### Running the Python script

* Change the working directory in terminal to this project directory.
* Run the command

  ```bash
  ${PYTHON} dfu_flash.py [ -d device ] [ -t type ] [ -c cfg ] [ -r reset] 
  ```

  where ${PYTHON} evalutes to specific python command according to the OS.
  In most cases, this should be `python` for Windows while `python3` for Linux.
* Options

  - -d | --device : Argument to identify the device (Mandatory).
  - -t | --type   : Argument to identify the type of the device gp,hs,hsfs (Mandatory).
  - -c | --cfg    : Argument to get the path of the custom configuration file.
  - -r | --reset  : Argument to reset the board after flashing.
  - --repartition-emmc : Destructively recreate three partitions on eMMC 0 UDA before flashing.
  - --dry-run : Validate configuration and generate uEnv.txt without accessing USB devices.

### Automatically partitioning and flashing three ext4 images

**WARNING: `--repartition-emmc` destroys the existing UDA layout and overwrites
data on every detected board. Back up data first. It runs on every invocation
with this option, including boards that already have a valid GPT.**

The layout is fixed:


| UDA partition | Name     | Start                         | Size                                               |
| --------------- | ---------- | ------------------------------- | ---------------------------------------------------- |
| 1             | rootfs_a | 1 MiB                         | 2 GiB (2147483648 bytes), system slot A            |
| 2             | rootfs_b | Immediately after partition 1 | 2 GiB, system slot B                               |
| 3             | data     | Immediately after partition 2 | Remaining GPT-usable space, shared persistent data |

Together the system slots occupy 4294967296 bytes. The data capacity depends on
the actual UDA capacity, not the product's nominal capacity.
The data image must fit that remaining partition. A smaller ext4 image remains
smaller than its partition unless expanded; `df` reports filesystem capacity,
whereas `lsblk` reports partition capacity. Increasing slots does not resize
existing filesystems or change already-flashed boards. Repartitioning to apply
this layout destroys existing data, so back it up first.

Repartitioning affects UDA only, not the Boot0/Boot1 layout.
Optional raw Boot0/Boot1 image writes remain supported. Raw UDA writes, duplicate
partition targets, missing partition images and other media are rejected.

When the flash configuration includes a `raw,1,-` Boot0 image, the tool also
automatically executes `mmc partconf 0 1 1 1` and `mmc bootbus 0 2 0 0`
before starting eMMC DFU, with or without `--repartition-emmc`. These enable
Boot0 boot with boot acknowledgement and configure an 8-bit SDR boot bus.
The tool selects `mmc dev 0 0` before these commands and again afterwards so
partition targets are resolved in UDA, not Boot0. Command failure prints a UART
error and prevents DFU and reset. This changes persistent eMMC boot settings
before image transfers; an interrupted flash may therefore leave Boot0 enabled
with incomplete firmware. Use this configuration only on boards supporting these
boot settings. Partition-only, Boot1-only and non-eMMC configurations do not
change boot settings. No `saveenv` is required; these are eMMC device settings.

From `tools/DFU_flash`, place `rootfs_a.ext4`, `rootfs_b.ext4`, `data.ext4` in
`bin/am62xx-evm/hsfs/images/`, alongside the bootloader images referenced by the
example. First preview the generated environment:

```bash
python3 dfu_flash.py -d am62xx-evm -t hsfs \
    -c bin/am62xx-evm/hsfs/flash-three-partitions.cfg \
    --repartition-emmc --dry-run
```

Slots A and B may be initialized with identical system images. Image filenames
determine DFU alternate names; GPT partition names are fixed by the layout.
Legacy custom configurations still target the same partition numbers, regardless
of their filenames. Existing image files are not renamed by the tool. Regenerate
`uEnv.txt` with the updated configuration rather than editing it manually.

Then connect the board in USB DFU boot mode and run:

```bash
sudo python3 dfu_flash.py -d am62xx-evm -t hsfs \
    -c bin/am62xx-evm/hsfs/flash-three-partitions.cfg \
    --repartition-emmc
```

The separate example leaves the existing default `flash-files.cfg` unchanged.
Without `--repartition-emmc`, no partition table is created or modified.
`--dry-run` overwrites the generated `uEnv.txt`, but performs no board operations.
Configuration image paths are relative to the working directory.

The host generates fresh disk/partition UUIDs and rejects empty partition images
or images larger than the first two partitions. On the board, commands select
`mmc 0` UDA, write GPT, rescan, verify the layout and check every image's required
sector count against its actual partition size before starting DFU. A failure
prints an error on UART and does not start the flashing interface or reset the
board; the host subsequently reports that the expected DFU target is unavailable.
No intermediate reset is required on U-Boot versions that refresh partition
information after `gpt write`, including the local TI U-Boot implementation.

The USB DFU U-Boot must support `mmc`, `gpt write`, `gpt verify`, `part size`,
`test`, `run`, and hush `if`/`&&` syntax, with enough environment/command space.
Use a reliably imported environment as described above and dfu-util 0.11 or newer;
large-file support must also be verified with the actual host build and board.
Host tests cannot validate a different prebuilt U-Boot binary.

These are raw filesystem images, not files copied into an existing filesystem.
An ext4 image smaller than its partition does not automatically grow: expand it
later with `resize2fs` on the correctly identified Linux device. Update kernel/DT
loading, `root=` and `/etc/fstab` for the selected system slot (partition 1 or 2).
Fresh GPT UUIDs mean
old `PARTUUID` references must be updated. `--reset` retains the existing Ctrl+C-to-exit-DFU
behavior rather than providing unattended end-of-transfer reset.

This prepares A/B storage only: it does not implement active-slot selection,
boot-attempt counting, health checks, rollback or an update agent. U-Boot must
load the kernel/DT and select the root filesystem from the same slot. GPT names
(`PARTLABEL=rootfs_a` / `PARTLABEL=rootfs_b`) identify slots; filesystem labels
inside ext4 images are independent and are not changed by this tool. Avoid
ambiguous filesystem UUID/label references when cloning the same image into both
slots. Mount partition 3 separately for shared data and expand its filesystem if
needed. Normal A/B updates should write only the inactive slot and preserve the
data partition; do not use `--repartition-emmc` or the full factory-flash example
for routine upgrades, since both can destroy persistent data.

Host regression tests (no board or third-party Python packages required):

```bash
python3 -m unittest discover -s tests -v
```

### Flashing to eMMC

* Without `--repartition-emmc`, partition-mode flashing requires an existing
  partition table. The following is an alternative manual two-partition example.
  Older U-Boot builds may require a reset to refresh partition information;
  newer builds can refresh it after `gpt write` without a reset.
* The eMMC device typically ships without any partition table. Make use of the
  GPT support in U-Boot to write a GPT partition table to eMMC. In this case we
  need to use the uuidgen program on the host to create the UUIDs used for the
  disk and each partition.Enter below commands in Linux host to generate uuid

```
$ uuidgen
  first_uuid
$ uuidgen
  second_uuid
```

* Flash default wic image to SD Card. Boot the board using the SD Card. Press any
  key to enter the U-Boot prompt. Enter following commands in U-Boot prompt.

```
# setenv uuid_gpt_disk first_uuid
# setenv uuid_gpt_rootfs second_uuid
# gpt write <device num> ${partitions} (device num can be found using mmclist)
```

* After the eMMC is partitioned, you can now flash to eMMC without errors.
  (After doing all the pre-steps as mentioned in previous sections)
* In your config file put operation as --operation=flash-emmc. Run the script
  in Linux or Windows host.

_Note:For flashing filesystem use an ext4 file and name it as rootfs.ext4 and
 specify the path in cfg file._

### Flash to SPI NOR

* In your config file put operation as --operation=flash-nor.
* Do follow all the pre-steps as mentioned in previous sections for flashing.
* Run the script in Linux or Windows host.

### Flash to SPI NAND

* In your config file put operation as --operation=flash-nand.
* Do follow all the pre-steps as mentioned in previous sections for flashing.
* Run the script in Linux or Windows host.

_Note: Flash to QSPI NAND on AM62x is tested only on GP. User needs to change
 the boot binaries which supports QSPI NAND flashing on am62x. This is tested
 on AM62x GP and binaries for same can be found in <bin/am62xx-evm/gp/qspi_nand_binaries>._

[1]: https://www.python.org/downloads/
[2]: https://dfu-util.sourceforge.net/releases/
[3]: dfu-util.sourceforge.net/releases/dfu-util-0.9-win64.zip
[4]: https://zadig.akeo.ie/
