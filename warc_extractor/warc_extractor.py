#!/usr/bin/env python3
"""
    warc-extractor, a simple command line tool for expanding warc files.
    Copyright (C) 2014  Ryan Chartier
    Portions (C) 2012 Internet Archive
    Added _main_interface function, disable duplication numbers. (C) 2024  FarmVillage Project

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.


warc.utils
~~~~~~~~~~

This file is part of warc

:copyright: (c) 2012 Internet Archive


warc.warc
~~~~~~~~~

Python library to work with WARC files.

:copyright: (c) 2012 Internet Archive

"""

from collections.abc import MutableMapping
from http.client import HTTPMessage
from urllib.parse import urlparse, unquote
from pprint import pprint
import os
import argparse
import mimetypes
import email.parser
import gzip
import datetime
import uuid
import re
import io
import hashlib

# ---------------------------------------------------
#                      warc.utils                  -
# ---------------------------------------------------
SEP = re.compile("[;:=]")


class CaseInsensitiveDict(MutableMapping):
    """Almost like a dictionary, but keys are case-insensitive.

        >>> d = CaseInsensitiveDict(foo=1, Bar=2)
        >>> d['foo']
        1
        >>> d['bar']
        2
        >>> d['Foo'] = 11
        >>> d['FOO']
        11
        >>> d.keys()
        ["foo", "bar"]
    """

    def __init__(self, *args, **kwargs):
        self._d = {}
        self.update(dict(*args, **kwargs))

    def __setitem__(self, name, value):
        self._d[name.lower()] = value

    def __getitem__(self, name):
        return self._d[name.lower()]

    def __delitem__(self, name):
        del self._d[name.lower()]

    def __eq__(self, other):
        return isinstance(other, CaseInsensitiveDict) and other._d == self._d

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)


class FilePart:
    """File interface over a part of file.

    Takes a file and length to read from the file and returns a file-object
    over that part of the file.
    """

    def __init__(self, fileobj, length):
        self.fileobj = fileobj
        self.length = length
        self.offset = 0
        self.buf = b''

    def read(self, size=-1):
        if size == -1:
            size = self.length

        if len(self.buf) >= size:
            content = self.buf[:size]
            self.buf = self.buf[size:]
        else:
            size = min(size, self.length - self.offset)
            content = self.buf + self.fileobj.read(size - len(self.buf))
            self.buf = b''
        self.offset += len(content)
        return content

    def unread(self, content):
        self.buf = content + self.buf
        self.offset -= len(content)

    def readline(self, size=1024):
        chunks = []
        chunk = self.read(size)
        while chunk and b"\n" not in chunk:
            chunks.append(chunk)
            chunk = self.read(size)

        if b"\n" in chunk:
            index = chunk.index(b"\n")
            self.unread(chunk[index + 1:])
            chunk = chunk[:index + 1]
        chunks.append(chunk)
        return b"".join(chunks)

    def __iter__(self):
        line = self.readline()
        while line:
            yield line
            line = self.readline()


class HTTPObject(CaseInsensitiveDict):
    """Small object to help with parsing HTTP warc entries"""

    def __init__(self, request_file):
        # Parse version line
        id_str_raw = request_file.readline()
        id_str = id_str_raw.decode("iso-8859-1")
        if "HTTP" not in id_str:
            # This is not an HTTP object.
            request_file.unread(id_str_raw)
            raise ValueError("Object is not HTTP.")

        words = id_str.split()
        command = path = status = error = version = None
        # If length is not 3 it is a bad version line.
        if len(words) >= 3:
            if words[1].isdigit():
                version = words[0]
                error = words[1]
                status = " ".join(words[2:])
            else:
                command, path, version = words

        self._id = {
            "vline": id_str_raw,
            "command": command,
            "path": path,
            "status": status,
            "error": error,
            "version": version,
        }

        self._header, self.hstring = self._parse_headers(request_file)
        super().__init__(self._header)
        self.payload = request_file
        self._content = None

    @staticmethod
    def _parse_headers(fp):
        """This is a modification of the python3 http.clint.parse_headers function."""
        headers = []
        while True:
            line = fp.readline(65536)
            headers.append(line)
            if line in (b'\r\n', b'\n', b''):
                break
        hstring = b''.join(headers)
        return email.parser.Parser(_class=HTTPMessage).parsestr(hstring.decode('iso-8859-1')), hstring

    def __repr__(self):
        return self.vline + str(self._header)

    def __getitem__(self, name):
        try:
            return super().__getitem__(name)
        except KeyError:
            value = name.lower()
            if value == "content_type":
                return self.content.type
            elif value in self.content:
                return self.content[value]
            elif value in self._id:
                return self._id[value]
            else:
                raise

    def reset(self):
        self.payload.unread(self.hstring)
        self.payload.unread(self._id['vline'])

    def write_to(self, f):
        f.write(self._id['vline'])
        f.write(self.hstring)
        f.write(self.payload.read())
        f.write(b"\r\n\r\n")
        f.flush()

    @property
    def content(self):
        if self._content is None:
            try:
                string = self._d["content-type"]
            except KeyError:
                string = ''
            self._content = ContentType(string)
        return self._content

    @property
    def vline(self):
        return self._id["vline"].decode("iso-8859-1")

    @property
    def version(self):
        return self._id["version"]

    def write_payload_to(self, fp):
        encoding = self._header.get("Transfer-Encoding", "None")
        if encoding == "chunked":
            found = b''
            length = int(str(self.payload.readline(), "iso-8859-1").rstrip(), 16)
            while length > 0:
                found += self.payload.read(length)
                self.payload.readline()
                length = int(str(self.payload.readline(), "iso-8859-1").rstrip(), 16)
        else:
            length = int(self._header.get("Content-Length", -1))
            found = self.payload.read(length)

        fp.write(found)


