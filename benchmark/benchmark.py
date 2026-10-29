import re
import sys
from enum import Enum
from datetime import datetime
from collections import defaultdict

# Enum defining the different actions
class Action(Enum):
    BOOT  = "BOOT"
    FLASH = "FLASH"
    OTHER = "OTHER"

# Regular expression to match the single lines of the logs
LOG_REGEX = r".*?\s(?P<ts>.*?)\s.*?\s(?P<msg>.*)"
LOG_REGEX = re.compile(LOG_REGEX)

# Regular expression to match the message
DEV_MSG_REGEX = r"\s+(?P<dpath>.*?)\s.*?\s(?P<fpath>.*)"
DEV_MSG_REGEX = re.compile(DEV_MSG_REGEX)

# Regular expression to match the DFU_FLASH_CONF
DFU_FLASH_CONF_REGEX = r"<<DFU_FLASH_CONF(\n.*)*\DFU_FLASH_CONF\n"
DFU_FLASH_CONF_REGEX = re.compile(DFU_FLASH_CONF_REGEX)

# Regular expression to match the DFU_BOOT_CONF
DFU_BOOT_CONF_REGEX = r"<<DFU_BOOT_CONF(\n.*)*\DFU_BOOT_CONF\n"
DFU_BOOT_CONF_REGEX = re.compile(DFU_BOOT_CONF_REGEX)

# Regular expression to match the DFU_ERROR_LOGS
DFU_ERROR_LOGS_REGEX = r"<<DFU_ERROR_LOGS(\n.*?)*\DFU_ERROR_LOGS\n"
DFU_ERROR_LOGS_REGEX = re.compile(DFU_ERROR_LOGS_REGEX)

# Regular expression to extract path and size from DFU configurations
DFU_CONF_LINE_REGEX = r"^\s*?[^\s]+?\s+?(?P<path>[^\s]+?)\s+?(?P<size>\d+)"
DFU_CONF_LINE_REGEX = re.compile(DFU_CONF_LINE_REGEX)

def pretty_print(headers, rows, alignments=None):
    if not alignments:
        alignments = ["c"] * len(headers)
    
    # List containing the maximum width for each column
    max_cols_width = [max(map(lambda x: len(x), row))
                      for row in zip(headers, *rows)]
    
    # Lambda function to pad the string with required spaces
    pad_str = lambda s, w, a: s.ljust(w)  if a == "l" else \
                              s.rjust(w)  if a == "r" else \
                              s.center(w)

    # Format the headers
    for i in range(len(headers)):
        headers[i] = pad_str(headers[i], max_cols_width[i], alignments[i])
    
    # Format the rows
    for r in range(len(rows)):
        for c in range(len(rows[0])):
            rows[r][c] = pad_str(rows[r][c], max_cols_width[c], alignments[c])
    
    # Divider to divide the header and the rest of the rows
    divider = ['-' * col_width for col_width in max_cols_width]
    
    # Generate the formatted string
    formatted_str = "\n".join(" ".join(row)
                              for row in [divider, headers, divider, *rows, divider])

    return formatted_str

def parse_dfu_conf(full_logs, heredoc):
    if heredoc == "DFU_FLASH_CONF":
        DFU_CONF_REGEX = DFU_FLASH_CONF_REGEX
        action = Action.FLASH
    else:
        DFU_CONF_REGEX = DFU_BOOT_CONF_REGEX
        action = Action.BOOT

    match = DFU_CONF_REGEX.search(full_logs)
    dfu_conf_str = match.group()

    print(f"Found DFU {action.value.lower()} configurations...\n{dfu_conf_str}")

    dfu_conf = dict()

    for line in dfu_conf_str.split('\n'):
        match = DFU_CONF_LINE_REGEX.search(line)
        if not match: continue

        match = match.groupdict()

        # Get the path and the size
        path = match["path"]
        size = int(match["size"])

        # Save the extracted info
        dfu_conf[path] = { "size": size, "action": action }

    return dfu_conf

def split_logs(full_logs):
    # Capture main process logs
    main_proc_pre_logs  = ""
    main_proc_post_logs = ""

    # Store device logs keyed by its USB path
    device_logs = defaultdict(str)

    for log in full_logs.split('\n'):
        # Extract message
        match = LOG_REGEX.match(log).groupdict()
        msg   = match["msg"]
        
        match = DEV_MSG_REGEX.match(msg)

        if match:
            dpath = match.groupdict()["dpath"]
            device_logs[dpath] += f"{log}\n"
        else:
            if not device_logs:
                main_proc_pre_logs += f"{log}\n"
            else:
                main_proc_post_logs += f"{log}\n"

    # Ignore the post logs
    for dpath in device_logs:
        device_logs[dpath] = f"{main_proc_pre_logs}{device_logs[dpath]}".strip()

    return device_logs

