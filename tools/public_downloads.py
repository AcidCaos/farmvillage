"""Anonymous, pinned, resumable HTTPS downloads. No cookies, netrc or credentials."""
from __future__ import annotations
import hashlib
import os
import re
from pathlib import Path, PurePosixPath
import ssl
import time
import urllib.request
from urllib.parse import urlsplit
CHUNK = 1024 * 1024

def ordinary(value):
    path = Path(value).expanduser().absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Linked or traversing paths are refused: ' + str(path))
    return path

def child(root, relative):
    part = PurePosixPath(relative)
    if not part.parts or part.is_absolute() or '..' in part.parts or '\\' in str(relative):
        raise ValueError('Unsafe resource path: ' + str(relative))
    return ordinary(ordinary(root).joinpath(*part.parts))

def identity(path, entry):
    path = ordinary(path)
    if not path.is_file() or path.stat().st_size != entry['bytes']:
        return False
    names = [x for x in ('sha256', 'sha1', 'md5') if entry.get(x)]
    if not names and not entry.get('gitBlob'):
        raise ValueError('A pinned download requires a digest')
    digests = {x: hashlib.new(x) for x in names}
    if entry.get('gitBlob'):
        digests['gitBlob'] = hashlib.sha1(('blob %d\0' % entry['bytes']).encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            for digest in digests.values():
                digest.update(block)
    return all(digest.hexdigest() == entry[name] for name, digest in digests.items())

def https_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError('Downloads require ordinary anonymous HTTPS URLs')
    return url

class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').is_file() else None)))

def download(url, destination, entry, *, report=print, open_url=None):
    https_url(url)
    destination = ordinary(destination)
    pins = {key: entry[key] for key in ('sha256', 'sha1', 'md5', 'gitBlob') if key in entry}
    if not pins or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{%d}' % {'sha256':64,'sha1':40,'md5':32,'gitBlob':40}[key], value) for key, value in pins.items()):
        raise ValueError('A valid pinned digest is required before downloading')
    if type(entry.get('bytes')) is not int or entry['bytes'] <= 0:
        raise ValueError('A positive pinned byte count is required')
    if identity(destination, entry):
        report('Verified cached ' + destination.name)
        return destination
    if destination.exists():
        raise ValueError('Existing download has a different identity; move it aside: ' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = ordinary(destination.with_name(destination.name + '.part'))
    if partial.exists() and (not partial.is_file() or partial.stat().st_size > entry['bytes']):
        raise ValueError('Invalid partial download: ' + str(partial))
    offset = partial.stat().st_size if partial.exists() else 0
    if offset == entry['bytes'] and identity(partial, entry):
        partial.rename(destination)
        return destination
    if offset == entry['bytes']:
        partial.unlink()
        offset = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'FarmVillage-public-installer/1', 'Accept-Encoding': 'identity', **({'Range': 'bytes=%d-' % offset} if offset else {})})
    open_url = open_url or opener().open
    report('Downloading ' + destination.name + (' (resuming at %d bytes)' % offset if offset else ''))
    with open_url(request, timeout=60) as response:
        status = response.status
        if status == 206:
            expected = 'bytes %d-%d/%d' % (offset, entry['bytes'] - 1, entry['bytes'])
            if response.headers.get('Content-Range') != expected:
                raise ValueError('The source returned an invalid resume range')
        elif status == 200:
            offset = 0
        else:
            raise ValueError('Unexpected download status: %s' % status)
        length = response.headers.get('Content-Length')
        if length and int(length) != entry['bytes'] - offset:
            raise ValueError('The source byte count differs from the pinned manifest')
        total, last = offset, 0.0
        with partial.open('ab' if offset else 'wb') as output:
            while True:
                block = response.read(min(CHUNK, entry['bytes'] - total + 1))
                if not block:
                    break
                if total + len(block) > entry['bytes']:
                    raise ValueError('Download exceeds its pinned size')
                import shutil
                if shutil.disk_usage(destination.parent).free < min(5 * 1024**3, entry['bytes']) + len(block):
                    raise OSError('Storage reserve reached; partial download retained for retry')
                output.write(block)
                total += len(block)
                if time.monotonic() - last > 5:
                    report('%s: %.1f%% (%d/%d bytes)' % (destination.name, 100 * total / entry['bytes'], total, entry['bytes']))
                    last = time.monotonic()
    if not identity(partial, entry):
        raise ValueError('Download incomplete or checksum mismatch; partial retained: ' + str(partial))
    partial.rename(destination)
    return destination
