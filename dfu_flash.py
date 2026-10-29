# Standard modules
import argparse
import os
import logging

# Custom modules
import src.logger
from src.flash import dfu_main
from src.parse import parse_cfg_file, get_command, get_repartition_env
from src.helper import dump_dfu_flash_conf, dump_dfu_boot_conf
from src.constants import BIN_DIR_PATH, FLASH_CFG_FILE_NAME, UENV_TEMPLATE

def main():
    # Define the argument parser
    args_parser = argparse.ArgumentParser()

    # Argument to identify the device
    args_parser.add_argument("-d",
                             "--device",
                             required=True,
                             help="Specify the device",)

    # Argument to identify the type of the device
    args_parser.add_argument("-t",
                             "--type",
                             required=True,
                             choices=["gp", "hsfs", "hs"],
                             help="Type of the device",)

    # Argument to get the path of the custom configuration file
    args_parser.add_argument("-c",
                             "--cfg",
                             help="Path to the flashing configuration file",)

    # Argument to reset the board after flashing
    args_parser.add_argument("-r",
                             "--reset",
                             action="store_true",
                             help="Reset the board to the flashed media",)

    args_parser.add_argument("--repartition-emmc",
                             action="store_true",
                             help="DESTROY existing eMMC UDA layout: create rootfs_a "
                                  "(2 GiB), rootfs_b (2 GiB), data (remaining space)",)
    args_parser.add_argument("--dry-run",
                             action="store_true",
                             help="Validate configuration and generate uEnv.txt without USB transfers",)

    # Parse the CLI arguments
    args = args_parser.parse_args()
    cli_args = {
        "device": args.device,
        "type"  : args.type,
        "cfg"   : args.cfg,
        "reset" : args.reset
    }

    # Validate the CLI arguments
    logging.info("Starting the flashing tool")
    logging.info("Validating the requirements before flashing...")

    # Path to the device directory
    DEVICE_PATH = BIN_DIR_PATH / cli_args["device"] / cli_args["type"]

    # Check if device path exists
    if not os.path.exists(DEVICE_PATH):
        logging.error(f"The device path {{{DEVICE_PATH}}} does not exist!!!")
        exit(1)

    # Path to the flash configuration file
    cfg_file = cli_args["cfg"]

    # If custom flash configuration file not given, use the default one
    if not cfg_file:
        cfg_file = DEVICE_PATH / FLASH_CFG_FILE_NAME

    if not os.path.exists(cfg_file):
        logging.error(f"The flash configuration file {{{cfg_file}}} does not exist!!!")
        exit(1)

    # Path to the DFU boot images
    dfu_tiboot3 = DEVICE_PATH / "tiboot3.bin"
    dfu_tispl   = DEVICE_PATH / "tispl.bin"
    dfu_uboot   = DEVICE_PATH / "u-boot.img"

    for path in [dfu_tiboot3, dfu_tispl, dfu_uboot]:
        if not os.path.exists(path):
            logging.error(f"The DFU boot binary {{{path}}} does not exist!!!")
            exit(1)

    logging.info("Validated the CLI arguments and the paths to the DFU boot binaries")
    logging.info(f"Parsing the flash configuration file {{{cfg_file}}}...")
        
    # Parse the flash configuration file
    dfu_flash_conf = parse_cfg_file(cfg_file)

    if not dfu_flash_conf:
        logging.error("Could not found any images to flash...")
        exit(1)

    repartition_env = ""
    if args.repartition_emmc:
        try:
            repartition_env = get_repartition_env(dfu_flash_conf)
        except ValueError as error:
            logging.error("%s", error)
            raise SystemExit(1)
        logging.warning("DESTRUCTIVE: every detected board will have eMMC 0 UDA "
                        "repartitioned and its existing data overwritten")

    # Get the DFU command
    command = get_command(dfu_flash_conf, cli_args["reset"], args.repartition_emmc)

    # Print the DFU flash configuration
    dump_dfu_flash_conf(dfu_flash_conf)

    # Path to the U-Boot environment file
    uEnv_path = DEVICE_PATH / "uEnv.txt"

    # Write the DFU command to U-Boot Environment file
    with open(uEnv_path, 'w', newline='\n') as f:
        f.write(repartition_env + UENV_TEMPLATE.format(command) + "\0")

    dfu_boot_conf = {
        "bootloader" : dfu_tiboot3,
        "tispl.bin"  : dfu_tispl,
        "u-boot.img" : dfu_uboot,
        "uEnv.txt"   : uEnv_path,
    }

    # Print the DFU boot configuration
    dump_dfu_boot_conf(dfu_boot_conf)

    if args.dry_run:
        logging.info("Dry run: generated {%s}; no USB transfers performed", uEnv_path)
        return

    # Start the DFU main function
    dfu_main(dfu_flash_conf, cli_args)

if __name__ == '__main__':
    main()
