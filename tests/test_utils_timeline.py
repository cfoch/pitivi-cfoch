# -*- coding: utf-8 -*-
#
# Copyright (c) 2013, Alex Băluț <alexandru.balut@gmail.com>
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

from unittest import TestCase, mock

from gi.repository import GES

from tests import common

from pitivi.application import Pitivi
from pitivi.utils.timeline import Selected, Selection, SELECT, SELECT_ADD, \
    UNSELECT


class TestSelected(TestCase):

    def testBoolEvaluation(self):
        selected = Selected()
        self.assertFalse(selected)

        selected.selected = True
        self.assertTrue(selected)

        selected.selected = False
        self.assertFalse(selected)


class TestSelection(TestCase):
    def setUp(self):
        app = Pitivi()
        app._startupCb(app)
        app.project_manager.newBlankProject()

        self.timeline = app.project_manager.current_project.timeline
        self.layer = self.timeline.append_layer()

    def testBoolEvaluation(self):
        clip1 = GES.TitleClip()
        self.layer.add_clip(clip1)

        # Remember that Selected __init__ as False
        clip1.selected = Selected()
        source1 = clip1.get_children(False)[0]
        source1.selected = Selected()
        clip1.ui = mock.MagicMock()

        selection = Selection()
        self.assertFalse(selection)
        selection.setSelection([clip1], SELECT)
        self.assertTrue(selection)
        selection.setSelection([clip1], SELECT_ADD)
        self.assertTrue(selection)
        selection.setSelection([clip1], UNSELECT)
        self.assertFalse(selection)

    def testGetSingleClip(self):
        selection = Selection()
        uri = common.TestCase.getSampleUri("tears_of_steel.webm")
        asset = GES.UriClipAsset.request_sync(uri)

        clip1 = asset.extract()
        clip2 = GES.TitleClip()

        self.layer.add_clip(clip1)
        self.layer.add_clip(clip2)

        # Remember that Selected __init__ as False
        clip1.selected = Selected()
        for source in clip1.get_children(False):
            source.selected = Selected()
        clip1.ui = None

        clip2.selected = Selected()
        source2 = clip2.get_children(False)[0]
        source2.selected = Selected()
        clip2.ui = None

        # Selection empty.
        self.assertFalse(selection.getSingleClip(GES.TitleClip))

        # Selection contains only a non-requested-type clip.
        selection.setSelection([clip1], SELECT)
        self.assertFalse(selection.getSingleClip(GES.TitleClip))

        # Selection contains only requested-type clip.
        selection.setSelection([clip2], SELECT)
        self.assertEqual(clip2, selection.getSingleClip(GES.TitleClip))

        # Selection contains more than one clip.
        selection.setSelection([clip1, clip2], SELECT)
        self.assertFalse(selection.getSingleClip(GES.UriClip))
