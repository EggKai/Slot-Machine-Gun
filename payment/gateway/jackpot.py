
# jackpot_server.py (cleaned)
# Python server for TinyScreen slot clients (devNum 2,3,4)
# Protocol:
#  - Client connects and sends header: 0xFD, devNum
#  - Server sends a single byte target (0..5) to command the middle symbol
#  - Client replies after spin with 4 bytes: devNum, top, mid, bottom

import socket
import threading
import time
import random
from typing import Dict, Tuple, List

HOST = "0.0.0.0"
PORT = 5000
BET = 10
EXPECTED_DEVICES = [2, 3, 4]  # devices map to columns 0,1,2
ROLL_RESPONSE_TIMEOUT = 10.0   # seconds to wait for client results after a roll

# multipliers per symbol index (0=lemon,1=cherry,2=clover,3=bell,4=diamond,5=seven)
MULTIPLIERS = [2, 4, 8, 12, 20, 25]

# server state
clients_lock = threading.Lock()
# devNum -> (conn_socket, (addr,port))
clients: Dict[int, Tuple[socket.socket, Tuple[str, int]]] = {}
latest_results_lock = threading.Lock()
# devNum -> [top, mid, bottom]
latest_results: Dict[int, List[int]] = {}

credits_lock = threading.Lock()
credits = 0
payout = 0

# round control
round_lock = threading.Lock()
round_in_progress = False
pending_reports = set()   # devices we are still waiting for this round
current_targets: Dict[int, int] = {}

# Winning lines
# LINES = [
#     # rows (top/mid/bot)
#     [(0,0),(0,1),(0,2)],
#     [(1,0),(1,1),(1,2)],
#     [(2,0),(2,1),(2,2)],
#     # columns (device 2,3,4)
#     [(0,0),(1,0),(2,0)],
#     [(0,1),(1,1),(2,1)],
#     [(0,2),(1,2),(2,2)],
#     # diagonals
#     [(0,0),(1,1),(2,2)],
#     [(0,2),(1,1),(2,0)],
# ]

LINES = [
    # row (mid)
    [(1, 0), (1, 1), (1, 2)]
]


def recv_exact(conn: socket.socket, n: int, timeout: float = 2.0) -> bytes:
    """Receive exactly n bytes or return shorter if connection closes or timeout."""
    if timeout is not None:
        conn.settimeout(timeout)
    else:
        conn.settimeout(None)
    data = b""
    while len(data) < n:
        try:
            chunk = conn.recv(n - len(data))
        except socket.timeout:
            break
        except Exception:
            break
        if not chunk:
            break
        data += chunk
    return data


def calculate_payout_from_grid(grid: List[List[int]]) -> int:
    """
    grid: 3x3 list of symbol indices (0..5)
    Returns payout in points (multipliers * BET summed over each winning line).
    Counts each winning line once. Overlaps are allowed (center can be in multiple wins).
    """
    total_multiplier = 0
    for line in LINES:
        symbols = [grid[r][c] for (r, c) in line]
        if symbols[0] == symbols[1] == symbols[2]:
            sym = symbols[0]
            if 0 <= sym < len(MULTIPLIERS):
                total_multiplier += MULTIPLIERS[sym]
    return total_multiplier * BET


def build_grid_from_results() -> List[List[int]]:
    """
    Build 3x3 grid where columns = devices (dev 2 -> col0, dev3 -> col1, dev4 -> col2)
    rows = top(0), mid(1), bottom(2).
    If a device hasn't reported, default symbol 0 (lemon).
    """
    with latest_results_lock:
        snapshot = {dev: latest_results.get(
            dev, [0, 0, 0]) for dev in EXPECTED_DEVICES}

    all_devs = [2, 3, 4]
    for dev in all_devs:
        if dev not in snapshot:
            snapshot[dev] = [0, 0, 0]

    # Columns are devices, rows are top/mid/bottom
    grid = [
        # top row: top of each device
        [snapshot[2][0], snapshot[3][0], snapshot[4][0]],
        [snapshot[2][1], snapshot[3][1], snapshot[4][1]],  # mid row
        [snapshot[2][2], snapshot[3][2], snapshot[4][2]],  # bottom row
    ]
    return grid


