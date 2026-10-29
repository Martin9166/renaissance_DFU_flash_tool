## How to Run the Benchmark Script

The benchmark script can be run using the following commands
```bash
cd ${PROJECT_DIR_PATH}/benchmark
${PYTHON} ./benchmark.py ${LOG_FILE}
```

A sample flash log file is added in the benchmark folder. The benchmarking for it can be done using
```bash
${PYTHON} ./benchmark.py ./sample-flash-logs.log
```

## The Benchmarking Script

The benchmarking script is designed to do the benchmarking solely by parsing the captured flash logs. It is thus made independent of the flashing procedure. This design is mainly for the following reasons:

- Avoid complicating the flashing tool scripts.
- Flexibility in benchmarking.
- Benchmarking any time by flashing and saving the logs.
- Compare the benchmarkings of different flashings done at different times.
- Modify the benchmarking script as needed to extract more granular information from flashing logs if needed.

## The Benchmarking Process

The benchmarking process follows the below steps:

- Parse the flash logs and extract the heredoc `DFU_FLASH_CONF` & `DFU_BOOT_CONF`.
- Parse these heredoc and extract the path and size of the binaries sent during the flashing procedure.
- Remove the heredoc `DFU_FLASH_CONF` & `DFU_BOOT_CONF` from the flash logs.
- Split the flash logs, which may contain parallel flashing logs in case of multiple devices, into single device flash logs as if the multiple devices were connected separately to different hosts, starting the flashing at the same point, and capturing the logs separately on each host.
- For each single device logs:
  - Divide each event log into an action of either `BOOT`, `FLASH`, or `OTHER`. An event log containing `Sent!` is categorised as `BOOT` or `FLASH` action while any other log is categorised as `OTHER` action. As an example:
    ```
    2023-08-29 17:13:21 INFO: Starting the flashing tool                                                                              |
    2023-08-29 17:13:21 INFO: Validating the requirements before flashing...                                                          |
    2023-08-29 17:13:21 INFO: Validated the CLI arguments and the paths to the DFU boot binaries                                      |
    2023-08-29 17:13:21 INFO: Parsing the flash configuration file {C:\ti\uboot-flash-writer\bin\am62xx-evm\hsfs\flash-files.cfg}...  |
    2023-08-29 17:13:21 INFO: Found 4 flash images                                                                                    | -> ACTION `OTHER`
    2023-08-29 17:13:21 INFO: Found 4 boot images                                                                                     |
    2023-08-29 17:13:21 INFO: Number of USB DFU devices detected: 1                                                                   |
    2023-08-29 17:13:21 INFO: Starting flashing for 1 identified devices                                                              |
    2023-08-29 17:13:21 INFO: Spawning 1 parallel processes                                                                           |
    2023-08-29 17:13:23 INFO:           1-3.2 Sent! C:\ti\uboot-flash-writer\bin\am62xx-evm\hsfs\tiboot3.bin  |
    2023-08-29 17:13:25 INFO:           1-3.2 Sent! C:\ti\uboot-flash-writer\bin\am62xx-evm\hsfs\tispl.bin    | -> ACTION `BOOT`
    2023-08-29 17:13:28 INFO:           1-3.2 Sent! C:\ti\uboot-flash-writer\bin\am62xx-evm\hsfs\u-boot.img   |
    2023-08-29 17:13:33 INFO:           1-3.2 Sent! C:\ti\uboot-flash-writer\bin\am62xx-evm\hsfs\uEnv.txt     |
    2023-08-29 17:13:35 INFO:           1-3.2 Sent! bin\am62xx-evm\hsfs\images\tiboot3.bin     |
    2023-08-29 17:13:36 INFO:           1-3.2 Sent! bin\am62xx-evm\hsfs\images\tispl.bin       | -> ACTION `FLASH`
    2023-08-29 17:13:38 INFO:           1-3.2 Sent! bin\am62xx-evm\hsfs\images\u-boot.img      |
    2023-08-29 17:15:08 INFO:           1-3.2 Sent! bin\am62xx-evm\hsfs\images\rootfs.img      |
    2023-08-29 17:15:08 INFO:           1-3.2 Flashing Successful...                       | -> ACTION `OTHER`
    2023-08-29 17:15:08 INFO: Flashed 1 out of 1 identified devices successfully...  |
    2023-08-29 17:15:11 INFO: Exiting!!!                                             | -> IGNORED
    ```
  - Calculate the bytes sent and the time taken for each of the actions.
- Calculate the average bytes sent and the average time taken for each of the action using
  ```
  ACTION_AVERAGE_BYTES_SENT = SUM(ACTION_BYTES_SENT_FOR_EACH_DEVICE) / (Number of successfully flashed devices)
  ACTION_AVERAGE_TIME_TAKEN = SUM(ACTION_TIME_TAKEN_FOR_EACH_DEVIE)  / (Number of successfully flashed devices)
  ACTION_AVERAGE_SPEED      = ACTION_AVERAGE_BYTES_SENT / ACTION_AVERAGE_TIME_TAKEN
  ```
- Calculate the overall benchmarking numbers using:
  ```
  AVERAGE_BYTES_SENT = SUM(ACTION_AVERAGE_BYTES_SENT)
  AVERAGE_TIME_TAKEN = SUM(ACTION_AVERAGE_TIME_TAKEN)
  AVERAGE_SPEED      = AVERAGE_BYTES_SENT / AVERAGE_TIME_TAKEN
  ```
- Dump the calculated numbers on the terminal.
