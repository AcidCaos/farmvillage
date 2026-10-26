"""Small synthetic public-download/WARC contracts; never original game downloads."""
from __future__ import annotations
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TOOLS=Path(__file__).resolve().parent
sys.path.insert(0,str(TOOLS))
import public_downloads as downloads
import resource_pipeline as pipeline


def record(name, body=b'original fixture', *, host='zynga1-a.akamaihd.net', status=200, extra=b''):
    response=b'HTTP/1.1 '+str(status).encode()+b' OK\r\n'+extra+b'Content-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
    target='https://'+host+'/farmville/assets/hashed/assets/'+name
    return b'WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: '+target.encode()+b'\r\nContent-Length: '+str(len(response)).encode()+b'\r\n\r\n'+response+b'\r\n\r\n'


class Response(io.BytesIO):
    def __init__(self,payload,status=200,headers=None):
        super().__init__(payload)
        self.status=status
        self.headers=headers or {'Content-Length':str(len(payload))}


class ResourcePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fv-pipeline-fixture-',dir='/private/tmp' if Path('/private/tmp').is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve()
        self.source=self.base/'source';self.source.mkdir()
        (self.source/'SOURCE_MANIFEST.json').write_text('{"synthetic":true}\n')
        self.root_patch=mock.patch.object(pipeline,'ROOT',self.source);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.pack=pipeline.own_target(self.base/'pack',self.source)
    def archive(self,payload):
        archive=self.base/'fixture.warc.gz'
        archive.write_bytes(gzip.compress(payload,mtime=0))
        return archive
    def entry(self,payload):
        return {'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    def extract_fixture(self):
        bodies={'Environment/fixture.bin':b'environment fixture','xpromoSupport/fixture.bin':b'xpromo fixture','crops/nested/fixture.png':b'fixture raster'}
        archive=self.archive(b''.join(record(name,body) for name,body in bodies.items())+record('ignored.bin',host='example.invalid')+record('missing.bin',status=404))
        with contextlib.redirect_stdout(io.StringIO()):
            count=pipeline.extract_archive(archive,self.pack,reserve=0)
        self.assertEqual(count,3)
        pipeline.export_art_manifest(self.pack)
        return bodies
    def test_synthetic_warc_extracts_resumes_and_seals_exact_original_bytes(self):
        bodies=self.extract_fixture()
        for name,payload in bodies.items():self.assertEqual((self.pack/'assets'/name).read_bytes(),payload)
        self.assertFalse((self.pack/'assets/ignored.bin').exists())
        self.assertFalse((self.pack/'assets/missing.bin').exists())
        runtime=self.pack/'Runtime';runtime.mkdir();(runtime/'server.py').write_text('# reviewed synthetic source\n')
        state=pipeline.seal(self.pack,'server')
        self.assertEqual(state['active_worlds'],16)
        self.assertEqual(state['retired_worlds'],['glen','hlights'])
        self.assertEqual(pipeline.check_pack(self.pack),state)
        # A repeated extraction verifies existing bytes and keeps one database row per path.
        self.extract_fixture()
        with sqlite3.connect(self.pack/'artwork.sqlite3') as db:self.assertEqual(db.execute('select count(*) from files').fetchone()[0],3)
        self.assertEqual(pipeline.check_pack(self.pack),state)
    def test_seal_detects_changed_artwork_and_runtime_source(self):
        bodies=self.extract_fixture();runtime=self.pack/'Runtime';runtime.mkdir();script=runtime/'server.py';script.write_text('fixture')
        pipeline.seal(self.pack,'server')
        asset=self.pack/'assets'/next(iter(bodies));original=asset.read_bytes();asset.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Artwork differs'):pipeline.check_pack(self.pack)
        asset.write_bytes(original);script.write_text('changed')
        with self.assertRaisesRegex(ValueError,'Resource pack differs'):pipeline.check_pack(self.pack)
    def test_pack_refuses_unlisted_runtime_or_native_executables(self):
        self.extract_fixture();runtime=self.pack/'Runtime';runtime.mkdir();(runtime/'server.py').write_text('fixture')
        (self.pack/'native').mkdir()
        pipeline.seal(self.pack,'mac')
        for relative in ('Runtime/extra.py','native/extra.sh'):
            path=self.pack/relative;path.write_text('# unrelated executable\n');path.chmod(0o755)
            with self.subTest(relative=relative),self.assertRaisesRegex(ValueError,'unlisted files'):
                pipeline.check_pack(self.pack)
            path.unlink()
        self.assertEqual(pipeline.check_pack(self.pack)['audience'],'mac')
    def test_pack_refuses_a_different_current_source_manifest(self):
        self.extract_fixture();runtime=self.pack/'Runtime';runtime.mkdir();(runtime/'server.py').write_text('fixture')
        pipeline.seal(self.pack,'server')
        manifest=self.source/'SOURCE_MANIFEST.json';original=manifest.read_bytes()
        manifest.write_text('{"synthetic":"new release"}\n')
        with self.assertRaisesRegex(ValueError,'different source release'):
            pipeline.check_pack(self.pack)
        manifest.write_bytes(original)
        self.assertEqual(pipeline.check_pack(self.pack)['status'],'complete')
    def test_gzip_and_chunked_http_artwork_are_decoded(self):
        wanted=b'fixture original HTTP bytes'
        chunked=('%x\r\n'%len(wanted)).encode()+wanted+b'\r\n0\r\n\r\n'
        archive=self.archive(record('Environment/gzip.bin',gzip.compress(wanted),extra=b'Content-Encoding: gzip\r\n')+record('xpromoSupport/chunked.bin',chunked,extra=b'Transfer-Encoding: chunked\r\n'))
        self.assertEqual(pipeline.extract_archive(archive,self.pack,reserve=0),2)
        for name in ('Environment/gzip.bin','xpromoSupport/chunked.bin'):self.assertEqual((self.pack/'assets'/name).read_bytes(),wanted)
    def test_encoded_traversal_and_linked_asset_parents_are_refused(self):
        outside=self.base/'outside';outside.mkdir();(outside/'keep').write_bytes(b'preserved')
        for name in ('%2e%2e/private.bin','%2fprivate.bin','crops/%2e%2e/%2e%2e/private.bin'):
            with self.subTest(name=name),self.assertRaises(ValueError):pipeline.extract_archive(self.archive(record(name)),self.pack,reserve=0)
        assets=self.pack/'assets';assets.mkdir(exist_ok=True);(assets/'crops').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):pipeline.extract_archive(self.archive(record('crops/private.bin')),self.pack,reserve=0)
        self.assertEqual(list(outside.iterdir()),[outside/'keep'])
    def test_truncated_and_oversized_records_leave_no_artwork_output(self):
        cases=(b'WARC/1.0\r\nContent-Length: 134217729\r\n\r\n',record('crops/test.bin')[:-20])
        for index,payload in enumerate(cases):
            with self.subTest(index=index),self.assertRaises(ValueError):pipeline.extract_archive(self.archive(payload),self.pack,reserve=0)
        self.assertFalse((self.pack/'assets/crops/test.bin').exists())
    def test_target_ownership_rejects_source_system_unrelated_and_moved_markers(self):
        unrelated=self.base/'unrelated';unrelated.mkdir();(unrelated/'keep').write_bytes(b'preserved')
        for target in (self.source,self.source/'generated',Path('/usr/fv-fixture'),unrelated):
            with self.subTest(target=target),self.assertRaises(ValueError):pipeline.target_path(target,self.source)
        moved=self.base/'moved';self.pack.rename(moved)
        with self.assertRaisesRegex(ValueError,'marker'):pipeline.target_path(moved,self.source)
        self.assertEqual((unrelated/'keep').read_bytes(),b'preserved')
    def test_download_resumes_exact_range_and_reuses_verified_cache(self):
        payload=b'original public fixture bytes';destination=self.pack/'download.bin';partial=destination.with_name('download.bin.part');partial.write_bytes(payload[:7]);seen=[]
        def open_url(request,timeout):
            seen.append(request)
            return Response(payload[7:],206,{'Content-Length':str(len(payload)-7),'Content-Range':'bytes 7-%d/%d'%(len(payload)-1,len(payload))})
        downloads.download('https://example.invalid/original',destination,self.entry(payload),open_url=open_url,report=lambda _:None)
        self.assertEqual(destination.read_bytes(),payload);self.assertFalse(partial.exists());self.assertEqual(seen[0].get_header('Range'),'bytes=7-')
        with mock.patch.object(downloads,'opener',side_effect=AssertionError('cached file contacted network')):
            downloads.download('https://example.invalid/original',destination,self.entry(payload),report=lambda _:None)
    def test_download_restarts_when_source_ignores_range(self):
        payload=b'fixture bytes';destination=self.pack/'download.bin';destination.with_name('download.bin.part').write_bytes(b'old')
        downloads.download('https://example.invalid/original',destination,self.entry(payload),open_url=lambda *args,**kwargs:Response(payload),report=lambda _:None)
        self.assertEqual(destination.read_bytes(),payload)
    def test_download_rejects_wrong_resume_and_preserves_partial(self):
        payload=b'fixture bytes';destination=self.pack/'download.bin';partial=destination.with_name('download.bin.part');partial.write_bytes(payload[:3])
        with self.assertRaisesRegex(ValueError,'invalid resume range'):
            downloads.download('https://example.invalid/original',destination,self.entry(payload),open_url=lambda *args,**kwargs:Response(payload[3:],206,{'Content-Range':'bytes 0-2/3'}),report=lambda _:None)
        self.assertEqual(partial.read_bytes(),payload[:3]);self.assertFalse(destination.exists())
    def test_download_rejects_oversize_and_authentication_urls_before_writing(self):
        destination=self.pack/'download.bin'
        for url in ('http://example.invalid/file','https://user:password@example.invalid/file','https://example.invalid:8443/file'):
            with self.subTest(url=url),self.assertRaises(ValueError):downloads.download(url,destination,self.entry(b'fixture'),open_url=lambda *args,**kwargs:self.fail('network attempted'))
        with self.assertRaisesRegex(ValueError,'exceeds'):
            downloads.download('https://example.invalid/original',destination,self.entry(b'fixture'),open_url=lambda *args,**kwargs:Response(b'fixture extra',headers={'Ignored':'header'}),report=lambda _:None)
        self.assertFalse(destination.exists())
    def test_missing_or_invalid_download_digests_fail_before_any_network_or_output(self):
        destination=self.pack/'not-created/download.bin'
        pins=({}, {'sha256':''}, {'sha256':'bad'}, {'md5':False},
              {'gitBlob':'f'*39}, {'sha1':'G'*40}, {'sha256':'f'*64,'md5':'invalid'})
        opened=mock.Mock(side_effect=AssertionError('unpinned source contacted network'))
        with mock.patch.object(downloads,'opener',side_effect=AssertionError('unpinned download created opener')):
            for pin in pins:
                with self.subTest(pin=pin),self.assertRaisesRegex(ValueError,'valid pinned digest'):
                    downloads.download('https://example.invalid/original',destination,dict(pin,bytes=7),open_url=opened,report=lambda _:None)
        opened.assert_not_called()
        self.assertFalse(destination.parent.exists())
    def test_process_environment_strips_inherited_credentials_and_private_configs(self):
        inherited={'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','LC_ALL':'C','TZ':'UTC',
                   'HOME':'/private/tmp/unread-private-home','NETRC':'/private/tmp/unread-netrc',
                   'GH_TOKEN':'synthetic-secret','GITHUB_TOKEN':'synthetic-secret',
                   'AWS_ACCESS_KEY_ID':'synthetic-secret','AWS_SECRET_ACCESS_KEY':'synthetic-secret',
                   'OPENAI_API_KEY':'synthetic-secret','SSH_AUTH_SOCK':'/private/tmp/unread-agent',
                   'SSH_ASKPASS':'untrusted-helper','GIT_CONFIG_GLOBAL':'unread-private-config',
                   'GIT_ASKPASS':'untrusted-helper','PIP_INDEX_URL':'https://user:secret@example.invalid',
                   'CARGO_HOME':'/private/tmp/unread-cargo','RUSTUP_HOME':'/private/tmp/unread-rust',
                   'NPM_TOKEN':'synthetic-secret','npm_config_userconfig':'unread-private-npmrc',
                   'HTTP_PROXY':'https://user:secret@example.invalid','PYTHONPATH':'unread-private-code'}
        with mock.patch.dict(pipeline.os.environ,inherited,clear=True):
            env=pipeline.environment(self.pack)
            runner=mock.Mock()
            with contextlib.redirect_stdout(io.StringIO()):pipeline.run(['synthetic-command'],self.pack,runner=runner)
        for key in inherited:
            if key in ('PATH','LANG','LC_ALL','TZ'):
                self.assertEqual(env[key],inherited[key])
            elif key not in ('HOME','NETRC','GIT_CONFIG_GLOBAL'):
                self.assertNotIn(key,env)
        self.assertEqual(Path(env['HOME']),self.pack/'work/home')
        self.assertEqual(env['NETRC'],pipeline.os.devnull)
        self.assertEqual(env['GIT_CONFIG_GLOBAL'],pipeline.os.devnull)
        self.assertEqual(runner.call_args.kwargs['env'],env)
        self.assertNotIn('synthetic-secret',json.dumps(env))
        self.assertEqual(list((self.pack/'work/home').iterdir()),[])
    def test_anonymous_opener_disables_environment_proxies_and_auth_handlers(self):
        opener=downloads.opener()
        handlers={type(handler).__name__ for handler in opener.handlers}
        self.assertFalse(any('Cookie' in name or 'Auth' in name for name in handlers))
        # A supplied empty proxy map may remove ProxyHandler entirely in urllib.
        self.assertTrue(all(not getattr(handler,'proxies',{}) for handler in opener.handlers))


if __name__=='__main__':unittest.main()