def handle_client(conn: socket.socket, addr: Tuple[str, int]):
    """
    Per-client thread: expect header 0xFD, devNum (2..4) first.
    Then continuously read 4-byte reports devNum,top,mid,bottom and update latest_results.
    """
    dev_num = None
    try:
        hdr = recv_exact(conn, 2, timeout=5.0)
        if len(hdr) != 2 or hdr[0] != 0xFD:
            print(f"[WARN] Bad header from {addr}, closing")
            conn.close()
            return
        dev_num = hdr[1]
        if dev_num not in EXPECTED_DEVICES:
            print(f"[WARN] Unknown devNum {dev_num} from {addr}, closing")
            conn.close()
            return

        with clients_lock:
            clients[dev_num] = (conn, addr)
        print(f"[REGISTER] devNum {dev_num} from {addr}")

        # read loop for reports (each report is 4 bytes)
        while True:
            # block until 4 bytes or closed
            data = recv_exact(conn, 4, timeout=None)
            if not data or len(data) < 4:
                # connection closed or broken
                break
            if len(data) != 4:
                # partial packet — ignore
                continue
            r_dev, top, mid, bot = data[0], data[1], data[2], data[3]
            if r_dev != dev_num:
                print(
                    f"[WARN] devNum mismatch {r_dev} != {dev_num} from {addr}")
            with latest_results_lock:
                latest_results[dev_num] = [top, mid, bot]
            print(
                f"[REPORT] dev {dev_num} @ {addr} -> top={top} mid={mid} bot={bot}")

            # If a round is waiting for this device, mark it as arrived
            with round_lock:
                if round_in_progress and dev_num in pending_reports:
                    pending_reports.discard(dev_num)
    except Exception as e:
        print(f"[ERROR] client {addr} exception: {e}")
    finally:
        try:
            conn.close()
        except:
            pass
        if dev_num is not None:
            with clients_lock:
                if dev_num in clients:
                    del clients[dev_num]
            with latest_results_lock:
                if dev_num in latest_results:
                    del latest_results[dev_num]
            # if a device disconnects while waiting, also remove from pending
            with round_lock:
                if dev_num in pending_reports:
                    pending_reports.discard(dev_num)
            print(f"[DISCONNECT] devNum {dev_num} ({addr}) disconnected")


def accept_loop(server_sock: socket.socket):
    while True:
        try:

            conn, addr = server_sock.accept()
            if addr[0] in ('127.0.0.1', 'localhost', '::1') or addr[0] == '::ffff:127.0.0.1':
                print(f"[LOCAL] Connection from localhost {addr}")
                threading.Thread(target=slots_to_rfid_communication, args=(
                    conn, addr), daemon=True).start()

            else:
                threading.Thread(target=handle_client, args=(
                    conn, addr), daemon=True).start()
        except Exception as e:
            print(f"[ERROR] accept loop: {e}")
            time.sleep(0.1)


def send_target_to_all(target_map: Dict[int, int]):
    """
    target_map: devNum -> target (0..5)
    Sends single-byte command to each connected client. If a client is disconnected, skip.
    """
    with clients_lock:
        # iterate over a snapshot of currently-known clients
        items = list(clients.items())
    for dev, (conn, addr) in items:
        if dev not in target_map:
            continue
        try:
            payload = bytes([target_map[dev]])
            conn.sendall(payload)
        except Exception as e:
            print(f"[WARN] failed to send to dev {dev} {addr}: {e}")


def do_roll_with_targets(target_map: Dict[int, int]):
    """Core roll logic shared by random and fixed-target rolls."""
    global credits, round_in_progress, pending_reports, current_targets

    # Ensure only one roll at a time
    with round_lock:
        if round_in_progress:
            print("[WARN] Roll already in progress — ignoring new roll request.")
            return
        round_in_progress = True

    try:
        # Deduct bet
        with credits_lock:
            if credits < BET:
                print("[WARN] Not enough credits to pull.")
                return
            credits -= BET
            before = credits + BET
        print(f"[ROLL] Credits before pull: {before}   (deducted {BET})")

        # snapshot connected devices right now (to avoid race with new connects)
        with clients_lock:
            connected = {d: clients[d][0]
                         for d in clients.keys() if d in EXPECTED_DEVICES}

        # Prepare round state
        pending_reports = set(connected.keys())
        current_targets = target_map.copy()

        print(
            f"[ROLL] sending targets -> connected devices: {list(connected.keys())}   targets: {target_map}")

        # send single-byte targets to all connected clients
        send_target_to_all(target_map)

        # Wait up to timeout for those connected devices to respond (update latest_results)
        deadline = time.time() + ROLL_RESPONSE_TIMEOUT
        while time.time() < deadline:
            with latest_results_lock:
                missing = [d for d in connected.keys()
                           if d not in latest_results]
            if not missing:
                break
            # also break early if all pending_reports cleared (handle case where device reports after we update latest_results)
            with round_lock:
                if not pending_reports:
                    break
            time.sleep(0.03)

        # If still missing, show warning
        with latest_results_lock:
            missing = [d for d in connected.keys() if d not in latest_results]
        if missing:
            print(
                f"[WARN] timed out waiting for devices: {missing} (using last-known/default values)")

        # Build grid and compute payout
        grid = build_grid_from_results()
        print("[GRID] (rows = top/mid/bottom; cols = dev2/dev3/dev4)")
        for row in grid:
            print(" ".join(str(x) for x in row))

        # Flash any winning rows
        winning_rows = get_winning_rows(grid)
        if winning_rows:
            print(f"[FLASH] winning rows per device: {winning_rows}")
            send_flash_to_all(winning_rows)

        payout = calculate_payout_from_grid(grid)
        with credits_lock:
            credits += payout
            after = credits
        print(f"[ROLL] Payout: {payout}   Credits after pull: {after}")
    finally:
        # clear round state
        with round_lock:
            round_in_progress = False
            pending_reports = set()
            current_targets = {}


