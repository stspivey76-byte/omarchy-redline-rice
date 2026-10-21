#!/usr/bin/python3
"""Stream playback spectrum to the taskbar; capture only an output monitor."""
import array
import cmath
import json
import math
import os
import select
import signal
import subprocess
import time

SIZE, RATE, BANDS = 1024, 24000, 20
WINDOW = [0.5 - 0.5 * math.cos(2 * math.pi * i / (SIZE - 1)) for i in range(SIZE)]
EDGES = [max(1, round(40 * (10000 / 40) ** (i / BANDS) * SIZE / RATE)) for i in range(BANDS + 1)]
TWIDDLES = {n: [cmath.exp(-2j * math.pi * k / n) for k in range(n // 2)] for n in [2 ** p for p in range(1, 11)]}
ORDER = [int(f'{i:010b}'[::-1], 2) for i in range(SIZE)]

def spectrum(samples):
    if max(map(abs, samples), default=0) < 0.000001:
        return [0.0] * BANDS
    data = [complex(samples[i] * WINDOW[i]) for i in ORDER]
    width = 2
    while width <= SIZE:
        half = width // 2
        for start in range(0, SIZE, width):
            for k, twiddle in enumerate(TWIDDLES[width]):
                a, b = data[start + k], data[start + k + half] * twiddle
                data[start + k], data[start + k + half] = a + b, a - b
        width *= 2
    result = []
    for i in range(BANDS):
        lo, hi = EDGES[i], max(EDGES[i] + 1, EDGES[i + 1])
        amplitude = max(abs(data[k]) for k in range(lo, min(hi, SIZE // 2))) * 4 / SIZE
        db = 20 * math.log10(max(amplitude, 1e-9))
        result.append(max(0.0, min(1.0, (db + 65) / 57)))
    return result

def default_sink():
    try:
        return subprocess.check_output(['pactl', 'get-default-sink'], text=True, timeout=2).strip()
    except (OSError, subprocess.SubprocessError):
        return ''

def stop_capture(capture):
    if capture:
        capture.terminate()
        try:
            capture.wait(timeout=1)
        except subprocess.TimeoutExpired:
            capture.kill(); capture.wait()

def main():
    capture, sink, buffer = None, '', b''
    levels = [0.0] * BANDS
    check_at = 0
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        while True:
            if time.monotonic() >= check_at:
                current = default_sink()
                check_at = time.monotonic() + 3
                if current != sink or capture is None or capture.poll() is not None:
                    stop_capture(capture)
                    capture, sink, buffer = None, current, b''
                    if sink:
                        capture = subprocess.Popen(['parec', '--device=' + sink + '.monitor', '--format=float32le', '--rate=' + str(RATE), '--channels=1', '--latency-msec=45', '--client-name=Taskbar Spectrum', '--stream-name=Playback spectrum'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if capture and capture.poll() is None:
                if not select.select([capture.stdout], [], [], 0.2)[0]:
                    continue
                chunk = os.read(capture.stdout.fileno(), SIZE * 4)
                if not chunk:
                    continue
                buffer += chunk
                if len(buffer) < SIZE * 4:
                    continue
                samples = array.array('f')
                samples.frombytes(buffer[:SIZE * 4]); buffer = buffer[SIZE * 4:]
                values = spectrum(samples)
            else:
                time.sleep(0.2)
                values = [0.0] * BANDS
            levels = [max(v, old * 0.78) for v, old in zip(values, levels)]
            print(json.dumps([round(v, 3) for v in levels]), flush=True)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        stop_capture(capture)

if __name__ == '__main__':
    main()
