import re
import os
from pathlib import Path

# Template for the U-Boot Environment File
UENV_TEMPLATE = \
"""
user_commands={}
""".lstrip()

DFU_SOCID_REG_EXP = r'Found DFU:.*path="(.*)".*name="SocId"'
DFU_SOCID_REG_EXP = re.compile(DFU_SOCID_REG_EXP)

DEV_TYPE_REG_EXP  = r'(am64x|am62x|am62a).*(GP|HSFS|HS)'.encode()
DEV_TYPE_REG_EXP  = re.compile(DEV_TYPE_REG_EXP)

# Get the root directory of this project
PROJECT_DIR_PATH = Path(__file__).parent.parent

# Logs directory
LOGS_DIR_PATH = PROJECT_DIR_PATH / "logs"
if not os.path.exists(LOGS_DIR_PATH): os.makedirs(LOGS_DIR_PATH)

# Directory containing different binaries
BIN_DIR_PATH = PROJECT_DIR_PATH / "bin"

# Path of the dfu-util
DFU_UTIL_PATH = "dfu-util"

# Default flash configuration file name
FLASH_CFG_FILE_NAME = "flash-files.cfg"

# Reserved alt names
RESERVED_ALT_NAMES = ["SocId", "bootloader", "tispl.bin", "u-boot.img", "uEnv.txt"]

# ## eMMC flash attributes: <raw|part>,<hwpart>,<partid>
# ### `raw|part`
# - Use `raw` for raw flashing to any offset of any hardware partition in eMMC. If `raw`
#   is used, only `hwpart` is required and the third parameter `partid` should be set to `-`.
# - Use `part` for raw flashing to a partition defined in GPT or DOS partition table. If `part`
#   is used, both `hwpart` & `partid` are required.
# - It should be noted using `part` requires a partition table already in the respective
#   hardware partition in eMMC.
#
# ### `hwpart`
# - `hwpart` defines the hardware partition index in eMMC. The mapping is usually the following
#   | Partition | Index |
#   | --------- | ----- |
#   | Boot0     | 1     |
#   | Boot1     | 2     |
#   | UDA       | 0     |
#
# ### `partid`
# - `partid` defines the partition index in the GPT or DOS partition table. For `raw` flashing,
#   it should be set to `-`. For `partid` flashing, it should be set to the partition index.

FLASH_EMMC_ATTRS_REGEX = r"(raw|part),(\d+?|-),(\d+?|-)$"
FLASH_EMMC_ATTRS_REGEX = re.compile(FLASH_EMMC_ATTRS_REGEX)
