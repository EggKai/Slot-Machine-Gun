import argparse
import os
import socket
import sys
import threading
import time
from datetime import datetime
from typing import Optional

from killcambot import send_video_to_subscribers  # local helper to push recorded clips

try:
    import cv2
except Exception:
    cv2 = None

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover
    print("pyserial not installed. Install with: pip install pyserial", file=sys.stderr)
    sys.exit(1)


class StepperClient:
    def __init__(self, port: str = "COM5", baud: int = 115200, timeout: float = 10.0, verbose: bool = False):
        self.verbose = verbose
        self.timeout = timeout
        self._lock = threading.Lock()
        self.ser = serial.Serial(port=port, baudrate=baud, timeout=timeout, write_timeout=timeout)
        time.sleep(2.0)  # allow Uno reset
        self.ser.reset_input_buffer()
        t0 = time.time()
        while time.time() - t0 < 1.0:
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line:
                break
            if self.verbose:
                print(f"< {line}")

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def _send(self, line: str) -> str:
        with self._lock:
            if not line.endswith("\n"):
                line += "\n"
            if self.verbose:
                print(f"> {line.rstrip()}")
            self.ser.reset_input_buffer()
            self.ser.write(line.encode("ascii"))
            self.ser.flush()
            end = time.time() + self.timeout
            resp = ""
            while time.time() < end:
                r = self.ser.readline().decode(errors="ignore").strip()
                if not r:
                    continue
                if r.startswith("READY") or r.startswith("Commands:"):
                    continue
                resp = r
                break
            if self.verbose and resp:
                print(f"< {resp}")
            return resp

    # High-level helpers
    def help(self) -> str:
        self.ser.reset_input_buffer()
        self._send("HELP")
        lines = []
        t0 = time.time()
        while time.time() - t0 < 0.5:
            line = self.ser.readline().decode(errors="ignore").rstrip()
            if not line:
                break
            lines.append(line)
        return "\n".join(lines)

    def speed(self, rpm: int) -> str:
        return self._send(f"SPEED {rpm}")

    def stop(self) -> str:
        return self._send("STOP")

    def resume(self) -> str:
        return self._send("RESUME")

    def release(self) -> str:
        return self._send("RELEASE")

    def step_a(self, steps: int) -> str:
        return self._send(f"A {steps}")

    def step_b(self, steps: int) -> str:
        return self._send(f"B {steps}")

    def step_c(self, steps: int) -> str:
        return self._send(f"C {steps}")

    def step_ab(self, a_steps: int, b_steps: int) -> str:
        return self._send(f"AB {a_steps} {b_steps}")

    def step_abc(self, a_steps: int, b_steps: int, c_steps: int) -> str:
        return self._send(f"ABC {a_steps} {b_steps} {c_steps}")

    def target(self) -> str:
        return self._send("TARGET")

    def demo(self, on: Optional[bool] = None) -> str:
        if on is None:
            return self._send("DEMO")
        return self._send("DEMO ON" if on else "DEMO OFF")


