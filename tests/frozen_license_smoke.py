"""Exercise the real frozen license transport without activating a real key.

Run explicitly; this test-only module is not imported by the shipped app.
The HTTPS failure case uses a loopback CONNECT proxy with a fresh untrusted
certificate, while the app continues to request its fixed official endpoint.
No certificate is installed in Windows and no verification setting is relaxed.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import tempfile
import threading


class SmokeFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def file_record(path):
    contents = path.read_bytes()
    return {'name': path.name, 'bytes': len(contents),
            'sha256': hashlib.sha256(contents).hexdigest()}


def python_tls_sources():
    import _ssl

    directory = Path(_ssl.__file__).resolve().parent
    sources = [directory / '_ssl.pyd', directory / 'libcrypto-3-x64.dll',
               directory / 'libssl-3-x64.dll']
    ssl_source = Path(importlib.util.find_spec('ssl').origin).resolve()
    policy_name = 'codex-rejected-cas.pem'
    if policy_name.encode('ascii') in ssl_source.read_bytes():
        sources.append(ssl_source.parent / policy_name)
    return sources


def tls_layout(executable, layout='auto'):
    require(layout in ('auto', 'onedir', 'onefile'), 'Unknown frozen TLS layout')
    if layout == 'auto':
        return 'onedir' if (executable.parent / '_internal').is_dir() else 'onefile'
    return layout


def verify_bundled_tls(executable, layout='auto'):
    sources = python_tls_sources()
    layout = tls_layout(executable, layout)
    archive = None
    if layout == 'onefile':
        # Test dependency only: the product never imports PyInstaller. Inspect
        # bytes in the EXE, not a neighboring folder or a previous extraction.
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(executable))
        entries = {name.replace('\\', '/'): name for name in archive.toc}
        require('onefile.marker' in entries, 'EXE is not a marked onefile distribution')
    records = []
    for source in sources:
        require(source.is_file(), 'Required build Python TLS runtime file is missing')
        expected = file_record(source)
        if archive is None:
            target = executable.parent / '_internal' / source.name
            require(target.is_file(), 'Required TLS runtime file is missing')
            bundled = file_record(target)
        else:
            require(source.name in entries, 'Required embedded TLS runtime file is missing')
            contents = archive.extract(entries[source.name])
            bundled = {'name': source.name, 'bytes': len(contents),
                       'sha256': hashlib.sha256(contents).hexdigest()}
            # A foreign copy under a second extraction path must not be hidden
            # by a valid top-level DLL (Windows DLL loading is name-based).
            matches = [name for name in entries if name.rsplit('/', 1)[-1].lower() == source.name.lower()]
            require(matches == [source.name], 'Embedded TLS runtime has ambiguous copies')
        require(expected == bundled, 'Bundled TLS runtime differs from build Python')
        records.append(bundled)
    return records


def proxy_environment(environment, port):
    result = {key: value for key, value in environment.items()
              if not key.lower().endswith('_proxy')}
    proxy = f'http://127.0.0.1:{port}'
    result.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, NO_PROXY='')
    return result


def run_probe(executable, output, name, proxy_port=None):
    folder = output / name
    folder.mkdir()
    local, roaming = folder / 'local', folder / 'roaming'
    local.mkdir()
    roaming.mkdir()
    environment = dict(os.environ, LOCALAPPDATA=str(local), APPDATA=str(roaming))
    environment.pop('EOINGPDF_NETWORK_DIAG', None)
    if proxy_port is not None:
        environment = proxy_environment(environment, proxy_port)
    report_path = folder / 'probe.json'
    nonce = secrets.token_hex(16)
    process = subprocess.run(
        [str(executable), '--license-network-check', str(report_path), nonce],
        cwd=str(folder), env=environment, capture_output=True, timeout=45,
    )
    # Never copy arbitrary stdout/stderr, credentials or exception text to logs.
    require(report_path.is_file(), 'Frozen process did not produce a probe report')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    require(report.get('nonce') == nonce, 'Probe report nonce mismatch')
    require(report.get('frozen') is True, 'Probe did not execute inside the frozen EXE')
    for flag in ('certificate_verification', 'hostname_verification',
                 'https_connection', 'https_handler'):
        require(report.get(flag) is True, 'Verified HTTPS runtime check failed')
    require(not list(local.rglob('license.dat')) and not list(roaming.rglob('license.dat')),
            'Connectivity check unexpectedly wrote license state')
    return {'name': name, 'returncode': process.returncode, 'report': report,
            'isolated_appdata': True, 'license_state_created': False}


def untrusted_server_context(output):
    # cryptography is a test dependency only. The key is generated solely for
    # this loopback server, loaded in memory and removed from disk immediately.
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'app.nal.la')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(identity).issuer_name(identity)
                   .public_key(private_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5))
                   .not_valid_after(now + timedelta(hours=2))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName('app.nal.la')]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(private_key, hashes.SHA256()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    with tempfile.TemporaryDirectory(prefix='loopback-tls-', dir=output) as temporary:
        directory = Path(temporary).resolve()
        require(directory.parent == output.resolve(), 'Unexpected TLS temporary directory')
        cert_path, key_path = directory / 'certificate.pem', directory / 'private-key.pem'
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        try:
            context.load_cert_chain(cert_path, key_path)
        finally:
            key_path.unlink(missing_ok=True)
            cert_path.unlink(missing_ok=True)
    return context


class LoopbackConnectProxy:
    def __init__(self, context):
        self.context = context
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(20)
        self.port = self.listener.getsockname()[1]
        self.events = {'connect_requested': False, 'target_is_license_server': False,
                       'tls_handshake_rejected': False, 'tls_handshake_succeeded': False}
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *unused):
        self.listener.close()
        self.thread.join(timeout=5)

    def serve(self):
        try:
            connection, _ = self.listener.accept()
            with connection:
                connection.settimeout(15)
                header = bytearray()
                while b'\r\n\r\n' not in header:
                    chunk = connection.recv(4096)
                    if not chunk or len(header) + len(chunk) > 65536:
                        return
                    header.extend(chunk)
                first_line = bytes(header).split(b'\r\n', 1)[0].split(b' ')
                self.events['connect_requested'] = first_line[0] == b'CONNECT'
                self.events['target_is_license_server'] = len(first_line) >= 2 and first_line[1] == b'app.nal.la:443'
                if not all((self.events['connect_requested'], self.events['target_is_license_server'])):
                    return
                connection.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                try:
                    with self.context.wrap_socket(connection, server_side=True):
                        self.events['tls_handshake_succeeded'] = True
                except ssl.SSLError as error:
                    self.events['tls_handshake_rejected'] = True
                    # A normalized TLS alert is safe; do not retain request or exception text.
                    self.events['alert'] = error.reason
        except Exception as error:
            self.events['error_type'] = type(error).__name__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--layout', choices=('auto', 'onedir', 'onefile'), default='auto')
    arguments = parser.parse_args()
    executable = Path(arguments.exe).resolve(strict=True)
    output = Path(arguments.output).resolve()
    require(executable.is_file(), 'Frozen EXE not found')
    output.mkdir(parents=True, exist_ok=False)
    summary = {'ok': False, 'tests': [], 'activation_performed': False,
               'windows_certificate_store_changed': False}
    try:
        summary['tls_layout'] = tls_layout(executable, arguments.layout)
        summary['bundled_tls'] = verify_bundled_tls(executable, summary['tls_layout'])
        live = run_probe(executable, output, 'live-invalid-key')
        summary['tests'].append(live)
        report = live['report']
        require(live['returncode'] == 0 and report.get('ok') is True,
                'Live license endpoint probe failed')
        require(all(report.get(flag) is True for flag in
                    ('server_json', 'server_rejected_probe', 'product_matches')),
                'Server did not return a genuine invalid-key JSON result')
        # A bound, non-listening socket reserves a local port while ensuring
        # the client receives connection refusal, with no external request.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as refusal:
            refusal.bind(('127.0.0.1', 0))
            offline = run_probe(executable, output, 'connection-refused', refusal.getsockname()[1])
        summary['tests'].append(offline)
        require(offline['returncode'] == 1 and offline['report'].get('ok') is False
                and offline['report'].get('error_kind') == 'connection',
                'Connection refusal was not reported as a connection error')
        with LoopbackConnectProxy(untrusted_server_context(output)) as proxy:
            rejected = run_probe(executable, output, 'untrusted-certificate', proxy.port)
            proxy.thread.join(timeout=5)
        rejected['loopback_proxy'] = proxy.events
        summary['tests'].append(rejected)
        require(rejected['returncode'] == 1 and rejected['report'].get('ok') is False
                and rejected['report'].get('error_kind') == 'tls',
                'Untrusted certificate was not rejected as a TLS error')
        require(proxy.events['connect_requested'] and proxy.events['target_is_license_server']
                and proxy.events['tls_handshake_rejected'] and not proxy.events['tls_handshake_succeeded'],
                'Real frozen client did not reject the loopback certificate handshake')
        require(proxy.events.get('alert') in ('TLSV1_ALERT_UNKNOWN_CA', 'SSLV3_ALERT_CERTIFICATE_UNKNOWN'),
                'TLS failure was not a certificate trust rejection')
        summary['ok'] = True
    except SmokeFailure as error:
        summary['failure'] = str(error)  # Only our fixed, non-sensitive assertions.
    except Exception as error:
        summary['failure_type'] = type(error).__name__
    with (output / 'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'ok': summary['ok'], 'cases': [case['name'] for case in summary['tests']],
                      'summary': str(output / 'summary.json')}, ensure_ascii=False))
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