def extract_data_from_device_logs(logs, dfu_conf):
    prev_ts = None
    extracted_data = []

    for log in logs.split('\n'):
        match = LOG_REGEX.match(log).groupdict()
        ts    = match["ts"]
        msg   = match["msg"]

        ts = datetime.strptime(ts, "%H:%M:%S")
        if prev_ts is None: prev_ts = ts

        tm = (ts - prev_ts).total_seconds()
        prev_ts = ts

        if "Sent!" in msg:
            match = DEV_MSG_REGEX.match(msg).groupdict()
            path  = match["fpath"]

            sz     = dfu_conf[path]["size"]
            action = dfu_conf[path]["action"]
        else:
            sz = 0
            action = Action.OTHER

        extracted_data.append([action, sz, tm])

    return extracted_data

def calculate_and_format_parameters(sz, tm):
    if sz:
        sz = (sz / 1024) / 1024
        sp = sz / tm

        sz = f"{sz:.2f}"
        sp = f"{sp:.2f}"
        tm = f"{tm:.2f}"
    else:
        sz = "-"
        sp = "-"
        tm = f"{tm:.2f}"

    return sz, tm, sp

if __name__ == "__main__":
    # Log file
    LOG_FILE = sys.argv[1]

    # Read the logs
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        full_logs = f.read()

    # Get the DFU configurations
    dfu_flash_conf = parse_dfu_conf(full_logs, "DFU_FLASH_CONF")
    dfu_boot_conf  = parse_dfu_conf(full_logs, "DFU_BOOT_CONF")

    # Remove the DFU configurations from the logs
    full_logs = DFU_FLASH_CONF_REGEX.sub('', full_logs)
    full_logs = DFU_BOOT_CONF_REGEX.sub('', full_logs)

    # Remove the DFU error logs
    full_logs = DFU_ERROR_LOGS_REGEX.sub('', full_logs)

    # Merge both configurations into one
    dfu_conf = dfu_flash_conf | dfu_boot_conf

    split_device_logs = split_logs(full_logs)
    extracted_data = dict()
    
    # Rows to capture the flashing status
    rows = []
    
    for dpath, device_logs in split_device_logs.items():
        if 'ERROR' not in device_logs:
            # Extract the data from the device logs
            extracted_data[dpath] = extract_data_from_device_logs(device_logs, dfu_conf)
            rows.append([dpath, "DONE"])
        else:
            rows.append([dpath, "FAIL"])

    print(f"Total number of devices: {len(split_device_logs)}")
    
    cnt = len(extracted_data)
    print(f"Number of successfully flashed devices: {cnt}")

    # Print the each device's flashing status
    headers = ["USB Path", "Flashing Status"]
    t = pretty_print(headers, rows, alignments=["r", "c"])

    print(f"\n{t}\n")

    # If no successfully flashed devices then exit
    if not cnt: exit(1)

    # Benchmarking numbers for different actions
    benchmark_numbers = {
        Action.OTHER: { "tm": 0, "sz": 0 },
        Action.FLASH: { "tm": 0, "sz": 0 },
        Action.BOOT : { "tm": 0, "sz": 0 },
    }

    for dpath in extracted_data:
        for action, sz, tm in extracted_data[dpath]:
            benchmark_numbers[action]["sz"] += sz
            benchmark_numbers[action]["tm"] += tm

    for action in benchmark_numbers:
        benchmark_numbers[action]["sz"] = benchmark_numbers[action]["sz"] / cnt
        benchmark_numbers[action]["tm"] = benchmark_numbers[action]["tm"] / cnt

    # Print the detailed numbers
    headers = ["Action", "Average Data Sent (in MB)", "Average Time Taken (in S)", "Average Speed (in MB/S)"]
    rows = []

    for action, numbers in benchmark_numbers.items():
        sz = benchmark_numbers[action]['sz']
        tm = benchmark_numbers[action]['tm']
        
        sz, tm, sp = calculate_and_format_parameters(sz, tm)
        
        rows.append([f"{action.value}", f"{sz}", f"{tm}", f"{sp}"])

    t = pretty_print(headers, rows)
    print(f"<<DETAILED_BENCHMARK_NUMBERS\n{t}\nDETAILED_BENCHMARK_NUMBERS\n")
    
    # Print the overall numbers
    sz, tm = 0, 0

    for action, numbers in benchmark_numbers.items():
        sz += benchmark_numbers[action]["sz"]
        tm += benchmark_numbers[action]["tm"]
    
    sz, tm, sp = calculate_and_format_parameters(sz, tm)

    headers = ["Average Data Sent (in MB)", "Average Time Taken (in S)", "Average Speed (in MB/S)"]
    rows = [[f'{sz}', f'{tm}', f'{sp}']]

    t = pretty_print(headers, rows)
    print(f"<<OVERALL_BENCHMARK_NUMBERS\n{t}\nOVERALL_BENCHMARK_NUMBERS\n")
