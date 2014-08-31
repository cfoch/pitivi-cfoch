# -*- coding: utf-8 -*-
# Pitivi video editor
#
#       pitivi/utils/imagesequences.py
#
# Copyright (c) 2014, Fabian Orccon <fabian.orccon@pucp.pe>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
# Boston, MA 02110-1301, USA.

import os
import tempfile
from urllib.parse import urlparse, unquote

from gi.repository import Gst

from pitivi.configure import get_ui_dir
from pitivi.utils.widgets import FractionWidget

IMAGE_SEQUENCE_PROTOCOL = "imagesequence"


class ImageSequencePlaylist:
    def __init__(self, filename=None):
        self.filename = self._set_filename(filename)
        self.filenames = []
        self.framerate = None

    def parse(self):
        Gst.init()
        with open(self.filename, "r") as playlist:
            for line in playlist.readlines():
                st = Gst.Structure.from_string(line)[0]
                if st["framerate"] is not None:
                    self.framerate = st["framerate"]
                if st["location"] is not None:
                    self.filenames.append(st["location"])
        playlist.close()
        return self._is_valid()

    def save(self, filename=None):
        if not self._is_valid():
            return
        if filename is None:
            playlist = tempfile.NamedTemporaryFile(mode="wt", prefix='pitivi_',
                delete=False)
            self.filename = playlist.name
        else:
            self.filename = filename
            playlist = open(filename, "w")
        playlist.write("metadata, framerate=(fraction)%d/%d\n" %
            (self.framerate.num, self.framerate.denom))
        for filename in self.filenames:
            playlist.write("image, location=\"%s\"\n" % filename)
        playlist.close()

    def get_uri(self):
        if self.filename is None:
            return
        return "%s://%s" % (IMAGE_SEQUENCE_PROTOCOL, self.filename)

    # private

    def _set_filename(self, path_or_uri):
        if path_or_uri is None:
            return
        filename = urlparse(path_or_uri)[2]
        return unquote(filename)

    def _is_valid(self):
        # TODO: Validate each filename exists
        return self.filenames and self.framerate is not None
