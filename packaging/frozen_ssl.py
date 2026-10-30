"""Keep Windows frozen TLS binaries from the Python that supplies _ssl.pyd.

PyInstaller can otherwise resolve a same-named OpenSSL DLL from another app
on PATH. These helpers run only while building, not in the shipped application.
"""
from importlib.util import find_spec
from pathlib import Path


SSL_DLL_NAMES = ('libcrypto-3-x64.dll', 'libssl-3-x64.dll')
SSL_POLICY_FILE = 'codex-rejected-cas.pem'


def python_ssl_binaries(ssl_extension=None):
    """Return explicit Analysis inputs; never search PATH for OpenSSL."""
    if ssl_extension is None:
        module = find_spec('_ssl')
        if module is None or not module.origin:
            raise RuntimeError('The build Python does not provide _ssl.pyd')
        ssl_extension = module.origin
    extension = Path(ssl_extension).resolve(strict=True)
    if not extension.is_file():
        raise RuntimeError('The build Python _ssl extension is not a file')
    directory = extension.parent
    binaries = []
    for name in SSL_DLL_NAMES:
        source = (directory / name).resolve(strict=True)
        if not source.is_file() or source.parent != directory:
            raise RuntimeError(f'OpenSSL must be supplied beside _ssl.pyd: {name}')
        binaries.append((str(source), '.'))
    return binaries


def python_ssl_data(ssl_module=None):
    """Preserve the build runtime's referenced certificate rejection policy.

    Some Python distributions load this file from beside ssl.py whenever an
    SSLContext is created. Freezing the module alone loses that dependency.
    Ordinary CPython does not reference this file and needs no added data.
    """
    if ssl_module is None:
        module = find_spec('ssl')
        if module is None or not module.origin:
            raise RuntimeError('The build Python does not provide ssl.py')
        ssl_module = module.origin
    source = Path(ssl_module).resolve(strict=True)
    if not source.is_file():
        raise RuntimeError('The build Python ssl module is not a file')
    if SSL_POLICY_FILE.encode('ascii') not in source.read_bytes():
        return []
    policy = (source.parent / SSL_POLICY_FILE).resolve(strict=True)
    if not policy.is_file() or policy.parent != source.parent:
        raise RuntimeError('SSL certificate policy must be supplied beside ssl.py')
    return [(str(policy), '.')]


def pin_ssl_binaries(entries, python_binaries):
    """Replace Analysis OpenSSL resolutions with the canonical Python pair.

    Remove every same-named copy, including nested/uppercase destinations,
    because a foreign DLL must not survive COLLECT under a second path.
    """
    canonical = {}
    for source, destination in python_binaries:
        source = Path(source).resolve(strict=True)
        name = source.name.lower()
        if destination != '.' or name not in SSL_DLL_NAMES or not source.is_file():
            raise RuntimeError('Invalid canonical Python OpenSSL binary')
        if name in canonical:
            raise RuntimeError(f'Duplicate canonical Python OpenSSL binary: {name}')
        canonical[name] = source
    if set(canonical) != set(SSL_DLL_NAMES):
        raise RuntimeError('Both Python OpenSSL binaries are required')
    if len({source.parent for source in canonical.values()}) != 1:
        raise RuntimeError('Python OpenSSL binaries must come from one directory')
    result = [entry for entry in entries
              if entry[0].replace('\\', '/').rsplit('/', 1)[-1].lower() not in canonical]
    result.extend((name, str(canonical[name]), 'BINARY') for name in SSL_DLL_NAMES)
    return result