def _track_face(ns, client: StepperClient):
    if cv2 is None:
        sys.exit("OpenCV not installed. Install with: pip install opencv-python")
    if ns.rpm and ns.rpm > 0:
        client.speed(int(ns.rpm))

    api_map = {
        "auto": getattr(cv2, "CAP_ANY", 0),
        "dshow": getattr(cv2, "CAP_DSHOW", 700),
        "msmf": getattr(cv2, "CAP_MSMF", 1400),
        "v4l2": getattr(cv2, "CAP_V4L2", 200),
        "avfoundation": getattr(cv2, "CAP_AVFOUNDATION", 1200),
        "gstreamer": getattr(cv2, "CAP_GSTREAMER", 1800),
    }
    cam_src = ns.cam
    try:
        cam_src = int(ns.cam)
    except ValueError:
        pass
    cap = cv2.VideoCapture(cam_src, api_map.get(ns.cam_api, api_map["auto"]))
    if not cap.isOpened():
        sys.exit(f"Failed to open camera {ns.cam} with api {ns.cam_api}")

    cascade_path = getattr(cv2.data, "haarcascades", None)
    face_model = cascade_path + "haarcascade_frontalface_default.xml" if cascade_path else None
    if not face_model:
        sys.exit("Could not locate haarcascade_frontalface_default.xml")
    face_cascade = cv2.CascadeClassifier(face_model)
    if face_cascade.empty():
        sys.exit("Failed to load Haar cascade")

    print("Tracking... press 'q' to quit")
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(ns.min_face, ns.min_face)
            )
            h, w = frame.shape[:2]
            cx_tgt, cy_tgt = w / 2.0, h / 2.0
            step_x = step_y = 0
            if len(faces) > 0:
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                cx = x + fw / 2.0
                cy = y + fh / 2.0
                err_x = cx - cx_tgt
                err_y = cy - cy_tgt
                step_x = int(max(-ns.max_step, min(ns.max_step, err_x * ns.step_scale)))
                step_y = int(max(-ns.max_step, min(ns.max_step, err_y * ns.step_scale)))
                if ns.invert_x:
                    step_x = -step_x
                if ns.invert_y:
                    step_y = -step_y
                if not ns.no_display:
                    cv2.rectangle(frame, (x, y), (x + fw, y + fh), (0, 255, 0), 2)
                    cv2.circle(frame, (int(cx), int(cy)), 4, (0, 0, 255), -1)
            if step_x != 0 or step_y != 0:
                client.step_ab(step_x, -step_y)  # negate Y so positive err_y drives up if wiring matches
            if not ns.no_display:
                cv2.drawMarker(frame, (int(cx_tgt), int(cy_tgt)), (255, 255, 0), cv2.MARKER_CROSS, 20, 2)
                cv2.putText(frame, f"err=({step_x},{step_y})", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 255), 1, cv2.LINE_AA)
                cv2.imshow("FaceTrack", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
            else:
                time.sleep(0.03)
    finally:
        try:
            cap.release()
        except Exception:
            pass
        if not ns.no_display:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass


def _target_once(ns, client: StepperClient):
    """Aim once using face detection, then run the C sweep macro."""
    if cv2 is None:
        sys.exit("OpenCV not installed. Install with: pip install opencv-python")
    if ns.rpm and ns.rpm > 0:
        client.speed(int(ns.rpm))

    api_map = {
        "auto": getattr(cv2, "CAP_ANY", 0),
        "dshow": getattr(cv2, "CAP_DSHOW", 700),
        "msmf": getattr(cv2, "CAP_MSMF", 1400),
        "v4l2": getattr(cv2, "CAP_V4L2", 200),
        "avfoundation": getattr(cv2, "CAP_AVFOUNDATION", 1200),
        "gstreamer": getattr(cv2, "CAP_GSTREAMER", 1800),
    }
    cam_src = ns.cam
    try:
        cam_src = int(ns.cam)
    except ValueError:
        pass
    cap = cv2.VideoCapture(cam_src, api_map.get(ns.cam_api, api_map["auto"]))
    if not cap.isOpened():
        sys.exit(f"Failed to open camera {ns.cam} with api {ns.cam_api}")

    cascade_path = getattr(cv2.data, "haarcascades", None)
    face_model = cascade_path + "haarcascade_frontalface_default.xml" if cascade_path else None
    if not face_model:
        sys.exit("Could not locate haarcascade_frontalface_default.xml")
    face_cascade = cv2.CascadeClassifier(face_model)
    if face_cascade.empty():
        sys.exit("Failed to load Haar cascade")

    face_found = False
    step_x = step_y = 0
    t_end = time.time() + ns.target_timeout
    try:
        while time.time() < t_end:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(ns.min_face, ns.min_face)
            )
            h, w = frame.shape[:2]
            cx_tgt, cy_tgt = w / 2.0, h / 2.0
            if len(faces) == 0:
                if not ns.no_display:
                    cv2.drawMarker(frame, (int(cx_tgt), int(cy_tgt)), (255, 255, 0), cv2.MARKER_CROSS, 20, 2)
                    cv2.putText(frame, "No face", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (0, 255, 255), 1, cv2.LINE_AA)
                    cv2.imshow("FaceTarget", frame)
                    cv2.waitKey(1)
                continue

            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            cx = x + fw / 2.0
            cy = y + fh / 2.0
            err_x = cx - cx_tgt
            err_y = cy - cy_tgt
            step_x = int(max(-ns.max_step, min(ns.max_step, err_x * ns.step_scale)))
            step_y = int(max(-ns.max_step, min(ns.max_step, err_y * ns.step_scale)))
            if ns.invert_x:
                step_x = -step_x
            if ns.invert_y:
                step_y = -step_y
            face_found = True

            if not ns.no_display:
                cv2.rectangle(frame, (x, y), (x + fw, y + fh), (0, 255, 0), 2)
                cv2.circle(frame, (int(cx), int(cy)), 4, (0, 0, 255), -1)
                cv2.drawMarker(frame, (int(cx_tgt), int(cy_tgt)), (255, 255, 0), cv2.MARKER_CROSS, 20, 2)
                cv2.putText(frame, f"err=({step_x},{step_y})", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 255), 1, cv2.LINE_AA)
                cv2.imshow("FaceTarget", frame)
                cv2.waitKey(1)
            break
    finally:
        try:
            cap.release()
        except Exception:
            pass
        if not ns.no_display:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    if not face_found:
        sys.exit("No face detected within target timeout")

    if step_x != 0 or step_y != 0:
        client.step_ab(step_x, -step_y)  # negate Y so positive err_y drives up if wiring matches

    # Run the C sweep macro on the firmware; fall back if unavailable
    resp = client.target()
    if resp.startswith("ERR") or resp == "":
        client.step_c(-150)
        time.sleep(1.0)
        client.step_c(150)
        return "TARGET: manual C sweep complete"
    return resp


