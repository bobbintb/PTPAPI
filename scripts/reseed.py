#!/bin/env python
import sys
import re
import os
import os.path
import xmlrpclib
import argparse
import ConfigParser
import logging
import readline

from pyrobase import bencode
from pyrocore import config
from pyrocore.util import load_config, metafile

import ptpapi

logger = logging.getLogger(__name__)

def matchByTorrent(movie, path):
    basename = os.path.basename(os.path.abspath(path))
    dirname = os.path.dirname(os.path.abspath(path))
    for t in movie.Torrents:
        # Only single files under a directory are matched currently
        # e.g. Movie.Name.Year.mkv -> Move Name (Year)/Movie.Name.Year.mkv
        if len(t.Filelist) == 1 and t.Filelist.keys()[0] == basename:
            logger.info("Found strong match by filename at torrent %s, creating new folder structure" % t.ID)
            tID  = t.ID
            newPath = os.path.join(dirname, t.ReleaseName)
            if not os.path.exists(newPath):
                logger.debug("Creating new directory %s" % newPath)
                os.mkdir(newPath)
            if not os.path.exists(os.path.join(dirname, t.ReleaseName, basename)):
                os.link(os.path.abspath(path),
                        os.path.join(dirname, t.ReleaseName, basename))
            return (t.ID, newPath)
        # Attempt to match cases where the folder has been renamed, but all files are the same
        fileList = {}
        for root, subFolders, files in os.walk(path):
            for real_file in files:
                f = os.path.join(root, real_file)
                fileList[real_file] = os.path.getsize(f)
        found_all_files = True
        for tfile in t.Filelist:
            if tfile not in fileList:
                found_all_files = False
                break
        if found_all_files:
            logger.info("Found strong match by subfiles at torrent %s, using as base path")
            return (t.ID, path)
    return None

def findByFile(ptp, filename):
    basename = os.path.basename(os.path.abspath(filename))
    dirname = os.path.dirname(os.path.abspath(filename))
    tID = None
    for m in ptp.search({'filelist':basename}):
        logger.debug("Found movie %s: %s" % (m.ID, m.Title))
        for t in m.Torrents:
            logger.debug("Found torrent %s under movie %s" % (t.ID, m.ID))
            # Exact match or match without file extension
            if t.ReleaseName == basename or t.ReleaseName == os.path.splitext(basename)[0]:
                logger.info("Found strong match by release name at %s" % t.ID)
                tID = t.ID
                if os.path.isdir(filename):
                    path = filename
                else:
                    path = dirname
                return (tID, path)
            elif t.ReleaseName in basename.decode('UTF-8'):
                logger.debug("Found weak match by name at %s" % t.ID)
        if not tID:
            logger.debug("Movie found but no match by release name, attempting to match by filename")
            m.load_html_data()
            matches = matchByTorrent(m, filename)
            if matches:
                return matches
    return None

def loadTorrent(ID, path):
    # Load pyroscope
    load_config.ConfigLoader().load()
    proxy = config.engine.open()

    torrent = ptpapi.Torrent(ID=ID)
    name = torrent.download_to_file()
    torrent = metafile.Metafile(name)
    data = bencode.bread(name)
    thash = metafile.info_hash(data)
    try:
        proxy.d.hash(thash, fail_silently=True)
        logger.error("Hash already exists in rtorrent, cannot load.")
        exit()
    except xmlrpclib.Fault:
        pass
    proxy.load(os.path.abspath(name))
    # Wait until the torrent is loaded and available
    while True:
        try:
            proxy.d.hash(thash, fail_silently=True)
            break
        except xmlrpclib.Fault:
            pass
    logger.info("Torrent loaded")
    proxy.d.ignore_commands.set(thash, 1)
    proxy.d.directory_base.set(thash, path)
    proxy.d.check_hash(thash)

    # Cleanup
    os.remove(name)

def main():
    parser = argparse.ArgumentParser(description='Attempt to find and reseed torrents on PTP')
    parser.add_argument('-u', '--url', help='Permalink to the torrent page')
    parser.add_argument('-p', '--path', help='Base directory of the file')
    parser.add_argument('-f', '--file', help='Path directly to file/directory')
    parser.add_argument('-n', '--dry-run', help="Don't actually load any torrents", action="store_true")
    parser.add_argument('--file-loop', help="Run in loop mode to avoid rapid session creation", action="store_true")
    parser.add_argument('--debug', help='Print lots of debugging statements', action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument('-v', '--verbose', help='Be verbose', action="store_const", dest="loglevel", const=logging.INFO)
    args = parser.parse_args()
    
    logging.basicConfig(level=args.loglevel)

    path = unicode(args.path)
    if args.file:
        arg_file = args.file.decode('UTF-8')
    tID = None

    # Load PTP API
    ptp = ptpapi.login()

    if args.file_loop:
        while True:
            filepath = raw_input('file>>> ').decode('UTF-8')
            if filepath in ['q', 'quit', 'exit']:
                break
            match = findByFile(ptp, filepath)
            if match:
                loadTorrent(*match)
        exit()

    if args.url:
        tID = re.search(r'(\d+)$', args.url).group(1)
        if not path and arg_file:
            path = unicode(os.path.dirname(os.path.abspath(arg_file)))
    else:
        if arg_file:
            match = findByFile(ptp, arg_file)
            if match:
                (tID, path) = match
        else:
            raise Exception("No file specified")

    # Make sure we have the minimum information required
    if not tID or not path:
        logger.error("Torrent ID or path missing, cannot reseed")
        ptp.logout()
        exit()
    logger.info("Found match, now loading torrent %s to path %s" % (tID, path))
    if args.dry_run:
        ptp.logout()
        exit()
    loadTorrent(tID, path)

    ptp.logout()

    logger.debug("Exiting...")

if __name__ == '__main__':
    main()
