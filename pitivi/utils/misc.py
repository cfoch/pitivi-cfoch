# -*- coding: utf-8 -*-
# Pitivi video editor
# Copyright (c) 2005, Edward Hervey <bilboed@bilboed.com>
# Copyright (c) 2009, Alessandro Decina <alessandro.d@gmail.com>
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
import bisect
import hashlib
import mimetypes
import os
import re
import subprocess
import threading
import time
from gettext import gettext as _
from urllib.parse import unquote
from urllib.parse import urlparse
from urllib.parse import urlsplit

from gi.repository import GES
from gi.repository import GLib
from gi.repository import Gst
from gi.repository import Gtk

import pitivi.utils.loggable as log
from pitivi.configure import APPMANUALURL_OFFLINE
from pitivi.configure import APPMANUALURL_ONLINE
from pitivi.configure import APPNAME
from pitivi.utils.threads import Thread


# Work around https://bugzilla.gnome.org/show_bug.cgi?id=759249
def disconnectAllByFunc(obj, func):
    i = 0
    while True:
        i += 1
        try:
            obj.disconnect_by_func(func)
        except TypeError:
            return i

    return i


def format_ns(timestamp):
    if timestamp is None:
        return None
    if timestamp == Gst.CLOCK_TIME_NONE:
        return "CLOCK_TIME_NONE"

    return str(timestamp / (Gst.SECOND * 60 * 60)) + ':' + \
        str((timestamp / (Gst.SECOND * 60)) % 60) + ':' + \
        str((timestamp / Gst.SECOND) % 60) + ':' + \
        str(timestamp % Gst.SECOND)


def call_false(function, *args, **kwargs):
    """Calls the specified function and returns False.

    Helper function for calling an arbitrary function once in the gobject
    mainloop.  Any positional or keyword arguments after the function will
    be provided to the function.

    Args:
        function (function): The function to call.

    Returns:
        bool: False
    """
    function(*args, **kwargs)
    return False


def get_proxy_target(obj):
    if isinstance(obj, GES.UriClip):
        asset = obj.get_asset()
    elif isinstance(obj, GES.TrackElement):
        asset = obj.get_parent().get_asset()
    else:
        asset = obj

    target = asset.get_proxy_target()
    if target and target.get_error() is None:
        asset = target

    return asset


# ------------------------------ URI helpers --------------------------------

def isWritable(path):
    """Returns whether the file/path is writable."""
    try:
        if os.path.isdir(path):
            # The given path is an existing directory.
            # To properly check if it is writable, you need to use os.access.
            return os.access(path, os.W_OK)
        else:
            # The given path is supposed to be a file.
            # Avoid using open(path, "w"), as it might corrupt existing files.
            # And yet, even if the parent directory is actually writable,
            # open(path, "rw") will IOError if the file doesn't already exist.
            # Therefore, simply check the directory permissions instead:
            return os.access(os.path.dirname(path), os.W_OK)
    except UnicodeDecodeError:
        unicode_error_dialog()


def uri_is_valid(uri):
    """Checks if the specified URI is usable (of type file://).

    Will also check if the size is valid (> 0).

    Args:
        uri (str): The location to check.
    """
    return (Gst.uri_is_valid(uri) and
            Gst.uri_get_protocol(uri) == "file" and
            len(os.path.basename(Gst.uri_get_location(uri))) > 0)


def uri_is_reachable(uri):
    """Checks whether the specified URI is reachable by GStreamer.

    Args:
        uri (str): The location to check.

    Returns:
        bool: True when the URI is reachable, False otherwise.
    """
    if not uri_is_valid(uri):
        raise NotImplementedError(
            # Translators: "non local" means the project is not stored
            # on a local filesystem
            _("%s doesn't yet handle non-local projects") % APPNAME)
    return os.path.isfile(Gst.uri_get_location(uri))


def path_from_uri(raw_uri):
    """Returns a path that can be used with Python's os.path."""
    uri = urlparse(raw_uri)
    assert uri.scheme == "file"
    return unquote(uri.path)


def filename_from_uri(uri):
    """Returns a filename for display.

    Excludes the path to the file.

    Can be used in UI elements or to shorten debug statements.
    """
    return os.path.basename(path_from_uri(uri))


def quote_uri(uri):
    """Encodes a URI according to RFC 2396.

    Does not touch the file:/// part.
    """
    # Split off the "file:///" part, if present.
    parts = urlsplit(uri, allow_fragments=False)
    # Make absolutely sure the string is unquoted before quoting again!
    raw_path = unquote(parts.path)
    # For computing thumbnail md5 hashes in the media library, we must adhere to
    # RFC 2396. It is quite tricky to handle all corner cases, leave it to Gst:
    return Gst.filename_to_uri(raw_path)


class PathWalker(Thread):
    """Thread for recursively searching in a list of directories."""

    def __init__(self, paths, callback):
        Thread.__init__(self)
        self.log("New PathWalker for %s", paths)
        self.paths = paths
        self.callback = callback
        self.stopme = threading.Event()

    def process(self):
        for folder in self.paths:
            self.log("folder %s" % folder)
            if folder.startswith("file://"):
                folder = unquote(folder[len("file://"):])
            for path, dirs, files in os.walk(folder):
                if self.stopme.isSet():
                    return
                uris = []
                for afile in files:
                    uris.append(quote_uri("file://%s" %
                                          os.path.join(path, afile)))
                if uris:
                    GLib.idle_add(self.callback, uris)

    def abort(self):
        self.stopme.set()