def _record_clip(cam: str, cam_api: str, duration: float = 5.0, fps: int = 20, ext: str = "mp4") -> Optional[str]:
    """Record a short clip from the specified camera; returns path or None."""
    if cv2 is None:
        print("[SERVER] OpenCV not installed; cannot record clip")
        return None

    api_map = {
        "auto": getattr(cv2, "CAP_ANY", 0),
        "dshow": getattr(cv2, "CAP_DSHOW", 700),
        "msmf": getattr(cv2, "CAP_MSMF", 1400),
        "v4l2": getattr(cv2, "CAP_V4L2", 200),
        "avfoundation": getattr(cv2, "CAP_AVFOUNDATION", 1200),
        "gstreamer": getattr(cv2, "CAP_GSTREAMER", 1800),
    }
    cam_src = cam
    try:
        cam_src = int(cam)
    except ValueError:
        pass

    def open_with_fallback():
        preferred = [api_map.get(cam_api, api_map["auto"])]
        # Common fallbacks to avoid blank captures on Windows.
        # Skip MSMF to reduce noisy grabFrame warnings on some drivers.
        for api_key in ("dshow", "auto"):
            val = api_map.get(api_key)
            if val is not None and val not in preferred:
                preferred.append(val)
        for backend in preferred:
            cap_try = cv2.VideoCapture(cam_src, backend)
            if not cap_try.isOpened():
                cap_try.release()
                continue
            ok, frm = cap_try.read()
            if ok and frm is not None and frm.mean() > 1.0:
                return cap_try, frm
            cap_try.release()
        return None, None

    cap, frame = open_with_fallback()
    if cap is None or frame is None:
        print(f"[SERVER] Failed to open camera {cam} with api {cam_api} (and fallbacks)")
        return None

    # Get frame size
    h, w = frame.shape[:2]
    ext = (ext or "avi").lower()
    if ext == "mp4":
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        suffix = "mp4"
    else:
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        suffix = "avi"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{ts}-shot.{suffix}"
    writer = cv2.VideoWriter(filename, fourcc, fps, (w, h))
    end = time.time() + duration

    # Write the first frame
    writer.write(frame)
    while time.time() < end:
        ok, frame = cap.read()
        if ok and frame is not None:
            writer.write(frame)
        else:
            time.sleep(0.01)

    writer.release()
    cap.release()
    print(f"[SERVER] Saved recording to {filename}")
    return filename


