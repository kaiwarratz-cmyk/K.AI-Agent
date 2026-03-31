from __future__ import annotations
import subprocess
import socket
import urllib.request

def net_ping(host: str, count: int = 2) -> str:
    """Pings a host to check network availability."""
    try:
        # Resolve hostname first
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return f"ERROR: Could not resolve hostname {host}"

    try:
        # Windows ping
        res = subprocess.run(
            ["ping", "-n", str(count), "-w", "1000", ip],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="cp850"
        )
        return res.stdout
    except subprocess.TimeoutExpired:
        return f"ERROR: Ping timeout to {ip}"
    except Exception as e:
        return f"ERROR: Ping failed: {e}"

def net_list_shares(host: str) -> str:
    """Lists accessible SMB shares on a given host."""
    host = host.lstrip("\\\\")
    try:
        res = subprocess.run(
            ["net", "view", f"\\\\{host}"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="cp850"
        )
        if res.returncode != 0:
            return f"ERROR: Command failed with code {res.returncode}. Output: {res.stderr}\n{res.stdout}"
        return res.stdout
    except subprocess.TimeoutExpired:
        return f"ERROR: net view timeout to {host}"
    except Exception as e:
        return f"ERROR: net view failed: {e}"

def net_dns_lookup(host: str) -> str:
    """Performs DNS resolution (IP from name)."""
    try:
        ip = socket.gethostbyname(host)
        return f"DNS Lookup: {host} -> {ip}"
    except Exception as e:
        return f"ERROR resolving DNS for {host}: {e}"

def net_http_status(url: str) -> str:
    """Quickly checks HTTP(S) availability of a URL."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return f"HTTP {response.getcode()} OK: {url}"
    except Exception as e:
        return f"ERROR checking HTTP status for {url}: {e}"

def net_connect_share(host: str, share: str, drive_letter: str = "", username: str = "", password: str = "") -> str:
    """Verbindet eine SMB-Freigabe (optional als Netzlaufwerk). Nutzt 'net use'."""
    host = host.lstrip("\\").strip()
    share = share.strip("\\").strip()
    unc = f"\\\\{host}\\{share}"
    cmd = ["net", "use"]
    if drive_letter:
        letter = drive_letter.rstrip(":").upper()
        cmd.append(f"{letter}:")
    cmd.append(unc)
    if password:
        cmd.append(password)
    if username:
        cmd.extend([f"/user:{username}"])
    cmd.append("/persistent:no")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding="cp850")
        if res.returncode == 0:
            mapped = f" als {drive_letter.rstrip(':').upper()}:" if drive_letter else ""
            return f"Verbunden: {unc}{mapped}"
        return f"Fehler (Code {res.returncode}): {(res.stderr or res.stdout).strip()}"
    except subprocess.TimeoutExpired:
        return f"ERROR: Timeout beim Verbinden mit {unc}"
    except Exception as e:
        return f"ERROR: {e}"
