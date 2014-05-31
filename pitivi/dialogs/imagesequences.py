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

from gi.repository import Gtk

import os
import shutil
from gettext import gettext as _

from pitivi.configure import get_ui_dir


class ImageSequenceDialog(object):
    """
    Displays the dialog to create an image sequence playlist.
    """
    def __init__(self, app, playlist):
        self.app = app
        self.playlist = playlist
        self.playlist_out = None
        self._savePlaylistDialog = None
        self.builder = Gtk.Builder()
        self.builder.add_from_file(os.path.join(get_ui_dir(), "imagesequence.ui"))
        self.dialog = self.builder.get_object("create_playlist_dialog")
        self.builder.connect_signals(self)

    def showSavePlaylistDialog(self):
        dialogtitle = _("Create Image Sequence Playlist")
        chooser_action = Gtk.FileChooserAction.SAVE
        self._savePlaylistDialog = Gtk.FileChooserDialog(title=dialogtitle,
            transient_for=None, action=chooser_action)
        self._savePlaylistDialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,
            Gtk.STOCK_ADD, Gtk.ResponseType.OK)
        self._savePlaylistDialog.connect('response', self._savePlaylistDialogResponseCb)
        self._savePlaylistDialog.run()

    def _savePlaylistDialogResponseCb(self, dialogbox, response):
        if response == Gtk.ResponseType.OK:
            playlist_out = dialogbox.get_filename()
            self.playlist.save(playlist_out)
            self.app.project_manager.current_project.addUris([self.playlist.get_uri()])
            self.dialog.destroy()
        self._savePlaylistDialog.destroy()
        self._savePlaylistDialog = None

    def _closeCb(self, widget):
        self.dialog.destroy()

    def _addCb(self, widget):
        self.showSavePlaylistDialog()

    def run(self):
        self.dialog.run()