def _handle_server_messages(sock: socket.socket, client: StepperClient, stop_event: threading.Event, rec_cfg: Optional[dict] = None):
    """Background listener for server messages."""
    buf = b""
    while not stop_event.is_set():
        try:
            data = sock.recv(1024)
        except OSError:
            break
        if not data:
            break
        buf += data

        def handle_msg(msg: str):
            if not msg:
                return False
            print(f"[SERVER] recv: {msg}")
            if msg.upper().__contains__("NO CREDS"):
                rec_thread = None
                video_path_holder = {"path": None}
                if rec_cfg:
                    rec_thread = threading.Thread(
                        target=lambda holder: holder.update({"path": _record_clip(
                            rec_cfg.get("cam", "0"),
                            rec_cfg.get("cam_api", "auto"),
                            rec_cfg.get("duration", 10.0),
                            10, # static fps, change this according to 
                            rec_cfg.get("ext", "mp4"),
                        )}),
                        args=(video_path_holder,),
                        daemon=True,
                    )
                    rec_thread.start()
                print('[STATUS] recording started, arming shot')
                time.sleep(0.5)
                print('[STATUS] shooting')
                client.step_c(-500)
                if rec_thread:
                    rec_thread.join(timeout=rec_cfg.get("duration", 7.0) + 2.0)
                    video_path = video_path_holder.get("path")
                    if video_path:
                        try:
                            send_video_to_subscribers(video_path, caption="NO CREDS event")
                        except Exception as e:
                            print(f"[WARN] Failed to send video: {e}")
                client.step_c(240)
                stop_event.set()
                return True
            return False

        # Process newline-delimited messages
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            msg = line.decode(errors="ignore").strip()
            if handle_msg(msg):
                return

        # Process short packets without newline
        if buf and b"\n" not in buf:
            msg = buf.decode(errors="ignore").strip()
            buf = b""
            if handle_msg(msg):
                return
    stop_event.set()


def start_server(host: str, port: int, client: StepperClient, rec_cfg: Optional[dict] = None):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    print(f"[SERVER] Listening on {host}:{port} ...")
    conn, addr = srv.accept()
    print(f"[SERVER] Client connected from {addr[0]}:{addr[1]}")
    stop_event = threading.Event()
    threading.Thread(target=_handle_server_messages, args=(conn, client, stop_event, rec_cfg), daemon=True).start()
    return srv, conn, stop_event