def hash_file(uri):
    """Hashes the first 256KB of the specified file."""
    sha256 = hashlib.sha256()
    with open(uri, "rb") as file:
        for _ in range(1024):
            chunk = file.read(256)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def quantize(input, interval):
    return (input // interval) * interval


def binary_search(elements, value):
    """Returns the index of the element closest to value.

    Args:
        elements (List): A sorted list.
    """
    if not elements:
        return -1
    closest_index = bisect.bisect_left(elements, value, 0, len(elements) - 1)
    element = elements[closest_index]
    closest_distance = abs(element - value)
    if closest_distance == 0:
        return closest_index
    for index in (closest_index - 1,):
        if index < 0:
            continue
        distance = abs(elements[index] - value)
        if closest_distance > distance:
            closest_index = index
            closest_distance = distance
    return closest_index


def show_user_manual(page=None):
    """Displays the user manual.

    First tries with Yelp and then tries opening the online version.

    Args:
        page (Optional[str]): A page ID to display instead of the index page,
            for contextual help.
    """
    def get_page_uri(uri, page):
        if page is not None:
            return uri + "#" + page
        return uri

    time_now = int(time.time())
    uris = (APPMANUALURL_OFFLINE, APPMANUALURL_ONLINE)
    for uri in uris:
        try:
            Gtk.show_uri(None, get_page_uri(uri, page), time_now)
            return
        except Exception as e:
            log.info("utils", "Failed loading URI %s: %s", uri, e)
            continue

    try:
        # Last try calling yelp directly (used in flatpak while we do
        # not have a portal to access system wild apps)
        subprocess.Popen(["yelp",
                          get_page_uri(APPMANUALURL_OFFLINE, page)])
    except FileNotFoundError:
        log.warning("utils", "Failed loading URIs")
        dialog = Gtk.MessageDialog(modal=True,
                                   message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK,
                                   text=_("Failed to open the user manual."
                                          " Make sure to have either the `yelp` GNOME "
                                          " documentation viewer or a web browser"
                                          " installed"))
        dialog.run()
        dialog.destroy()


def unicode_error_dialog():
    message = _("The system's locale that you are using is not UTF-8 capable. "
                "Unicode support is required for Python3 software like Pitivi. "
                "Please correct your system settings; if you try to use Pitivi "
                "with a broken locale, weird bugs will happen.")
    dialog = Gtk.MessageDialog(transient_for=None,
                               modal=True,
                               message_type=Gtk.MessageType.ERROR,
                               buttons=Gtk.ButtonsType.OK,
                               text=message)
    dialog.set_icon_name("pitivi")
    dialog.set_title(_("Error while decoding a string"))
    dialog.run()
    dialog.destroy()


def filename_of_type(filename, mimetype, compare_subtype=True):
    """
    Checks if filename is of type or type/subtype if compare_subtype.
    """
    btype = mimetypes.guess_type(filename)[0]
    ret = False
    if btype is not None:
        if compare_subtype:
            ret = btype == mimetype
        else:
            ret = (mimetype.split("/")[0] is not None and
                btype.split("/")[0] == mimetype.split("/")[0])
    return ret


def filenames_same_type(filenames, compare_mimetype=True,
                        compare_extension=True):
    """
    Checks if all the filenames have the same type.
    """
    mime_base = mimetypes.guess_type(filenames[0])[0]
    ext = os.path.splitext(filenames[0])[1]
    for filename in filenames:
        extension = os.path.splitext(filenames[0])[1]
        if ((compare_mimetype and not filename_of_type(filename, mime_base))
            or (compare_extension and ext != extension)):
            return False
    return True

def image_sequence_info_from_pattern(pattern):
    path = os.path.dirname(pattern)
    filenames = os.listdir(path)
    if not filenames:
        return
    if (not filename_of_type(filenames[0], "image", False) or
        not filenames_same_type(filenames) or len(filenames) < 2):
        return
    basename = os.path.basename(pattern)
    extension = os.path.splitext(basename)[1]

    indices = []
    for filename in filenames:
        tmp_root, tmp_extension = os.path.splitext(filename)
        if extension != tmp_extension:
            return
        sequence_index = int(tmp_root)
        indices.append(sequence_index)

    if not indices:
        return

    # Validate that filenames follow a sequence
    indices.sort()
    if indices != list(range(indices[0], indices[-1] + 1)):
        return

    start = indices[0]
    stop = indices[-1]
    return {"start-index": start, "stop-index": stop, "location": pattern}

def discover_image_sequence_pattern(path):
    if not os.path.isdir(path):
        path = os.path.dirname(path)
    filenames = os.listdir(path)
    if not filenames:
        return
    if (not filename_of_type(filenames[0], "image", False) or
        not filenames_same_type(filenames) or len(filenames) < 2):
        return
    # The filename with the longest length can give more information to
    filename_target = max(filenames, key=len)
    extension = os.path.splitext(filename_target)[1]
    regex = '(\d+\\b%s\\b)' % extension
    tokens_cmp = re.split(regex, filename_target)[:-1]
    if (len(tokens_cmp) != 2):
        return
    n_zeros = len(tokens_cmp[1].split(".")[0])

    indices = []
    for filename in filenames:
        tokens = re.split(regex, filename)[:-1]
        n_zeros = min(n_zeros, len(tokens[1].split(".")[0]))
        if not tokens or len(tokens) != 2 or tokens[0] != tokens_cmp[0]:
            return
        sequence_index = int(os.path.splitext(tokens[-1])[0])
        indices.append(sequence_index)
    if not indices:
        return

    # Validate that filenames follow a sequence
    indices.sort()
    if indices != list(range(indices[0], indices[-1] + 1)):
        return

    printf_format = '%0' + str(n_zeros) + 'd'
    tokens_cmp[1] = printf_format
    tokens_cmp.append(extension)
    pattern =  "".join(tokens_cmp)
    return os.path.join(path, pattern)