class ContentType(CaseInsensitiveDict):
    def __init__(self, string):
        data = {}
        self.type = ''
        if string:
            _list = [i.strip() for i in string.lower().split(";")]
            self.type = _list[0]
            data["type"] = _list[0]
            for i in _list[1:]:
                test = [n.strip() for n in re.split(SEP, i)]
                # It's only a property if it has two elements.
                if len(test) > 1:
                    data[test[0]] = test[1]

        super().__init__(data)

    def __repr__(self):
        return self.type


# ---------------------------------------------------
#                      warc.warc                   -
# ---------------------------------------------------

class WARCHeader(CaseInsensitiveDict):
    """The WARC Header object represents the headers of a WARC record.

    It provides dictionary like interface for accessing the headers.

    The following mandatory fields are accessible also as attributes.

        * h.record_id == h['WARC-Record-ID']
        * h.content_length == int(h['Content-Length'])
        * h.date == h['WARC-Date']
        * h.type == h['WARC-Type']

    :params headers: dictionary of headers.
    :params defaults: If True, important headers like WARC-Record-ID,
                      WARC-Date, Content-Type and Content-Length are
                      initialized to automatically if not already present.

    """
    CONTENT_TYPES = dict(warcinfo='application/warc-fields',
                         response='application/http; msgtype=response',
                         request='application/http; msgtype=request',
                         metadata='application/warc-fields')

    KNOWN_HEADERS = {
        "type": "WARC-Type",
        "date": "WARC-Date",
        "record_id": "WARC-Record-ID",
        "ip_address": "WARC-IP-Address",
        "target_uri": "WARC-Target-URI",
        "warcinfo_id": "WARC-Warcinfo-ID",
        "request_uri": "WARC-Request-URI",
        "content_type": "Content-Type",
        "content_length": "Content-Length"
    }

    def __init__(self, headers, defaults=False):
        self.version = "WARC/1.0"
        super().__init__(headers)
        if defaults:
            self.init_defaults()

    def __repr__(self):
        return "<WARCHeader: type={}, record_id={}>".format(self.type, self.record_id)

    def init_defaults(self):
        """Initializes important headers to default values, if not already specified.

        The WARC-Record-ID header is set to a newly generated UUID.
        The WARC-Date header is set to the current datetime.
        The Content-Type is set based on the WARC-Type header.
        The Content-Length is initialized to 0.
        """
        if "WARC-Record-ID" not in self:
            self['WARC-Record-ID'] = "<urn:uuid:%s>" % uuid.uuid1()
        if "WARC-Date" not in self:
            self['WARC-Date'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        if "Content-Type" not in self:
            self['Content-Type'] = WARCHeader.CONTENT_TYPES.get(self.type, "application/octet-stream")

    def write_to(self, f):
        """Writes this header to a file, in the format specified by WARC.
        """
        f.write(self.version.encode() + b"\r\n")
        for name, value in self.items():
            name = name.title()
            # Use standard forms for commonly used patterns
            name = name.replace("Warc-", "WARC-").replace("-Ip-", "-IP-").replace("-Id", "-ID").replace("-Uri", "-URI")
            entry = "{}: {}\r\n".format(str(name), str(value)).encode()
            f.write(entry)

        # Header ends with an extra CRLF
        f.write(b"\r\n")

    @property
    def content_length(self):
        """The Content-Length header as int."""
        return int(self['Content-Length'])

    @property
    def type(self):
        """The value of WARC-Type header."""
        return self['WARC-Type']

    @property
    def record_id(self):
        """The value of WARC-Record-ID header."""
        return self['WARC-Record-ID']

    @property
    def date(self):
        """The value of WARC-Date header."""
        return self['WARC-Date']


class WARCRecord(object):
    """The WARCRecord object represents a WARC Record.
    """

    def __init__(self, header=None, payload=None, headers=None, defaults=True):
        """Creates a new WARC record.
        """
        if headers is None:
            headers = {}

        if header is None and defaults is True:
            headers.setdefault("WARC-Type", "response")

        self.header = header or WARCHeader(headers, defaults=True)

        if defaults is True and 'Content-Length' not in self.header:
            if payload:
                self.header['Content-Length'] = len(payload)
            else:
                self.header['Content-Length'] = "0"

        if defaults is True and 'WARC-Payload-Digest' not in self.header:
            self.header['WARC-Payload-Digest'] = self._compute_digest(payload)

        if isinstance(payload, str):
            payload = payload.encode()
        if isinstance(payload, bytes):
            payload = io.BytesIO(payload)

        self.payload = payload
        self._http = None
        self._content = None

    @staticmethod
    def _compute_digest(payload):
        return "sha1:" + hashlib.sha1(payload).hexdigest()

    def write_to(self, f):
        self.header.write_to(f)
        if self.http:
            self.http.reset()
        f.write(self.payload.read())
        f.write(b"\r\n")
        f.write(b"\r\n")
        f.flush()

    @property
    def content(self):
        if self._content is None:
            try:
                string = self.header["content-type"]
            except KeyError:
                string = ''
            self._content = ContentType(string)
        return self._content

    @property
    def http(self):
        if self._http is None:
            if 'application/http' in self.header['content-type']:
                self._http = HTTPObject(self.payload)
            else:
                self._http = False
        return self._http

    @property
    def type(self):
        """Record type"""
        return self.header.type

    @property
    def url(self):
        """The value of the WARC-Target-URI header if the record is of type "response"."""
        return self.header.get('WARC-Target-URI')

    @property
    def ip_address(self):
        """The IP address of the host contacted to retrieve the content of this record.

        This value is available from the WARC-IP-Address header."""
        return self.header.get('WARC-IP-Address')

    @property
    def date(self):
        """UTC timestamp of the record."""
        return self.header.get("WARC-Date")

    @property
    def checksum(self):
        return self.header.get('WARC-Payload-Digest')

    def __getitem__(self, name):
        try:
            return self.header[name]
        except KeyError:
            if name == "content_type":
                return self.content.type
            elif name in self.content:
                return self.content[name]

    def __setitem__(self, name, value):
        self.header[name] = value

    def __contains__(self, name):
        return name in self.header

    def __repr__(self):
        return "<WARCRecord: type=%r record_id=%s>" % (self.type, self['WARC-Record-ID'])

    @staticmethod
    def from_response(response):
        """Creates a WARCRecord from given response object.

        This must be called before reading the response. The response can be
        read after this method is called.

        :param response: An instance of :class:`requests.models.Response`.
        """
        # Get the httplib.HTTPResponse object
        http_response = response.raw._original_response

        # HTTP status line, headers and body as strings
        status_line = "HTTP/1.1 %d %s" % (http_response.status, http_response.reason)
        headers = str(http_response.msg)
        body = http_response.read()

        # Monkey-patch the response object so that it is possible to read from it later.
        response.raw._fp = io.BytesIO(body)

        # Build the payload to create warc file.
        payload = status_line + "\r\n" + headers + "\r\n" + body

        headers = {
            "WARC-Type": "response",
            "WARC-Target-URI": response.request.url.encode('utf-8')
        }
        return WARCRecord(payload=payload, headers=headers)


class WARCFile:
    def __init__(self, filename=None, mode=None, fileobj=None, compress=None):
        if fileobj is None:
            fileobj = open(filename, mode or "rb")
            mode = fileobj.mode
        # initiaize compress based on filename, if not already specified
        if compress is None and filename and filename.endswith(".gz"):
            compress = True

        if compress:
            fileobj = gzip.open(fileobj, mode)

        self.fileobj = fileobj
        self._reader = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __iter__(self):
        return iter(self.reader)

    @property
    def reader(self):
        if self._reader is None:
            self._reader = WARCReader(self.fileobj)
        return self._reader

    def write_record(self, warc_record):
        """Adds a warc record to this WARC file.
        """
        warc_record.write_to(self.fileobj)

    def read_record(self):
        """Reads a warc record from this WARC file."""
        return self.reader.read_record()

    def close(self):
        self.fileobj.close()

    def tell(self):
        """Returns the file offset.
        """
        return self.fileobj.tell()


class WARCReader:
    RE_VERSION = re.compile(r"WARC/(\d+.\d+)\r\n")
    RE_HEADER = re.compile(r"([a-zA-Z_\-]+): *(.*)\r\n")
    SUPPORTED_VERSIONS = ["1.0"]

    def __init__(self, fileobj):
        self.fileobj = fileobj
        self.current_payload = None

    def read_header(self, fileobj):
        version_line = fileobj.readline().decode("utf-8")
        if not version_line:
            return None

        m = self.RE_VERSION.match(version_line)
        if not m:
            raise IOError("Bad version line: %r" % version_line)
        version = m.group(1)
        if version not in self.SUPPORTED_VERSIONS:
            raise IOError("Unsupported WARC version: %s" % version)

        headers = {}
        while True:
            line = fileobj.readline().decode("utf-8")
            if line == "\r\n":  # end of headers
                break
            m = self.RE_HEADER.match(line)
            if not m:
                raise IOError("Bad header line: %r" % line)
            name, value = m.groups()
            headers[name] = value
        return WARCHeader(headers)

    @staticmethod
    def expect(fileobj, expected_line, message=None):
        line = fileobj.readline().decode("utf-8")
        if line != expected_line:
            message = message or "Expected %r, found %r" % (expected_line, line)
            raise IOError(message)

    def finish_reading_current_record(self):
        # consume the footer from the previous record
        if self.current_payload:
            # consume all data from the current_payload before moving to next record
            self.current_payload.read()
            self.expect(self.current_payload.fileobj, "\r\n")
            self.expect(self.current_payload.fileobj, "\r\n")
            self.current_payload = None

    def read_record(self):
        self.finish_reading_current_record()
        fileobj = self.fileobj

        header = self.read_header(fileobj)
        if header is None:
            return None

        self.current_payload = FilePart(fileobj, header.content_length)
        record = WARCRecord(header, self.current_payload, defaults=False)
        return record

    @staticmethod
    def _read_payload(fileobj, content_length):
        size = 0
        while size < content_length:
            chunk_size = min(1024, content_length - size)
            chunk = fileobj.read(chunk_size)
            size += chunk_size
            yield chunk

    def __iter__(self):
        record = self.read_record()
        while record is not None:
            yield record
            record = self.read_record()


# ---------------------------------------------------
#                 Extractor                        -
# ---------------------------------------------------

counts = {}


class FilterObject:
    """Basic object for storing filters."""

    def __init__(self, string):
        self.result = True
        if string[0] == "!":
            self.result = False
            string = string[1:]

        _list = string.lower().split(":")

        self.http = (_list[0] == 'http')
        if self.http:
            del _list[0]

        self.k = _list[0]
        self.v = _list[1]


def inc(obj, header=None, dic=None):
    """Short script for counting entries."""
    if header:
        try:
            obj = obj[header]
        except KeyError:
            obj = None

    holder = counts
    if dic:
        if dic not in counts:
            counts[dic] = {}
        holder = counts[dic]

    if obj in holder:
        holder[obj] += 1
    else:
        holder[obj] = 1


def warc_records(string, path):
    """Iterates over warc records in path."""
    for filename in os.listdir(path):
        if re.search(string, filename) and ".warc" in filename:
            print(" * parsing", filename)
            with WARCFile(path + filename) as warc_file:
                for record in warc_file:
                    yield record


def check_filter(filters, record):
    """Check record against filters."""
    for i in filters:
        if i.http:
            if not record.http:
                return False
            value = record.http
        else:
            value = record.header

        string = value.get(i.k, None)
        if not string or (i.v in string) != i.result:
            return False
    return True


def parse(args):
    # Clear output warc file.
    if args.dump == "warc":
        if args.silence:
            print("Recording", args.dump, "to", args.output + ".")
        with open(args.output_path + args.output, "wb"):
            pass

    for record in warc_records(args.string, args.path):
        try:
            # Filter out unwanted entries.
            if not check_filter(args.filter, record):
                continue

            # Increment Index counters.
            if args.silence:
                inc("records")
                inc(record, "warc-type", "types")
                inc(record, "content_type", "warc-content")
                if record.http:
                    inc(record.http, "content_type", "http-content")
                    inc(record.http, "error", "status")

            # Dump records to file.
            if args.dump == "warc":
                with open(args.output_path + args.output, "ab") as output:
                    record.write_to(output)

            if args.dump == "content":
                url = urlparse(unquote(record['WARC-Target-URI']))

                # Set up folder
                index = url.path.rfind("/") + 1
                file = url.path[index:]
                path = url.path[:index]

                # Process filename
                if "." not in file:
                    path += file
                    if not path.endswith("/"):
                        path += "/"

                    file = 'index.html'

                # Final fixes.
                path = path.replace(".", "-")
                host = url.hostname.replace('www.', '', 1)
                path = args.output_path + host + path

                # Create new directories
                if not os.path.exists(path):
                    try:
                        os.makedirs(path)
                    except OSError:
                        path = "/".join([i[:25] for i in path.split("/")])
                        os.makedirs(path)

                # Test if file has a proper extension.
                index = file.index(".")
                suffix = file[index:]
                content = record.http.get("content_type", "")
                slist = mimetypes.guess_all_extensions(content)
                if suffix not in slist:
                    # Correct suffix if we can.
                    suffix = mimetypes.guess_extension(content)
                    if suffix:
                        file = file[:index] + suffix
                    else:
                        inc(record.http, "content_type", "unknown mime type")

                # Check for gzip compression.
                if record.http.get("content-encoding", None) == "gzip":
                    file += ".gz"

                path += file

                # If Duplicate file then insert numbers
                # index = path.rfind(".")
                # temp = path
                # n = 0
                # while os.path.isfile(temp):
                #     n += 1
                #     temp = path[:index] + "(" + str(n) + ")" + path[index:]
                # path = temp

                # Write file.
                try:
                    with open(path, 'wb') as fp:
                        record.http.write_payload_to(fp)
                except OSError as e:
                    print("unable to save file due to operating system error:", e)

        except Exception:
            if args.error:
                if args.silence:
                    print("Error in record. Recording to error.warc.")
                with open(args.output_path + "error.warc", "ab") as fp:
                    record.write_to(fp)
            else:
                raise

    # print results
    if args.silence:
        print("-----------------------------")
        for i in counts:
            print("\nCount of {}.".format(i))
            pprint(counts[i])


def main():
    parser = argparse.ArgumentParser(description='Extracts attributes from warc files.')
    parser.add_argument("filter", nargs='*',
                        help="Attributes to filter by. Entries that do not contain filtered elements are ignored. "
                             "Example: warc-type:response, would ignore all warc entries that are not responses. "
                             "Attributes in an HTTP object should be prefixed by 'http'. Example, http:error:200.")
    parser.add_argument("-silence", action="store_false", help="Silences output of warc data.")
    parser.add_argument("-error", action="store_true",
                        help="Silences most errors and records problematic warc entries to error.warc.")
    parser.add_argument("-string", default="",
                        help="Regular expression to limit parsed warc files. Defaults to empty string.")
    parser.add_argument("-path", default="./", help="Path to folder containing warc files. Defaults to current folder.")
    parser.add_argument("-output_path", default="data/",
                        help="Path to folder to dump content files. Defaults to data/ folder.")
    parser.add_argument("-output", default="output.warc",
                        help="File to output warc contents. Defaults to 'output.warc'.")
    parser.add_argument("-dump", choices=['warc', 'content'], type=str,
                        help="Dumps all entries that survived filter. 'warc' creates a filtered warc file. "
                             "'content' tries to reproduce file structure of archived websites.")
    args = parser.parse_args()

    if args.path[-1] != "/":
        args.path += "/"

    if args.output_path[-1] != "/":
        args.output_path += "/"

    if args.dump:
        if not os.path.exists(args.output_path):
            os.makedirs(args.output_path)

    # Forced filters
    filters = list(args.filter)
    if args.dump == "content":
        filters.append("warc-type:response")
        filters.append("content-type:application/http")

    args.filter = [FilterObject(i) for i in filters]

    args.string = re.compile(args.string)
    parse(args)

def _main_interface(filter=[], silence=True, error=False, string="", path="./", output_path="data/", output="output.warc", dump="content"):
    args = argparse.Namespace()
    args.filter = filter
    args.silence = silence
    args.error = error
    args.string = string
    args.path = path
    args.output_path = output_path
    args.output = output
    args.dump = dump
    
    if args.path[-1] != "/":
        args.path += "/"

    if args.output_path[-1] != "/":
        args.output_path += "/"

    if args.dump:
        if not os.path.exists(args.output_path):
            os.makedirs(args.output_path)

    # Forced filters
    filters = list(args.filter)
    if args.dump == "content":
        filters.append("warc-type:response")
        filters.append("content-type:application/http")

    args.filter = [FilterObject(i) for i in filters]

    args.string = re.compile(args.string)
    parse(args)

if __name__ == "__main__":
    main()
