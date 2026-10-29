# Standard modules
import os
import shlex
import logging
from enum import Enum
from uuid import uuid4

# Custom modules
from src.constants import RESERVED_ALT_NAMES, FLASH_EMMC_ATTRS_REGEX

# Flash medias
class FLASH_MEDIA(Enum):
    NOR  = "NOR"
    EMMC = "EMMC"
    NAND = "NAND"
    GPMC_NAND = "GPMC_NAND"

# DFU start commands which are required to start the DFU interface
dfu_commands = {
    FLASH_MEDIA.NOR  : 'dfu 0 sf 0:0',
    FLASH_MEDIA.EMMC : 'dfu 0 mmc 0',
    FLASH_MEDIA.NAND : 'dfu 0 mtd spi-nand0',
    FLASH_MEDIA.GPMC_NAND : 'dfu 0 nand 0'
}

# Reset commands which when used reset the board to the respective media
reset_commands = {
    FLASH_MEDIA.NOR  : 'mw 0x43000030 0x273 0x1;reset;',
    FLASH_MEDIA.EMMC : 'mw 0x43000030 0xcb 0x1;reset;',
    FLASH_MEDIA.NAND : 'mw 0x43000030 0x03 0x1;reset;',
    FLASH_MEDIA.GPMC_NAND : 'mw 0x43000030 0x5b 0x1;reset;',
}

# Block sizes of the different media
block_size = {
    FLASH_MEDIA.NOR  : 0x1,
    FLASH_MEDIA.EMMC : 0x200,
    FLASH_MEDIA.NAND : 0x40000,
    FLASH_MEDIA.GPMC_NAND : 0x40000,
}

def get_repartition_env(dfu_conf):
    partition_images = {}
    for entry in dfu_conf.values():
        if entry["media"] is not FLASH_MEDIA.EMMC:
            raise ValueError("--repartition-emmc only supports flash-emmc")
        access, hwpart, partid = entry["attrs"].split(",")
        if access == "raw":
            if hwpart not in ("1", "2"):
                raise ValueError("Repartitioning only allows raw writes to Boot0/Boot1")
            continue
        if hwpart != "0" or partid not in ("1", "2", "3"):
            raise ValueError("Partition images must target part,0,1 through part,0,3")
        if partid in partition_images:
            raise ValueError(f"Multiple images target UDA partition {partid}")
        if int(entry["addr"], 16) != 0:
            raise ValueError("Partition images must use --flash-offset=0x0")
        size = os.path.getsize(entry["path"])
        if size == 0:
            raise ValueError(f"Partition {partid} image is empty")
        if partid in ("1", "2") and size > 2 * 1024 ** 3:
            raise ValueError(f"Partition {partid} image exceeds 2 GiB")
        partition_images[partid] = (size + 511) // 512

    if set(partition_images) != {"1", "2", "3"}:
        raise ValueError("Repartitioning requires one image for each UDA partition 1, 2, 3")

    layout = (
        f"uuid_disk={uuid4()};"
        f"name=rootfs_a,start=1MiB,size=2GiB,uuid={uuid4()};"
        f"name=rootfs_b,size=2GiB,uuid={uuid4()};"
        f"name=data,size=-,uuid={uuid4()}"
    )
    prepare = (
        "mmc dev 0 0 && mmc rescan && "
        "gpt write mmc 0 ${emmc_layout} && mmc rescan && "
        "gpt verify mmc 0 ${emmc_layout}"
    )
    checks = []
    for partid in ("1", "2", "3"):
        checks.extend([
            f"part size mmc 0 {partid} emmc_part_blocks",
            # 'part size' stores hexadecimal digits without a 0x prefix.
            f"test 0x${{emmc_part_blocks}} -ge {hex(partition_images[partid])}",
        ])
    return (
        f"emmc_layout={layout}\n"
        f"emmc_prepare={prepare}\n"
        f'emmc_check={" && ".join(checks)}\n'
    )


def get_command(dfu_conf, reset, repartition=False):
    alt = []

    for a, D in dfu_conf.items():
        # Unpack the different alt attributes
        path, addr, media, attrs = D["path"], D["addr"], D["media"], D["attrs"]

        # Everything has been validated before so direcly use
        size = os.path.getsize(path)
        addr = int(addr, 16)
        bs   = block_size[media]

        # Calculate number of blocks
        n_blocks = size // bs
        if size % bs: n_blocks += 1

        if media is FLASH_MEDIA.NOR:
            alt.append(f"{a} raw {hex(addr)} {hex(n_blocks * bs)}")
        elif media is FLASH_MEDIA.NAND:
            alt.append(f"{a} raw {hex(addr)} {hex(n_blocks * bs)}")
        elif media is FLASH_MEDIA.GPMC_NAND:
            alt.append(f"{a} raw {hex(addr)} {hex(n_blocks * bs)}")
        elif media is FLASH_MEDIA.EMMC:
            accesstype, hwpart, partid = attrs.split(",")

            if accesstype == "raw":
                alt.append(f"{a} raw {hex(addr // bs)} {hex(n_blocks)} mmcpart {hwpart}")
            else:
                alt.append(f"{a} {accesstype} {hwpart} {partid}")

    if media is FLASH_MEDIA.NAND:
        flash_command = f'mtd list;setenv dfu_alt_info "{";".join(alt)}"'
    else:
        flash_command = f'setenv dfu_alt_info "{";".join(alt)}"'
    
    dfu_command = dfu_commands[media]
    reset_command = reset_commands[media] if reset else ""

    command = ";".join([flash_command, dfu_command, reset_command])
    writes_boot0 = any(
        entry["media"] is FLASH_MEDIA.EMMC and entry["attrs"] == "raw,1,-"
        for entry in dfu_conf.values()
    )
    if writes_boot0:
        command = (
            "if mmc dev 0 0 && mmc partconf 0 1 1 1 && "
            "mmc bootbus 0 2 0 0 && mmc dev 0 0; then "
            f"{command}"
            "else echo ERROR: eMMC Boot0 configuration failed; fi;"
        )
    if repartition:
        command = (
            "if run emmc_prepare && run emmc_check; then "
            f"{command}"
            "else echo ERROR: eMMC partition setup or image capacity check failed; fi"
        )
    return command

