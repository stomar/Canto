#Canto - ncurses RSS reader
#   Copyright (C) 2008 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

import cPickle
import codecs
import getopt
import time
import os
import sys
import feedparser
import shutil

def log(path, str, verbose, mode="a"):
    if verbose:
        print str

    try :
        f = codecs.open(path, mode, "UTF-8", "ignore")
        try:
            f.write(str)
        finally:
            f.close()
    except IOError:
        pass

def print_usage():
    print "USAGE: canto-fetch [-hvfVCFL]"
    print "--help    -h        Print this help."
    print "--version -v        Print version info."
    print "--verbose -V        Print status while updating."
    print "--force   -f        Force update, even if timestamp is too recent."
    print "--conf    -C [path] Set configuration file. (~/.canto/sconf)"
    print "--fdir    -F [path] Set feed directory. (~/.canto/feeds/)"
    print "--log     -L [path] Set log file (~/.canto/slog)"

def main():
    MAJOR,MINOR,REV = (0,5,0)
    
    home = os.getenv("HOME")
    conf = home + "/.canto/sconf"
    path = home + "/.canto/feeds/"
    log_file = home + "/.canto/slog"
    verbose = 0
    force = 0

    try:
        optlist, arglist = getopt.getopt(sys.argv[1:], 'hvfVC:F:L:',\
                ["verbose","conf=","fdir=","log=", "help", "force"])
    except getopt.GetoptError, e:
        print "Error: %s" % e.msg
        sys.exit(-1)

    for opt, arg in optlist:
        if opt in ["-v","--version"]:
            print "Canto-fetch v %d.%d.%d" % (MAJOR,MINOR,REV)
            sys.exit(0)
        if opt in ["-V","--verbose"]:
            verbose = 1
        elif opt in ["-h","--help"]:
            print_usage()
            sys.exit(0)
        elif opt in ["-C", "--conf"]:
            conf = arg
        elif opt in ["-F", "--fdir"]:
            path = arg
            if path[-1] != '/':
                path += '/'
        elif opt in ["-L", "--log"]:
            log_file = arg
        elif opt in ["-f", "--force"]:
            force = 1
    
    log(log_file, "Canto-fetch v %d.%d.%d\n" % (MAJOR,MINOR,REV), 0, "w")
    log(log_file, "Started execution: %s\n" % time.asctime(time.localtime()),0, "a")
    log_func = lambda x : log(log_file, x, verbose, "a")
  
    f = open(conf, "r")
    feeds = cPickle.load(f)
    f.close()

    if not os.path.exists(path):
        os.mkdir(path)
    elif not os.path.isdir(path):
        os.unlink(path)
        os.mkdir(path)

    for file in os.listdir(path):
        file = path  + file
        for handle in [f[0] for f in feeds]:
            valid = path + handle.replace("/", " ")
            if file == valid or file == valid + ".lock":
                break
        else:
            log_func("Deleted extraneous file: %s\n" % file)
            try:
                os.unlink(file)
            except:
                pass

    for handle,url,update,keep in feeds:
        fpath = path + "/" + handle.replace("/", " ")
        lpath = fpath + ".lock"
        try:
            lock = os.open(lpath, os.O_CREAT|os.O_EXCL)
        except OSError:
            if time.time() - os.stat(lpath).st_ctime > 120:
                os.unlink(lpath)
                log_func("Deleted stale lock for %s." % handle)
                try:
                    lock = os.open(lpath, os.O_CREAT|os.O_EXCL)
                except:
                    log_func("Failed to get lock for %s." % handle)
                    continue

        fpath = path + "/" + handle.replace("/", " ")
        if os.path.exists(fpath):
            if os.path.isfile(fpath):
                f = open(fpath, "rb")
                try:
                    curfeed = cPickle.load(f)
                except:
                    log_func("cPickle load exception on %s" % fpath)
                    raise
                f.close()
            else:
                log_func("%s is not normal file, old format?" % fpath)
                log_func("  Deleting...")
                if os.path.isdir(fpath):
                    shutil.rmtree(fpath)
                else:
                    os.unlink(fpath)
                curfeed = {"canto_state":[], "entries":[], "canto_update":0}
        else:
            curfeed = {"canto_state":[], "entries":[], "canto_update":0}

        if time.time() - curfeed["canto_update"] < update * 60 and not force:
            os.unlink(lpath)
            continue
        elif verbose:
            print "Updating %s" % handle

        newfeed = feedparser.parse(url)
        if newfeed.has_key("bozo_exception"):
            log_func("Recoverable error in feed %s: %s" % (handle, newfeed["bozo_exception"]))
            newfeed["bozo_exception"] = None

        newfeed["canto_state"] = curfeed["canto_state"]
        newfeed["canto_update"] = time.time()
        for entry in newfeed["entries"]:
            if entry.has_key("content"):
                for c in entry["content"]:
                    c["value"] = c["value"].encode("UTF-8")
                    c["value"] = c["value"].replace("%", "\\%")

            for key in entry.keys():
                if type(entry[key]) in [unicode,str]:
                    entry[key] = entry[key].encode("UTF-8")
                    entry[key] = entry[key].replace("%", "\\%")

        for i in range(len(newfeed["entries"])) :
            if not newfeed["entries"][i].has_key("id"):
                if newfeed["entries"][i].has_key("link"):
                    newfeed["entries"][i]["id"] = newfeed["entries"][i]["link"]
                elif newfeed["entries"][i].has_key("title"):
                    newfeed["entries"][i]["id"] = newfeed["entries"][i]["title"]
                else:
                    newfeed["entries"][i]["id"] = None

            for j in range(len(curfeed["entries"])) :
                if newfeed["entries"][i]["id"] == curfeed["entries"][j]["id"]:
                    newfeed["entries"][i]["canto_state"] = curfeed["entries"][j]["canto_state"]
                    curfeed["entries"].remove(curfeed["entries"][j])
                    break

            if not newfeed["entries"][i].has_key("canto_state"):
                newfeed["entries"][i]["canto_state"] = [ handle,"unread", "*"]

        
        if len(newfeed["entries"]) < keep:
            newfeed["entries"] += curfeed["entries"][:keep - len(newfeed["entries"])]
        else:
            newfeed["entries"] = newfeed["entries"][:keep]

        f = open(fpath, "wb")
        try:
            cPickle.dump(newfeed, f)
        except:
            log_func("cPickle dump exception on %s" % fpath)
            raise
        f.close()

        os.unlink(lpath)
    
    log_func("Gracefully exiting Canto-fetch.\n")
    sys.exit(0)
