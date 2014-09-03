import os
import time
import tempfile
from urllib.parse import urlparse
from gettext import ngettext, gettext as _

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository.GdkPixbuf import Pixbuf
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import Gst

from pitivi.configure import get_ui_dir
from pitivi.utils.widgets import FractionWidget
from pitivi.utils.imagesequences import ImageSequencePlaylist

from IPython import embed


class ImageSequenceEditor:
    DEFAULT_ROWS_NUMBER = 4
    DEFAULT_IMAGE_WIDTH = 240
    DEFAULT_WINDOW_WIDTH = 240 * DEFAULT_ROWS_NUMBER
    DEFAULT_WINDOW_HEIGHT = 200

    def __init__(self, app, playlist):
        self.app = app
        self.builder = Gtk.Builder()
        self.builder.add_from_file(os.path.join(get_ui_dir(), "imagesequence_dialog.ui"))

        self.dialog = self.builder.get_object("dialog")
        self.dialog.set_default_size(self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT)
        self.playlist = playlist

        self.scrolled = self.builder.get_object("scrolled")
        self.scrolled.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.NEVER)

        self.iconview = self.builder.get_object("iconview")
        self.liststore = Gtk.ListStore(Pixbuf, str)
        self.iconview.set_tooltip_column(1)

        # Beautify the iconview
        self.iconview.set_model(self.liststore)
        self.iconview.set_pixbuf_column(0)
        self.iconview.set_text_column(1)
        self.iconview.set_columns(0)
        self.iconview.set_margin(0)
        self.iconview.set_column_spacing(0)
        self.iconview.set_item_padding(0)
        self.iconview.set_item_width(0)

        self._addDialog = None

        self._framerate_toolitem = self.builder.get_object("framerate_toolitem")
        self.progressbar = self.builder.get_object("progressbar")
        self.add_button = self.builder.get_object("add_button")
        self.framerate_w = FractionWidget()
        self._framerate_toolitem.add(self.framerate_w)

        # self.create_button = self.builder.get_object("create_button")
        # self.create_button.connect("clicked", self._createCb)
        self.dialog.show_all()

        # Utilities to import items and updating the progressbar
        self.thumbnailer = self._getThumbnailer()

        self.filenames = []
        self.pending_uris = []
        self.pending_items = []
        self._current_item_number = 0
        self._imported_items_total = 0

        self.builder.connect_signals(self)

    def run(self):
        self.playlist = ImageSequencePlaylist(self.playlist)
        if not self.playlist.parse():
            return
        self.framerate_w.setWidgetValue("%d:%d" %
            (self.playlist.framerate.num, self.playlist.framerate.denom))
        self._loadClipImages()
        self.dialog.run()

    @staticmethod
    def _getThumbnailer():
        # if not GNOMEDESKTOP_SOFT_DEPENDENCY:
        #    return None
        from gi.repository import GnomeDesktop
        # We need to instanciate the thumbnail factory on the main thread...
        size_normal = GnomeDesktop.DesktopThumbnailSize.NORMAL
        return GnomeDesktop.DesktopThumbnailFactory.new(size_normal)

    def _loadClipImages(self):
        uris = ["file://" + filename for filename in self.playlist.filenames]
        self.pending_uris += uris
        self._imported_items_total = len(self.pending_uris)
        GObject.timeout_add(100, self._add_icons)

    def _add_icons(self):
        if len(self.pending_uris) > 0:
            uri = self.pending_uris.pop(0)
            self._add_icon(uri)
            return True
        # Add the rest of items
        self._flush_pending_items()
        return False

    def _get_pixbuf(self, uri):
        image_file = Gio.file_new_for_uri(uri)
        info = image_file.query_info(attributes="standard::*",
                                    flags=Gio.FileQueryInfoFlags.NONE,
                                    cancellable=None)
        mime = Gio.content_type_get_mime_type(info.get_content_type())
        pixbuf = self.thumbnailer.generate_thumbnail(uri, mime)
        return pixbuf

    def _add_icon(self, uri):
        interpolation = GdkPixbuf.InterpType.BILINEAR

        path = urlparse(uri)[2]
        filename = os.path.basename(path)

        self.filenames.append(path)

        pixbuf = self._get_pixbuf(uri)
        item = [pixbuf, path]
        self.pending_items.append(item)

        self._current_item_number += 1
        self._update_progressbar()

        if len(self.pending_items) > 50:
            self._flush_pending_items()

    def _update_progressbar(self):
        fraction = self._current_item_number / self._imported_items_total

        progressbar_text = _("Importing clip %(current_clip)d of %(total)d" %
            {"current_clip": self._current_item_number + 1,
            "total": self._imported_items_total})

        self.progressbar.set_text(progressbar_text)
        self.progressbar.set_fraction(fraction)

    def _flush_pending_items(self):
        for item in self.pending_items:
            self.liststore.append(item)
            # Get the iconview growing horizontally
            # TODO: There should be a smarter way to get iconview growing horizontally
            columns = self.iconview.get_columns()
            self.iconview.set_columns(columns + 1)
        del self.pending_items[:]

    def _get_filenames(self):
        filenames = []
        for item in self.liststore:
            filenames.append(item[1])
        return filenames

    # Callbacks
    def _addCb(self, button):
        chooser_action = Gtk.FileChooserAction.OPEN
        dialogtitle = _("Add one or more frames")

        self._addDialog = Gtk.FileChooserDialog(title=dialogtitle, transient_for=None,
                                        action=chooser_action)
        self._addDialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,
                                    Gtk.STOCK_ADD, Gtk.ResponseType.OK)
        self._addDialog.connect('response', self._addDialogResponseCb)
        self._addDialog.connect('close', self._dialogBoxCloseCb)
        self._addDialog.set_select_multiple(True)

        # Allow only png or jpeg files
        file_filter = Gtk.FileFilter()
        file_filter.add_mime_type("image/png")
        file_filter.add_mime_type("image/jpeg")

        self._addDialog.add_filter(file_filter)
        self._addDialog.run()

    def _saveCb(self, button):
        dialogtitle = _("Create Image Sequence Playlist")
        chooser_action = Gtk.FileChooserAction.SAVE
        self._saveDialog = Gtk.FileChooserDialog(title=dialogtitle,
            transient_for=None, action=chooser_action)
        self._saveDialog.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,
            Gtk.STOCK_ADD, Gtk.ResponseType.OK)
        self._saveDialog.connect('response', self._saveDialogResponseCb)
        self._saveDialog.run()

    def _addDialogResponseCb(self, dialogbox, response):
        if response == Gtk.ResponseType.OK:
            uris = self._addDialog.get_uris()
            self.pending_uris += uris
            self._imported_items_total = len(self.pending_uris)
            GObject.timeout_add(100, self._add_icons)
        dialogbox.destroy()
        self._addDialog = None

    def _dialogBoxCloseCb(self, dialogbox):
        dialogbox.destroy()
        self._addDialog = None

    def _saveDialogResponseCb(self, dialogbox, response):
        if response == Gtk.ResponseType.OK:
            filename = urlparse(dialogbox.get_uri())[2]
            self.playlist.filenames = self._get_filenames()
            self.playlist.framerate = self.framerate_w.getWidgetValue()
            self.playlist.save(filename)
            embed()
            self.app.project_manager.current_project.addUris([self.playlist.get_uri()])
            self.dialog.destroy()
        self._saveDialog.destroy()
        self._saveDialog = None

    def _closeCb(self, unused_dialogbox):
        self.dialog.destroy()