def roll_random_all():
    global credits, pending_reports, current_targets, round_in_progress
    with credits_lock:
        if credits < BET:
            print("[WARN] Not enough credits to pull.")
            return
        credits -= BET
        before = credits + BET
    print(f"[ROLL] Credits before pull: {before}   (deducted {BET})")

    targets = {dev: random.randint(0, 5) for dev in EXPECTED_DEVICES}

    with clients_lock:
        connected_devs = [d for d in clients.keys() if d in EXPECTED_DEVICES]

    with latest_results_lock:
        for d in connected_devs:
            latest_results[d] = None   # clear previous results

    pending_reports = set(connected_devs)
    current_targets = targets.copy()
    round_in_progress = True

    print(
        f"[ROLL] sending targets -> connected devices: {connected_devs}   targets: {targets}")
    send_target_to_all(targets)

    deadline = time.time() + ROLL_RESPONSE_TIMEOUT
    while time.time() < deadline:
        with latest_results_lock:
            missing = [d for d in connected_devs if latest_results[d] is None]
        if not missing:
            break
        time.sleep(0.03)

    if missing:
        print(
            f"[WARN] timed out waiting for devices: {missing} (using last-known/default values)")

    grid = build_grid_from_results()
    print("[GRID] (rows = top/mid/bottom; cols = dev2/dev3/dev4)")
    for row in grid:
        print(" ".join(str(x) for x in row))

    payout = calculate_payout_from_grid(grid)
    with credits_lock:
        credits += payout
        after = credits
    print(f"[ROLL] Payout: {payout}   Credits after pull: {after}")

    round_in_progress = False
    pending_reports = set()
    current_targets = {}


def roll_set_target_map(target_map: Dict[int, int]):
    """Roll but using an externally-specified map of targets (allow 't N' type commands)."""
    with clients_lock:
        connected_devs = [d for d in clients.keys() if d in EXPECTED_DEVICES]
    with latest_results_lock:
        for d in connected_devs:
            if d in latest_results:
                del latest_results[d]
    do_roll_with_targets(target_map)


def send_flash_to_all(flash_map: Dict[int, List[int]]):
    with clients_lock:
        for dev, (conn, addr) in clients.items():
            rows = flash_map.get(dev, [])
            mask = 0
            for r in rows:
                mask |= (1 << r)  # bit0=top, bit1=mid, bit2=bottom
            if mask == 0:
                continue
            mask |= 0x80  # set high bit to avoid conflict with 0..5
            try:
                conn.sendall(bytes([mask]))
            except Exception as e:
                print(f"[WARN] failed to send flash mask to dev {dev}: {e}")


def get_winning_rows(grid) -> Dict[int, List[int]]:
    flash_map = {}
    # flash any row/column/diagonal
    for idx, line in enumerate(LINES):
        symbols = [grid[r][c] for r, c in line]
        if symbols[0] == symbols[1] == symbols[2]:
            # for each column (device) in the line
            for col_idx, dev in enumerate([2, 3, 4]):
                rows = [r for r, c in line if c == col_idx]
                flash_map.setdefault(dev, []).extend(rows)
    return flash_map


def add_credits(amount=100):
    global credits
    with credits_lock:
        credits += amount
        print(f"[CREDIT] Added {amount}, credits now {credits}")


def set_credits(amount):
    global credits
    with credits_lock:
        credits = amount
        print(f"[CREDIT] Set credits = {credits}")


def show_credits():
    with credits_lock:
        print(f"[CREDITS] {credits}")


