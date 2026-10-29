import os
import logging

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

def dump_dfu_flash_conf(dfu_flash_conf):
    # Headers and rows of the table
    headers = ["Alt", "Path", "Size", "Offset", "Media", "Attributes"]
    rows = []

    for a, D in dfu_flash_conf.items():
        rows.append([f'{a}',
                     f'{D["path"]}',
                     f'{os.path.getsize(D["path"])}',
                     f'{D["addr"]}',
                     f'{D["media"].value}',
                     f'{D["attrs"]}'])
    
    # Get the formatted string
    t = pretty_print(headers, rows, alignments=["r", "l", "r", "r", "l", "l"])

    logging.info(f"Found {len(dfu_flash_conf)} flash images\n<<DFU_FLASH_CONF\n{t}\nDFU_FLASH_CONF")

def dump_dfu_boot_conf(dfu_boot_conf):
    # Headers and rows of the table
    headers = ["Alt", "Path", "Size"]
    rows = []

    for a, D in dfu_boot_conf.items():
        rows.append([f'{a}',
                     f'{D}',
                     f'{os.path.getsize(D)}'])

    t = pretty_print(headers, rows, alignments=["r", "l", "r"])
    
    logging.info(f"Found {len(dfu_boot_conf)} boot images\n<<DFU_BOOT_CONF\n{t}\nDFU_BOOT_CONF")
