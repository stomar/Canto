# -*- coding: utf-8 -*-

#Canto - ncurses RSS reader
#   Copyright (C) 2008 Jack Miller <jack@codezen.org>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License version 2 as 
#   published by the Free Software Foundation.

from const import *
import story
import tag

from threading import Thread
import cPickle
import fcntl

# Feed() controls a single feed and implements all of the update functionality
# on top of Tag() (which is the generic class for lists of items). Feed() is
# also the lowest granule for custom renderers because the renderers are
# most likely using information specific to the XML, rather than information
# specific to an arbitrary list.

# Each feed has a self.ufp item that contains a verbatim copy of the data
# returned by the feedparser.

# Each feed will also only write its status back to disk on tick() and only if
# has_changed() has been called by one of the Story() items Feed() contains.

class Feed(list):
    def __init__(self, cfg, dirpath, URL, tags, rate, keep, \
            filter, username, password):

        # Configuration set settings
        self.tags = tags
        if self.tags[0] == None:
            self.base_set = 0
            self.base_explicit = 0
        else:
            self.base_set = 1
            self.base_explicit = 1

        self.URL = URL
        self.rate = rate
        self.time = 1
        self.keep = keep
        self.username = username
        self.password = password

        # Hard filter
        if filter:
            self.filter = lambda x: filter(self, x)
        else:
            self.filter = None

        # Other necessities
        self.path = dirpath
        self.cfg = cfg
        self.ufp = []
   
    def update(self):
        lockflags = fcntl.LOCK_SH
        if self.base_set:
            lockflags |= fcntl.LOCK_NB

        try:
            f = open(self.path, "r")
            try:
                fcntl.flock(f.fileno(), lockflags)
                self.ufp = cPickle.load(f)
            except:
                return 0
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()
        except:
            return 0

        # If this data pre-dates 0.6.0 (the last disk format update)
        # toss a key error.
        if "canto_version" not in self.ufp or\
                self.ufp["canto_version"][1] < 6:
            raise KeyError

        if not self.base_set:
            self.base_set = 1
            if "feed" in self.ufp and "title" in self.ufp["feed"]:
                replace = lambda x: x or self.ufp["feed"]["title"]
                self.tags = [ replace(x) for x in self.tags]
            else:
                # Using URL for tag, no guarantees
                self.tags = [self.URL] + self.tags

        self.extend(self.ufp["entries"])
        self.todisk()
        return 1

    def extend(self, entries):
        newlist = []
        for entry in entries:
            # If tags were added in the configuration, c-f won't
            # notice (doesn't care about tags), so we check and
            # append as needed.

            for tag in self.tags:
                if tag not in entry["canto_state"]:
                    entry["canto_state"].append(tag)

            if entry not in self:
                newlist.append(story.Story(entry))

        for centry in self:
            if centry not in entries:
                self.remove(centry)

        list.extend(self, filter(self.filter, newlist))

    def todisk(self):
        changed = self.changed()
        if not changed :
            return

        for entry in changed:
            old = self.ufp["entries"][self.ufp["entries"].index(entry)]
            if old["canto_state"] != entry["canto_state"]:
               if entry.updated:
                   old["canto_state"] = entry["canto_state"]
               else:
                   entry["canto_state"] = old["canto_state"]

        f = open(self.path, "r+")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            f.seek(0, 0)
            f.truncate()
            cPickle.dump(self.ufp, f)
            f.flush()
            for x in changed:
                x.updated = 0
        except:
            return 0
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()
        return 1

    def changed(self):
        return [ x for x in self if x.updated ]

class UpdateThread(Thread):
    def __init__(self, cfg, feed):
        self.cfg = cfg
        self.feed = feed
        self.status = THREAD_IDLE

    def run(self, old):
        self.status = THREAD_UPDATING
        if self.feed.update():
            self.feed.time = self.feed.rate

        self.status = THREAD_FILTERING
        filter = self.cfg.filters.cur()
        if not filter:
            filter = lambda x, y: 1

        self.new = []
        for item in self.feed:
            if item in old or (not filter(self.feed, item)):
                continue
            self.new.append(item)

        self.old = []
        for item in old:
            if item in self.feed and filter(self.feed, item):
                continue
            self.old.append(item)

    def tick(self, old=None):
        self.feed.time -= 1
        if self.feed.time <= 0 and self.status == THREAD_IDLE:
            self.status = THREAD_START
            if old == None:
                old = self.feed[:]
            self.run(old)
            self.status = THREAD_DONE

