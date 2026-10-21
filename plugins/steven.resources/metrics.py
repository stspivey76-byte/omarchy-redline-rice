import json
import math
import shutil
import time
from pathlib import Path


def sample():
    cpu = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
    mem = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    rx = tx = 0
    for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
        name, data = line.split(':')
        if name.strip() != 'lo':
            fields = data.split()
            rx += int(fields[0])
            tx += int(fields[8])
    return sum(cpu[:8]), cpu[3] + cpu[4], mem, rx, tx


def traffic_level(rate):
    # Log scale: small transfers remain visible; full scale is 12.5 MB/s.
    return min(1, math.log1p(rate / 1024) / math.log1p(12500000 / 1024))


previous = sample()
last = time.monotonic()
while True:
    time.sleep(1)
    current = sample()
    now = time.monotonic()
    elapsed = max(0.001, now - last)
    total = current[0] - previous[0]
    disk = shutil.disk_usage(str(Path.home()))
    levels = [1 - (current[1] - previous[1]) / max(1, total),
              1 - current[2]['MemAvailable'] / current[2]['MemTotal'],
              disk.used / disk.total]
    rx = max(0, current[3] - previous[3]) / elapsed
    tx = max(0, current[4] - previous[4]) / elapsed
    print(json.dumps({'levels': [max(0, min(1, n)) for n in levels],
                      'download': traffic_level(rx), 'upload': traffic_level(tx),
                      'rx': rx, 'tx': tx}), flush=True)
    previous, last = current, now
