import os
import shutil

from gi.repository import Gtk
from gettext import ngettext, gettext as _

from pitivi.configure import get_ui_dir


class CreatePlaylistDialog(object):
    """
    Displays the dialog to create an image sequence playlist.
    """
    def __init__(self, project, playlist_in):
        self.project = project
        self.playlist_in = playlist_in
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
            shutil.copyfile(self.playlist_in, playlist_out)
            self.project.addUris(["imagesequence://" + playlist_out])
            self.dialog.destroy()
        self._savePlaylistDialog.destroy()
        self._savePlaylistDialog = None

    def _closeCb(self, widget):
        self.dialog.destroy()

    def _addCb(self, widget):
        self.showSavePlaylistDialog()

    def _fileSetCb(self, widget):
        playlist_out = widget.get_filename()
        shutil.copyfile(self.playlist_in, playlist_out)
        self.project.addUris([playlist_out])
        self.dialog.destroy()

    def run(self):
        self.dialog.run()
