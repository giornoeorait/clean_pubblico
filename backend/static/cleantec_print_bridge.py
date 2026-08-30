#!/usr/bin/env python3
"""
CleanTec Print Bridge — stampa diretta DDT su stampante di rete (Ricoh MP C4503 e simili).
Da eseguire su un PC/Raspberry nella STESSA RETE della stampante. Solo libreria standard Python 3.7+.

USO:
  python3 cleantec_print_bridge.py --server https://cleantec.app --token IL_TUO_BRIDGE_TOKEN
"""
import argparse
import json
import socket
import struct
import sys
import time
import urllib.request

POLL_SEC = 3


def http(server, path, token, data=None, binary=False):
    req = urllib.request.Request(server + path, data=data,
                                 headers={"X-Bridge-Token": token, "User-Agent": "CleanTecPrintBridge/1.0"})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return body if binary else json.loads(body.decode())


def ipp_attr(tag, name, value):
    if isinstance(value, str):
        value = value.encode()
    return struct.pack(">B", tag) + struct.pack(">H", len(name)) + name.encode() + struct.pack(">H", len(value)) + value


def ipp_print(ip, port, pdf, copies=1):
    """IPP Print-Job (RFC 8011) minimale. Ritorna (ok, msg)."""
    for path in ("/ipp/print", "/printers/ipp", "/printer", ""):
        uri = f"ipp://{ip}:{port}{path}"
        body = struct.pack(">HHI", 0x0101, 0x0002, 1)  # version 1.1, Print-Job, request-id
        body += b"\x01"  # operation-attributes-tag
        body += ipp_attr(0x47, "attributes-charset", "utf-8")
        body += ipp_attr(0x48, "attributes-natural-language", "it")
        body += ipp_attr(0x45, "printer-uri", uri)
        body += ipp_attr(0x42, "requesting-user-name", "cleantec")
        body += ipp_attr(0x49, "document-format", "application/pdf")
        if copies > 1:
            body += b"\x02" + ipp_attr(0x21, "copies", struct.pack(">i", copies))
        body += b"\x03"  # end-of-attributes
        body += pdf
        try:
            req = urllib.request.Request(f"http://{ip}:{port}{path or '/'}", data=body,
                                         headers={"Content-Type": "application/ipp"})
            with urllib.request.urlopen(req, timeout=25) as r:
                resp = r.read(8)
                status = struct.unpack(">H", resp[2:4])[0] if len(resp) >= 4 else 0xFFFF
                if status <= 0x0002:  # successful-ok*
                    return True, f"IPP ok su {path or '/'} (status 0x{status:04x})"
        except Exception as e:
            last = f"IPP {path or '/'}: {e}"
    return False, last


def raw9100_print(ip, port, pdf, copies=1):
    """Invio RAW su porta 9100 (richiede PDF/PostScript Direct Print sulla stampante)."""
    try:
        for _ in range(copies):
            with socket.create_connection((ip, port), timeout=15) as s:
                s.settimeout(30)
                s.sendall(pdf)
        return True, f"RAW {port}: {len(pdf)} byte inviati x{copies}"
    except Exception as e:
        return False, f"RAW {port}: {e}"


def check_printer(ip, ports=(631, 9100)):
    for p in ports:
        try:
            with socket.create_connection((ip, p), timeout=5):
                return True, f"Stampante raggiungibile su {ip}:{p}"
        except Exception:
            continue
    return False, f"Stampante NON raggiungibile su {ip} (porte {ports})"


def handle(server, token, job):
    printer = job.get("printer") or {}
    ip, proto = printer.get("ip"), printer.get("protocollo", "ipp")
    copies = int(printer.get("copie") or 1)
    if job["tipo"] == "check":
        ok, msg = check_printer(ip)
        print(f"  [check] {msg}")
        return ok, msg
    pdf = http(server, f"/api/print-bridge/jobs/{job['id']}/pdf", token, binary=True)
    print(f"  PDF scaricato: {len(pdf)} byte — {job.get('ddt_numero') or job['tipo']}")
    if proto == "ipp":
        ok, msg = ipp_print(ip, int(printer.get("porta") or 631), pdf, copies)
        if not ok:
            print(f"  IPP fallito ({msg}), provo RAW 9100…")
            ok, msg = raw9100_print(ip, 9100, pdf, copies)
    else:
        ok, msg = raw9100_print(ip, int(printer.get("porta") or 9100), pdf, copies)
        if not ok:
            ok2, msg2 = ipp_print(ip, 631, pdf, copies)
            if ok2:
                ok, msg = ok2, msg2
    print(f"  Risultato: {'STAMPATO' if ok else 'FALLITO'} — {msg}")
    return ok, msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="URL del gestionale, es. https://cleantec.app")
    ap.add_argument("--token", required=True, help="Bridge token (pagina Stampa & Totem)")
    a = ap.parse_args()
    server = a.server.rstrip("/")
    host = socket.gethostname()
    print(f"CleanTec Print Bridge avviato — server {server}, device {host}. CTRL+C per uscire.")
    while True:
        try:
            data = http(server, f"/api/print-bridge/poll?device={host}", a.token)
            job = data.get("job")
            if job:
                print(f"[{time.strftime('%H:%M:%S')}] Job {job['id'][:8]} tipo={job['tipo']}")
                ok, msg = handle(server, a.token, job)
                http(server, f"/api/print-bridge/jobs/{job['id']}/status", a.token,
                     data=json.dumps({"stato": "printed" if ok else "failed", "errore": None if ok else msg}).encode())
            else:
                time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            print(f"[bridge] errore: {e} — riprovo tra 10s")
            time.sleep(10)


if __name__ == "__main__":
    main()