def start_server_async(host: str, port: int, client: StepperClient, rec_cfg: Optional[dict] = None):
    """Start a listener in a background thread so tracking can run concurrently."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    stop_event = threading.Event()
    conn_holder = {"conn": None}

    def accept_and_handle():
        print(f"[SERVER] Listening on {host}:{port} ...")
        try:
            conn, addr = srv.accept()
        except OSError:
            return
        conn_holder["conn"] = conn
        print(f"[SERVER] Client connected from {addr[0]}:{addr[1]}")
        threading.Thread(target=_handle_server_messages, args=(conn, client, stop_event, rec_cfg), daemon=True).start()
        stop_event.wait()

    thread = threading.Thread(target=accept_and_handle, daemon=True)
    thread.start()
    return srv, conn_holder, stop_event, thread


def main(argv=None) -> int:
    # Default behavior: run face tracking + listener with preset options when no CLI args are provided.
    if argv is None and len(sys.argv) == 1:
        argv = [
            "track",
            "--port", "COM5",
            "--cam", "0",
            "--cam-api", "dshow",
            "--rpm", "12",
            "--step-scale", "0.05",
            "--max-step", "50",
            "--listen-while-track",
            "--tcp-host", "0.0.0.0",
            "--tcp-port", "9000",
        ]
    p = argparse.ArgumentParser(description="Control ULN2003 28BYJ-48 steppers over Arduino serial")
    p.add_argument("command", type=lambda s: s.lower(), choices=[
        "help", "speed", "stop", "resume", "release", "a", "b", "c", "ab", "abc", "demo", "target", "track", "listen", "repl"
    ], help="Command to run")
    p.add_argument("args", nargs="*", help="Command arguments")
    p.add_argument("--port", default="COM5", help="Serial port (default: COM5)")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    p.add_argument("--timeout", type=float, default=10.0, help="Response timeout seconds (default: 10)")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose I/O logging")
    # Tracking options
    p.add_argument("--cam", default="0", help="Camera index or path for face tracking (default 0)")
    p.add_argument("--cam-api", default="auto", choices=["auto", "dshow", "msmf", "v4l2", "avfoundation", "gstreamer"],
                   help="OpenCV capture backend for tracking")
    p.add_argument("--rpm", type=int, default=12, help="Stepper RPM to set before tracking (default 12)")
    p.add_argument("--step-scale", type=float, default=0.05, help="Steps per pixel error (default 0.05)")
    p.add_argument("--max-step", type=int, default=25, help="Max step burst per update (default 25)")
    p.add_argument("--min-face", type=int, default=60, help="Minimum face size in pixels (default 60)")
    p.add_argument("--target-timeout", type=float, default=3.0, help="Seconds to search for a face in TARGET (default 3)")
    p.add_argument("--invert-x", action="store_true", help="Invert pan direction")
    p.add_argument("--invert-y", action="store_true", help="Invert tilt direction")
    p.add_argument("--no-display", action="store_true", help="Disable window during tracking")
    p.add_argument("--record-ext", choices=["avi", "mp4"], default="mp4", help="Recording format for NO CREDS clips")
    p.add_argument("--tcp-host", default="0.0.0.0", help="TCP bind host for listen command")
    p.add_argument("--tcp-port", type=int, default=9000, help="TCP bind port for listen command")
    p.add_argument(
        "--listen-while-track",
        action="store_true",
        default=True,
        help="Start TCP listener while tracking (enabled by default)",
    )
    ns = p.parse_args(argv)

    client = StepperClient(port=ns.port, baud=ns.baud, timeout=ns.timeout, verbose=ns.verbose)
    try:
        cmd = ns.command
        a = ns.args
        if cmd == "repl":
            print("Interactive mode. Type commands like 'HELP', 'A 200', 'STOP'. Ctrl+C to exit.")
            while True:
                try:
                    line = input("> ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not line.strip():
                    continue
                resp = client._send(line)
                if resp:
                    print(resp)
            return 0
        if cmd == "help":
            print(client.help())
        elif cmd == "speed":
            if len(a) != 1:
                p.error("speed requires 1 arg: <rpm>")
            print(client.speed(int(a[0])))
        elif cmd == "stop":
            print(client.stop())
        elif cmd == "resume":
            print(client.resume())
        elif cmd == "release":
            print(client.release())
        elif cmd == "a":
            if len(a) != 1:
                p.error("a requires 1 arg: <steps>")
            print(client.step_a(int(a[0])))
        elif cmd == "b":
            if len(a) != 1:
                p.error("b requires 1 arg: <steps>")
            print(client.step_b(int(a[0])))
        elif cmd == "c":
            if len(a) != 1:
                p.error("c requires 1 arg: <steps>")
            print(client.step_c(int(a[0])))
        elif cmd == "ab":
            if len(a) != 2:
                p.error("ab requires 2 args: <a_steps> <b_steps>")
            print(client.step_ab(int(a[0]), int(a[1])))
        elif cmd == "abc":
            if len(a) != 3:
                p.error("abc requires 3 args: <a_steps> <b_steps> <c_steps>")
            print(client.step_abc(int(a[0]), int(a[1]), int(a[2])))
        elif cmd == "target":
            if len(a) != 0:
                p.error("target takes no args")
            print(_target_once(ns, client))
        elif cmd == "demo":
            if len(a) == 0:
                print(client.demo())
            elif a[0].lower() in ("on", "1", "true"):
                print(client.demo(True))
            elif a[0].lower() in ("off", "0", "false"):
                print(client.demo(False))
            else:
                p.error("demo arg must be on/off or 1/0")
        elif cmd == "listen":
            if len(a) != 0:
                p.error("listen takes no args")
            rec_cfg = {"cam": ns.cam, "cam_api": ns.cam_api, "duration": 10.0, "ext": ns.record_ext or "mp4"}
            srv, conn, stop_event = start_server(ns.tcp_host, ns.tcp_port, client, rec_cfg)
            try:
                while True:
                    time.sleep(0.5)
                    if stop_event.is_set():
                        break
            except KeyboardInterrupt:
                print("\nStopping listener")
            finally:
                stop_event.set()
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    srv.close()
                except Exception:
                    pass
        elif cmd == "track":
            srv = conn = stop_event = None
            server_ctx = None
            if ns.listen_while_track:
                rec_cfg = {"cam": ns.cam, "cam_api": ns.cam_api, "duration": 10.0, "ext": ns.record_ext or "mp4"}
                srv, conn_holder, stop_event, _ = start_server_async(ns.tcp_host, ns.tcp_port, client, rec_cfg)
                server_ctx = (srv, conn_holder, stop_event)
            try:
                _track_face(ns, client)
            finally:
                if server_ctx:
                    stop_event.set()
                    conn = conn_holder.get("conn")
                    try:
                        if conn:
                            conn.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass
                    try:
                        srv.close()
                    except Exception:
                        pass
        else:
            p.error("unknown command")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
