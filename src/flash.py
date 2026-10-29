# Standard modules
import time
import logging
import subprocess
from multiprocessing import Process, Value

# Custom Modules
from src.constants import DFU_UTIL_PATH, DFU_SOCID_REG_EXP, BIN_DIR_PATH

def wait_for_dfu_enumeration(path, name, iterations=25):
    for _ in range(iterations):
        output = subprocess.check_output([DFU_UTIL_PATH, "-p", path, "-a", name, "-l"], stderr=subprocess.DEVNULL, text=True)

        if f'name="{name}"' in output:
            return True

        # Check the status after 1 second
        time.sleep(1)

    return False

def detect_devices():
    paths = []

    while not paths:
        # Enumerate the DFU devices
        output = subprocess.check_output([DFU_UTIL_PATH, "-a", "SocId", "-l"], stderr=subprocess.DEVNULL)

        # Pick all paths
        paths = DFU_SOCID_REG_EXP.findall(output.decode())

    return paths

def dfu_download(path, a, D, extra_args=[]):
    # Wait for the DFU interface to appear
    status = wait_for_dfu_enumeration(path, name=a)

    if not status:
        logging.error(f"{path:>15} Aborting!! Max iterations reached. DFU device not listening for `{a}`")
        return False

    # Run the DFU command to send the binary
    ps = subprocess.run([DFU_UTIL_PATH, "-p", path, *extra_args, "-a", a, "-D", D], capture_output=True)
    out, err = ps.stdout, ps.stderr

    # Simple approach to confirm the binary is sent fully
    if ps.returncode == 0 and b"100%" in out:
        logging.info(f"{path:>15} Sent! {D}")
        status = True
    else:
        err_s = f"<<DFU_ERROR_LOGS\n{out.decode()}\n{err.decode()}\nDFU_ERROR_LOGS"
        logging.error(f"{path:>15} Error! {D}\n{err_s}")
        status = False

    return status

def dfu_start(path, dfu_conf, cli_args, ret):
    DEVICE_PATH = BIN_DIR_PATH / cli_args["device"] / cli_args["type"]

    # Path to the DFU boot images
    dfu_tiboot3 = DEVICE_PATH / "tiboot3.bin"
    dfu_tispl   = DEVICE_PATH / "tispl.bin"
    dfu_uboot   = DEVICE_PATH / "u-boot.img"

    # Path to the U-Boot environment file
    uEnv_path = DEVICE_PATH / "uEnv.txt"

    status = True

    status = status and dfu_download(path, "bootloader", dfu_tiboot3)
    
    # The AM64x R5 SPL (tiboot3.bin) does a warm reset on booting, so send the R5 SPL again
    if "am64" in cli_args["device"]:
        status = status and dfu_download(path, "bootloader", dfu_tiboot3)
        
    status = status and dfu_download(path, "tispl.bin",  dfu_tispl, ["-R"])
    status = status and dfu_download(path, "u-boot.img", dfu_uboot, ["-R"])
    status = status and dfu_download(path, "uEnv.txt",   uEnv_path, ["-R"])

    for a, D in dfu_conf.items():
        D = D["path"]
        status = status and dfu_download(path, a, D)

    if status:
        logging.info(f"{path:>15} Flashing Successful...")

        if cli_args["reset"]:
            logging.info(f"{path:>15} Press Ctrl + C on the serial terminal to reset the board...")

        # Flashing successful
        ret.value = True

def dfu_main(dfu_conf, cli_args):
    try:
        while True:
            # Detect the devices
            enumerated_paths = detect_devices()
            cnt = len(enumerated_paths)

            logging.info(f"Number of USB DFU devices detected: {cnt}")

            logging.info(f"Starting flashing for {cnt} identified devices")
            logging.info(f"Spawning {cnt} parallel processes")

            # List of processes
            processes = []

            for path in enumerated_paths:
                # Status variable
                ret = Value('b', False)

                p = Process(target=dfu_start, args=(path, dfu_conf, cli_args, ret))
                processes.append([p, ret])
                p.start()

            for p, ret in processes:
                p.join()

                if not ret.value:
                    cnt -= 1

            logging.info(f"Flashed {cnt} out of {len(enumerated_paths)} identified devices successfully...")
    except KeyboardInterrupt:
        logging.info("Exiting!!!")
        exit(1)