def parse_to_dict(config_string):
    config_dict = dict()
    splitter = shlex.shlex(config_string, posix=True)
    splitter.commenters="#"
    splitter.whitespace = ' '
    splitter.whitespace_split = True

    for key_value_pair in splitter:
        kv = key_value_pair.strip()
        if not kv:
            continue
        kv_t = kv.split('=', 1)
        if(len(kv_t)==1):
            #error, no value
            pass
        else:
            config_dict[kv_t[0]] = kv_t[1]

    return config_dict

def parse_operation(operation):
    if operation == "flash-nor":
        return FLASH_MEDIA.NOR

    if operation == "flash-nand":
        return FLASH_MEDIA.NAND
    
    if operation == "flash-emmc":
        return FLASH_MEDIA.EMMC
    
    if operation == "flash-gpmc_nand":
        return FLASH_MEDIA.GPMC_NAND

    # If none of the above return None
    return None

def parse_and_validate_cfg_line(cfg_line, idx):
    # Parse the config line in accordance to the syntax rules
    cfg_line_dict = parse_to_dict(cfg_line)
    
    # If dict is empty, return empty dict. This can be due to
    # - A blank line
    # - A comment line
    # - A line having no `<key>=<value>` pair
    if len(cfg_line_dict) == 0: return cfg_line_dict

    # Try to report as many errors as possible.
    # This gives a chance to rectify most errors in one go.

    # If KeyError return None
    path  = cfg_line_dict.get("--file",         None)
    oprn  = cfg_line_dict.get("--operation",    None)
    addr  = cfg_line_dict.get("--flash-offset", None)
    attrs = cfg_line_dict.get("--attributes",   None)

    # Parse the operation
    media = parse_operation(oprn)

    # Variable to track if an error occured
    is_error = False

    if path is None:
        logging.error(f"#Line {idx + 1}# Key `--file` not found!!")
        is_error = True
    else:
        # Check if the path exists
        if not os.path.exists(path):
            logging.error(f"#Line {idx + 1}# File {{{path}}} not found!!")
            is_error = True

    if oprn is None:
        logging.error(f"#Line {idx + 1}# Key `--operation` not found!!")
        is_error = True
    else:
        # Check if operation is correct
        if not media:
            logging.error(f"#Line {idx + 1}# Operation `{oprn}` not supported!!")
            is_error = True

    if addr is None:
        logging.error(f"#Line {idx + 1}# Key `--flash-offset` not found!!")
        is_error = True
    else:
        # Check if address is a valid hexadecimal address and a multiple of the block size
        try:
            _ = int(addr, 16)
            if media and (_ % block_size[media] != 0):
                logging.error(f"#Line {idx + 1}# Address `{addr}` is not a multiple of the "
                              f"{media.value} block size of `{hex(block_size[media])}`!!")
                is_error = True
        except ValueError as e:
            logging.error(f"#Line {idx + 1}# Address `{addr}` is not a valid hexadecimal address!!")
            is_error = True

    if media == FLASH_MEDIA.EMMC:
        # If key `--attributes` not found or value not valid, log warning and set to default
        if attrs is None:
            logging.warn(f"#Line {idx + 1}# Setting `--attributes=raw,1,-` as key `--attributes` not found!")
            attrs = "raw,1,-"
        elif not FLASH_EMMC_ATTRS_REGEX.match(attrs):
            logging.warn(f"#Line {idx + 1}# Setting `--attributes=raw,1,-` as value `{attrs}` of key"
                         "`--attributes` not valid!")
            attrs = "raw,1,-"
    else:
        attrs = None

    # Return None if any errors
    if is_error is True: return None
    
    # Everything is in place
    return { "path": path, "media": media, "addr": addr, "attrs": attrs }

def parse_cfg_file(cfg_file):
    dfu_conf = dict()
    cnt = 0

    prev_media = None
    is_error = False

    with open(cfg_file, 'r', encoding='utf-8') as f:
        for idx, cfg_line in enumerate(f.readlines()):
            # Parse and validate the config line
            cfg_dict = parse_and_validate_cfg_line(cfg_line, idx)
            
            # If None, some errors occured
            if cfg_dict is None: is_error = True; continue

            # If length is zero, no errors so continue and go to next line
            if len(cfg_dict) == 0: continue

            # Check if current operation is different from the previous operations
            if prev_media and cfg_dict["media"] != prev_media:
                logging.error(f"#Line {idx + 1}# Operation is different than the previous operations!!")
                exit(1)
            else:
                prev_media = cfg_dict["media"]

            # Derive the alt from the basename of the file
            a = os.path.basename(cfg_dict['path'])
            a = a.split('.')[0][:25]

            # If alt is duplicate, create an unique alt by appending an unique incremental value
            if a in dfu_conf or a in RESERVED_ALT_NAMES:
                a = f'{a}.{cnt}'
                cnt += 1

            # Save the validated config line keyed by alt
            dfu_conf[a] = cfg_dict

    # Exit if any errors
    if is_error is True:
        logging.info("Please rectify the errors to proceed with flashing...")
        exit(1)
    
    # Everything is in place
    return dfu_conf