def main():
    global credits
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(8)
    print(f"[LISTEN] Server listening on {HOST}:{PORT}")

    threading.Thread(target=accept_loop, args=(
        server_sock,), daemon=True).start()

    # main command loop
    while True:
        try:

            cmd = input(
                "Commands: (enter)=roll random, 't N'=roll N to all, 'c'=add100, 's'=show, 'set N'=set credits, 'q'=quit\n> ").strip()
        except EOFError:
            break

        if cmd == "":
            show_credits()
            roll_random_all()
        elif cmd.lower() == "c":
            add_credits(100)
        elif cmd.lower() == "s":
            show_credits()
        elif cmd.lower().startswith("set "):
            parts = cmd.split()
            if len(parts) >= 2:
                try:
                    val = int(parts[1])
                    set_credits(val)
                except:
                    print("[ERR] bad set value")
            else:
                print("[ERR] usage: set N")
        elif cmd.lower().startswith("t "):
            # allow "t N" to force all to same target N
            parts = cmd.split()
            if len(parts) >= 2:
                try:
                    n = int(parts[1])
                    if 0 <= n <= 5:
                        target_map = {dev: n for dev in EXPECTED_DEVICES}
                        show_credits()
                        roll_set_target_map(target_map)
                    else:
                        print("[ERR] N must be 0..5")
                except:
                    print("[ERR] bad number")
            else:
                print("[ERR] usage: t N")
        elif cmd.lower() == "q":
            print("Quitting.")
            break
        else:
            print("[?] Unknown command")


def slots_to_rfid_communication(conn: socket.socket, addr):
    global payout, credits
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            message = data.decode().strip()
            print(message)
            if message == "SUCCESS":
                # Calculate payout first
                roll_slot_all()
                # Now payout contains the actual calculated value
                print(f"[ROLL] Actual payout calculated: {payout}")

                # Send the payout status to RFID
                send_slots_status_to_RFID(conn, payout)

                # Send payout command to slot clients
                if payout > 0:
                    print(f"[PAYOUT] Sending payout {payout} to slot clients")
                    send_target_payout(payout)
                else:
                    print("[PAYOUT] No payout to send (0 or negative)")

            elif message == "NO CREDS":
                print("HERE - NO CREDS detected, calling send_target_credits()")
                send_target_credits()
                print("HERE - Returned from send_target_credits()")
    except ConnectionResetError:
        print(f"[!] Connection lost with {addr[0]}:{addr[1]}")
    except Exception as e:
        print(f"[ERROR] RFID communication error: {e}")


def send_target_credits():
    global credits, current_targets
    with clients_lock:
        items = list(clients.items())
    for dev, (conn, addr) in items:
        try:
            payload = bytes([0xAA])  # send only 1 byte
            conn.sendall(payload)
        except Exception as e:
            print(f"[WARN] failed to send to dev {dev} {addr}: {e}")


def send_target_payout(payout):
    global credits, current_targets
    print(f"[DEBUG] Preparing to send payout: {payout}")
    with clients_lock:
        items = list(clients.items())
    for dev, (conn, addr) in items:
        try:
            payload = bytes([0xAB])  # send only 1 byte
            print(f"[DEBUG] Sending command 0xAB to dev {dev}")
            conn.sendall(payload)
            time.sleep(0.1)  # Reduced delay
            payout_byte = max(0, min(255, payout))
            print(f"[DEBUG] Sending payout value: {payout_byte} to dev {dev}")
            conn.sendall(bytes([payout_byte]))
        except Exception as e:
            print(f"[WARN] failed to send to dev {dev} {addr}: {e}")


def roll_slot_all():
    global credits, pending_reports, current_targets, round_in_progress, payout

    targets = {dev: random.randint(0, 5) for dev in EXPECTED_DEVICES}

    with clients_lock:
        connected_devs = [d for d in clients.keys() if d in EXPECTED_DEVICES]

    with latest_results_lock:
        for d in connected_devs:
            latest_results[d] = None   # clear previous results

    pending_reports = set(connected_devs)
    current_targets = targets.copy()
    round_in_progress = True

    print(
        f"[ROLL] sending targets -> connected devices: {connected_devs}   targets: {targets}")
    send_target_to_all(targets)

    deadline = time.time() + ROLL_RESPONSE_TIMEOUT
    while time.time() < deadline:
        with latest_results_lock:
            missing = [d for d in connected_devs if latest_results[d] is None]
        if not missing:
            break
        time.sleep(0.03)

    if missing:
        print(
            f"[WARN] timed out waiting for devices: {missing} (using last-known/default values)")

    grid = build_grid_from_results()
    print("[GRID] (rows = top/mid/bottom; cols = dev2/dev3/dev4)")
    for row in grid:
        print(" ".join(str(x) for x in row))

    payout = calculate_payout_from_grid(grid)

    round_in_progress = False
    pending_reports = set()
    current_targets = {}


def send_slots_status_to_RFID(conn, payout):

    conn.sendall(str(payout).encode())


if __name__ == "__main__":
    main()
