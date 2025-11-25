import serial
import requests
import re
import time
import socket
import threading
import json

# --- Settings ---
SERIAL_PORT = "COM5"
BAUD_RATE = 9600
BASE_URL = "http://103.213.247.25:8000/rfid/deduct"
BASE_URL_2 = "http://103.213.247.25:8000/rfid/add"
DEDUCT_AMOUNT = -10  # Amount to deduct each time
HOST = "127.0.0.1"
PORT = 5000

HOST2 = "10.102.150.134"
PORT2 = 9000

# Global variable for server response
server_response = None
response_lock = threading.Lock()
response_received = threading.Event()


def send_rfid_post(rfid_id, ser):
    payload = {
        "rfid_id": rfid_id,
        "amount": str(DEDUCT_AMOUNT)
    }

    remaining_credits = None  # Initialize variable

    try:
        res = requests.post(BASE_URL, json={"rfid_id": rfid_id})
        print("Sent POST:", payload)

        print("Response:", res.text[:200])  # show first 200 chars
        print(f"✅ OK (status {res.status_code})")

        data = json.loads(res.text[:200])
        remaining_credits = data["remaining_credits"]

    except Exception as e:
        print("❌ FAIL (error:", e, ")")
        return "FAILED"
    finally:
        # ✅ Tell Arduino it's safe to scan again
        ser.write(b"DONE\n")
        ser.flush()
        print("Sent DONE to Arduino\n")

    # Return after the finally block based on the credits
    if remaining_credits == 0:
        return "NO CREDS"
    else:
        return "SUCCESS"


def parse_rfid_line(line):
    match = re.search(r"USER ID tag\s*:\s*([0-9A-Fa-f ]+)", line)
    if match:
        return "".join(match.group(1).strip().split())  # e.g. 534E23A2
    return None


def handle_server_messages(sock):
    """Thread function to read messages from server."""
    global server_response
    while True:
        try:
            data = sock.recv(1024)
            if not data:
                print("[SERVER] Connection closed")
                break

            message = data.decode().strip()
            print("[SERVER] Received:", message)

            # Store the response and notify main thread
            with response_lock:
                server_response = message
            response_received.set()

        except Exception as e:
            print("[SERVER] Error:", e)
            break


def connect_to_server(hostaddr, hostport):
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((hostaddr, hostport))
            print(f"[SERVER] Connected to {hostaddr}:{hostport}")
            threading.Thread(target=handle_server_messages,
                             args=(sock,), daemon=True).start()
            return sock
        except Exception as e:
            print(f"[ERROR] Failed to connect to {hostaddr}:{hostport} - {e}")


def wait_for_server_response(timeout=3):
    """Wait for server response with timeout"""
    global server_response
    print("Waiting for server response...")

    if response_received.wait(timeout=timeout):
        with response_lock:
            response = server_response
            server_response = None  # Reset for next use
        response_received.clear()
        return response
    else:
        print("❌ Timeout waiting for server response")
        return None


def update_server_rfid(rfid_id, payout):
    payload = {"rfid_id": rfid_id, "amount": payout}
    try:
        res = requests.post(BASE_URL_2, json=payload, timeout=5)
        print(f"Status: {res.status_code}")
        print("Response:", res.json())
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)


def main():
    global server_response

    print(f"Opening serial port {SERIAL_PORT}...")
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
        time.sleep(5)
        print("Listening for RFID scans...\n")

    while True:
        try:
            jackpot_server_sock = connect_to_server(HOST, PORT)
            turret_server_sock = connect_to_server(HOST2, PORT2)
            break  # Break out of the loop only when both connections are successful
        except Exception as e:
            print(f"[ERROR] One or both connections failed, retrying both...")

        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            print("Serial:", line)
            rfid_id = parse_rfid_line(line)
            if rfid_id:
                # Send RFID data to HTTP server
                return_message = send_rfid_post(rfid_id, ser)

                # Send result to socket server
                jackpot_server_sock.sendall(return_message.encode())
                print(
                    f"Sent '{return_message}' to server, waiting for response...")

                if return_message == "NO CREDS":
                    print(f"Send message to turret_server {return_message}")
                    turret_server_sock.sendall(
                        (return_message + "\n").encode())

                # Wait for server response before continuing
                server_response = wait_for_server_response()

                print(f"Raw server response: {server_response}")

                # Handle the server response safely
                if server_response is not None:
                    try:
                        payout_value = int(server_response)

                        if payout_value == 0:
                            print(f"Payout: 0")
                        elif payout_value > 0:
                            print(f"Payout: {payout_value}")
                            update_server_rfid(rfid_id, payout_value)
                        else:
                            print(f"Unexpected payout value: {payout_value}")

                    except (ValueError, TypeError) as e:
                        print(
                            f"Error converting server response to integer: {e}")
                        print(f"Server sent: '{server_response}'")
                else:
                    print("No response from server, continuing anyway...")


if __name__ == "__main__":
    main()
