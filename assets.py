import os
import sys
import shutil
import threading
import requests
import tqdm
import hashlib

from bundle import ASSETS_DIR, TMP_DIR
from warc_extractor.warc_extractor import _main_interface

WARC_PATH = os.path.join(TMP_DIR, "warc")
EXTRACTION_PATH = os.path.join(TMP_DIR, "extracted")
EXTRACTED_INNER_ASSETS_PATH = os.path.join(EXTRACTION_PATH, "zynga1-a.akamaihd.net", "farmville", "assets", "hashed", "assets")

BASE_URL = "https://archive.org/download/original-farmville/"
FILES = [
    {   "filename": "urls-bluepload.unstable.life-farmvilleassets.txt-shallow-20201225-045045-5762m-00000.warc.gz",
        "hash": "d9a36e44e5361e3db6ce1457f74ddf89",
    },
    {   "filename": "urls-bluepload.unstable.life-farmvilleassets.txt-shallow-20201225-045045-5762m-00001.warc.gz",
        "hash": "54a8d13a5dfe0b12b5a3e17e39167a1e",
    },
    {   "filename": "urls-bluepload.unstable.life-farmvilleassets.txt-shallow-20201225-045045-5762m-00002.warc.gz",
        "hash": "04938bcbc6585858f88962e9af6232b1",
    },
    {   "filename": "urls-bluepload.unstable.life-farmvilleassets.txt-shallow-20201225-045045-5762m-00003.warc.gz",
        "hash": "4bb8d8f949f2ecfdab395cd35c9a47e6",
    },
]

def __inner_assets_check():
    return os.path.exists(os.path.join(ASSETS_DIR, "Environment")) and os.path.exists(os.path.join(ASSETS_DIR, "xpromoSupport")) # TODO: check for more directories
    
def check_assets():

    # check if extracted assets directory exists
    if __inner_assets_check():
        print(" * Assets directory found.")
        return
    print(" * Assets not found or missing assets.")
    
    # check if assets dir already exists and is not empty
    if os.path.exists(ASSETS_DIR) and os.listdir(ASSETS_DIR):
        print(" [!] Assets directory found (not empty) but seems incomplete. Remove before proceeding. Exiting...")
        sys.exit(1)
    elif os.path.exists(ASSETS_DIR):
        print(" [!] Empty assets directory found. Removing...")
        os.rmdir(ASSETS_DIR)
    
    # check if tmp directory exists
    if not os.path.exists(TMP_DIR):
        print(" * Creating tmp directory...")
        os.mkdir(TMP_DIR)
    
    # check if WARC directory exists and is not empty
    if not os.path.exists(WARC_PATH) or not os.listdir(WARC_PATH):
        print(" * WARC directory not found. Downloading WARC assets files... (one time only, might take a while)")
        warc_download(FILES)
    
    # check if all WARC files in dir
    missing_warc_files = []
    for file_dict in FILES:
        file = file_dict["filename"]
        expected_file_hash = file_dict["hash"]
        filelocation = os.path.join(WARC_PATH, file)
        if not os.path.exists(filelocation):
            print(f" [!] File '{file}' not found in assets directory.")
            missing_warc_files.append(file_dict)
            continue
        with open(filelocation, 'rb') as f:
            print(f" * Checking hash of file '{file}'...")
            md5 = hashlib.md5()
            for chunk in iter(lambda: f.read(4*1024*1024), b""):
                md5.update(chunk)
            file_hash = md5.hexdigest()
            if file_hash != expected_file_hash:
                print(f" [!] File '{file}' hash mismatch.\n     Obtained '{file_hash}', expected '{expected_file_hash}'.")
                redownload: bool = input(" [?] Do you want to redownload the file? (Y/n): ").lower() != 'n'
                if redownload:
                    missing_warc_files.append(file_dict)
                    continue
                else:
                    print(" [!] File hash mismatch. Need to redownload. Exiting...")
                    sys.exit(1)

    if missing_warc_files:
        print(" [!] (Re)Downloading missing or corrupted WARC assets file(s)...")
        warc_download(missing_warc_files)
        check_assets()
        return
    
    # At this point, assets are not found or incomplete, so we need to extract them
    print(" * Extracting assets... (one time only, might take a while: up to 1h)")
    assets_extract()

    # move extracted assets to assets directory
    print(" * Moving extracted assets to assets directory...")

    # If the destination is a directory or a symlink to a directory, the source is moved inside the directory.
    # The destination path must not already exist.
    assert not os.path.exists(ASSETS_DIR)
    
    # If the destination is on our current filesystem (it should be),
    # then rename() is used (which should be really efficient), instead of a copy and remove.
    dest = shutil.move(EXTRACTED_INNER_ASSETS_PATH, ASSETS_DIR)
    if not dest:
        print(" [!] Moving extracted assets failed. Exiting...")
        sys.exit(1)
    
    # delete tmp extracted assets directory and warc directory
    print(" * Cleaning up tmp dir...")
    shutil.rmtree(TMP_DIR)
    print(" * Assets extracted!")
    
    # Let's check again if the assets are extracted
    if not __inner_assets_check():
        print(" [!] Asset extraction failed. Exiting...")
        sys.exit(1)
    return

def warc_download(files_list):
    # create WARC directory
    if not os.path.exists(WARC_PATH):
        os.mkdir(WARC_PATH)

    threads = []

    def download(desc, link, filelocation):
        r = requests.get(link, stream=True)
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        tqdm_params = {
            'desc': desc,
            'total': total,
            'miniters': 1,
            'unit': 'B',
            'unit_scale': True,
            'unit_divisor': 1024,
        }
        with open(filelocation, 'wb') as f:
            with tqdm.tqdm(**tqdm_params) as pb:
                for chunk in r.iter_content(1024):
                    if chunk:
                        pb.update(len(chunk))
                        f.write(chunk)
    
    def create_download_thread(desc, link, filelocation):
        download_thread = threading.Thread(target=download, args=(desc, link, filelocation))
        download_thread.start()
        return download_thread
    
    # download assets with threads
    for file_dict in files_list:
        file = file_dict["filename"]
        expected_file_hash = file_dict["hash"]
        filelocation = os.path.join(WARC_PATH, file)
        link = BASE_URL + file
        desc = f" * {file}"
        thread = create_download_thread(desc, link, filelocation)
        threads.append(thread)

    # wait for all threads to finish
    for thread in threads:
        thread.join()
    
    print(" * WARC Assets downloaded!")

def assets_extract():

    # create extracted assets directory
    if not os.path.exists(EXTRACTION_PATH):
        os.mkdir(EXTRACTION_PATH)
        
    # WARC extraction
    _main_interface(
        path=WARC_PATH,
        output_path=EXTRACTION_PATH,
        dump="content",
        filter=["WARC-Target-URI:zynga1-a.akamaihd.net/farmville/assets/hashed/assets"],
        silence=False
    )
    if not os.path.exists(EXTRACTED_INNER_ASSETS_PATH) or not os.listdir(EXTRACTED_INNER_ASSETS_PATH):
        print(" [!] Extraction failed. Consider extracting and placing the assets manually. Exiting...")
        sys.exit(1)
