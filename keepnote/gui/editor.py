"""

    KeepNote
    Editor widget in main window

"""


#
#  KeepNote
#  Copyright (c) 2008-2009 Matt Rasmussen
#  Author: Matt Rasmussen <rasmus@mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
#


# python imports
import gettext
import sys, os


_ = gettext.gettext


# pygtk imports
import pygtk
pygtk.require('2.0')
from gtk import gdk
import gtk.glade
import gobject

# keepnote imports
import keepnote
from keepnote import \
     KeepNoteError
from keepnote.notebook import \
     NoteBookError, \
     NoteBookVersionError
from keepnote import notebook as notebooklib
from keepnote.gui import richtext
from keepnote.gui.richtext import \
     RichTextView, RichTextIO, RichTextError, RichTextImage
from keepnote.gui import \
     get_resource, \
     get_resource_image, \
     get_resource_pixbuf, \
     Action, \
     ToggleAction, \
     update_file_preview
from keepnote.gui.font_selector import FontSelector
from keepnote.gui.colortool import FgColorTool, BgColorTool
from keepnote.gui.richtext.richtext_tags import color_tuple_to_string
from keepnote.gui import dialog_find

def set_menu_icon(uimanager, path, filename):
    item = uimanager.get_widget(path)
    img = gtk.Image()
    img.set_from_pixbuf(get_resource_pixbuf(filename))
    item.set_image(img)


class KeepNoteEditor (gtk.VBox):

    def __init__(self, app):
        gtk.VBox.__init__(self, False, 0)
        self._app = app
        self._notebook = None
        
        # state
        self._textview = RichTextView()    # textview
        self._page = None                  # current NoteBookPage
        self._page_scrolls = {}            # remember scroll in each page
        self._page_cursors = {}
        self._textview_io = RichTextIO()

        
        self._sw = gtk.ScrolledWindow()
        self._sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self._sw.set_shadow_type(gtk.SHADOW_IN)       
        self._sw.add(self._textview)
        self.pack_start(self._sw)
        
        self._textview.connect("font-change", self._on_font_callback)
        self._textview.connect("modified", self._on_modified_callback)
        self._textview.connect("child-activated", self._on_child_activated)
        self._textview.connect("visit-url", self._on_visit_url)
        self._textview.disable()
        self.show_all()


        self.find_dialog = dialog_find.KeepNoteFindDialog(self)


    def set_notebook(self, notebook):
        """Set notebook for editor"""

        # remove listener for old notebook
        if self._notebook:
            self._notebook.node_changed.remove(self._on_notebook_changed)

        # set new notebook
        self._notebook = notebook

        if self._notebook:
            # add listener and read default font
            self._notebook.node_changed.add(self._on_notebook_changed)
            self._textview.set_default_font(self._notebook.pref.default_font)
        else:
            # no new notebook, clear the view
            self.clear_view()

    def _on_notebook_changed(self, node, recurse):
        self._textview.set_default_font(self._notebook.pref.default_font)
    
    def _on_font_callback(self, textview, font):
        self.emit("font-change", font)
    
    def _on_modified_callback(self, textview, modified):
        self.emit("modified", self._page, modified)

    def _on_child_activated(self, textview, child):
        self.emit("child-activated", textview, child)


    def _on_visit_url(self, textview, url):
        
        if url.startswith("nbk:///"):
            nodeid = url[7:]
            node = self._notebook.get_node_by_id(nodeid)
            if node:
                self.emit("visit-node", node)

        else:
            try:
                self._app.open_webpage(url)
            except KeepNoteError, e:
                self.emit("error", e.msg, e)
                            
    
    def get_textview(self):
        return self._textview
    
        
    def is_focus(self):
        return self._textview.is_focus()


    def clear_view(self):
        self._page = None
        self._textview.disable()
    
    def view_pages(self, pages):
        """View a page"""
        
        # TODO: generalize to multiple pages
        assert len(pages) <= 1

        # save current page before changing pages
        self.save()

        if self._page is not None:
            mark = self._textview.get_buffer().get_insert()
            it = self._textview.get_buffer().get_iter_at_mark(mark)
            self._page_cursors[self._page] = it.get_offset()
            
            x, y = self._textview.window_to_buffer_coords(gtk.TEXT_WINDOW_TEXT, 0, 0)
            it = self._textview.get_iter_at_location(x, y)
            self._page_scrolls[self._page] = it.get_offset()
            

        pages = [node for node in pages
                 if node.get_attr("content_type") ==
                    notebooklib.CONTENT_TYPE_PAGE]
        
        if len(pages) == 0:            
            self.clear_view()
                
        else:
            page = pages[0]
            self._page = page
            self._textview.enable()

            try:
                self._textview_io.load(self._textview,
                                       self._textview.get_buffer(),
                                       self._page.get_data_file())

                # place cursor in last location
                if self._page in self._page_cursors:
                    offset = self._page_cursors[self._page]
                    it = self._textview.get_buffer().get_iter_at_offset(offset)
                    self._textview.get_buffer().place_cursor(it)

                # place scroll in last position
                if self._page in self._page_scrolls:
                    offset = self._page_scrolls[self._page]
                    buf = self._textview.get_buffer()
                    it = buf.get_iter_at_offset(offset)
                    mark = buf.create_mark(None, it, True)
                    self._textview.scroll_to_mark(mark,
                        0.49, use_align=True, xalign=0.0)
                    buf.delete_mark(mark)

            except RichTextError, e:
                self.clear_view()                
                self.emit("error", e.msg, e)
            except Exception, e:
                self.clear_view()
                self.emit("error", "Unknown error", e)
                
    
    def save(self):
        """Save the loaded page"""
        
        if self._page is not None and \
           self._page.is_valid() and \
           self._textview.is_modified():

            try:
                self._textview_io.save(self._textview.get_buffer(),
                                       self._page.get_data_file(),
                                       self._page.get_title())
                
            except RichTextError, e:
                self.emit("error", e.msg, e)
                return
            
            self._page.set_attr_timestamp("modified_time")
            
            try:
                self._page.save()
            except NoteBookError, e:
                self.emit("error", e.msg, e)
    
    def save_needed(self):
        """Returns True if textview is modified"""
        return self._textview.is_modified()


    #==================================================
    # Image/screenshot actions


    def on_screenshot(self):
        """Take and insert a screen shot image"""

        # do nothing if no page is selected
        if self._page is None:
            return

        imgfile = ""

        # Minimize window
        self.emit("window-request", "minimize")
        #self.minimize_window()
        
        try:
            imgfile = self._app.take_screenshot("keepnote")
            #self.restore_window()
            self.emit("window-request", "restore")
            
            # insert image
            self.insert_image(imgfile, "screenshot.png")
            
        except Exception, e:
            # catch exceptions for screenshot program
            #self.restore_window()
            self.emit("window-request", "restore")
            self.emit("error",
                      _("The screenshot program encountered an error:\n %s")
                       % str(e), e)
        
            
        # remove temp file
        try:
            if os.path.exists(imgfile):
                os.remove(imgfile)
        except OSError, e:
            self.emit("error",
                      _("%s was unable to remove temp file for screenshot") %
                       keepnote.PROGRAM_NAME)


    def on_insert_hr(self):
        """Insert horizontal rule into editor"""
        if self._page is None:
            return
        
        self._textview.insert_hr()

        
    def on_insert_image(self):
        """Displays the Insert Image Dialog"""
        
        if self._page is None:
            return
                
  
        dialog = gtk.FileChooserDialog(
            _("Insert Image From File"), self.get_toplevel(), 
            action=gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons=(_("Cancel"), gtk.RESPONSE_CANCEL,
                     _("Insert"), gtk.RESPONSE_OK))

        # setup preview
        preview = gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect("update-preview", update_file_preview, preview)

        if os.path.exists(self._app.pref.insert_image_path):
            dialog.set_current_folder(self._app.pref.insert_image_path)        
            
            
        # run dialog
        response = dialog.run()

        if response == gtk.RESPONSE_OK:
            self._app.pref.insert_image_path = dialog.get_current_folder()
            
            filename = dialog.get_filename()
                        
            imgname, ext = os.path.splitext(os.path.basename(filename))
            if ext.lower() in (".jpg", ".jpeg"):
                imgname = imgname + ".jpg"
            else:
                imgname = imgname + ".png"
            
            try:
                self.insert_image(filename, imgname)
            except Exception, e:
                # TODO: make exception more specific
                self.emit("error",
                          _("Could not insert image '%s'") % filename, e)
            
        dialog.destroy()
        


    
    def insert_image(self, filename, savename="image.png"):
        """Inserts an image into the text editor"""

        if self._page is None:
            return
        
        pixbuf = gdk.pixbuf_new_from_file(filename)
        img = RichTextImage()
        img.set_from_pixbuf(pixbuf)
        self._textview.insert_image(img, savename)






# add new signals to KeepNoteEditor
gobject.type_register(KeepNoteEditor)
gobject.signal_new("visit-node", KeepNoteEditor, gobject.SIGNAL_RUN_LAST, 
    gobject.TYPE_NONE, (object,))
gobject.signal_new("modified", KeepNoteEditor, gobject.SIGNAL_RUN_LAST, 
    gobject.TYPE_NONE, (object, bool))
gobject.signal_new("font-change", KeepNoteEditor, gobject.SIGNAL_RUN_LAST, 
    gobject.TYPE_NONE, (object,))
gobject.signal_new("error", KeepNoteEditor, gobject.SIGNAL_RUN_LAST, 
    gobject.TYPE_NONE, (str, object))
gobject.signal_new("child-activated", KeepNoteEditor, gobject.SIGNAL_RUN_LAST, 
    gobject.TYPE_NONE, (object, object))
gobject.signal_new("window-request", KeepNoteEditor, gobject.SIGNAL_RUN_LAST, 
    gobject.TYPE_NONE, (str,))



class FontUI (object):

    def __init__(self, widget, signal):
        self.widget = widget
        self.signal = signal



class EditorMenus (gobject.GObject):

    def __init__(self, editor):
        gobject.GObject.__init__(self)
        
        self._editor = editor
        self._font_ui_signals = []     # list of font ui widgets



    #=============================================================
    # Update UI (menubar) from font under cursor
    
    def on_font_change(self, editor, font):
        """Update the toolbar reflect the font under the cursor"""
        
        # block toolbar handlers
        for ui in self._font_ui_signals:
            ui.widget.handler_block(ui.signal)

        # update font mods
        self.bold.widget.set_active(font.mods["bold"])
        self.italic.widget.set_active(font.mods["italic"])
        self.underline.widget.set_active(font.mods["underline"])
        self.strike.widget.set_active(font.mods["strike"])
        self.fixed_width.widget.set_active(font.mods["tt"])
        self.link.widget.set_active(font.link is not None)
        self.no_wrap.widget.set_active(font.mods["nowrap"])
        
        # update text justification
        self.left_align.widget.set_active(font.justify == "left")
        self.center_align.widget.set_active(font.justify == "center")
        self.right_align.widget.set_active(font.justify == "right")
        self.fill_align.widget.set_active(font.justify == "fill")

        # update bullet list
        self.bullet.widget.set_active(font.par_type == "bullet")
        
        # update family/size buttons        
        self.font_family_combo.set_family(font.family)
        self.font_size_button.set_value(font.size)
        
        # unblock toolbar handlers
        for ui in self._font_ui_signals:
            ui.widget.handler_unblock(ui.signal)


    #==================================================
    # changing font handlers

    def on_mod(self, mod):
        """Toggle a font modification"""
        self._editor.get_textview().toggle_font_mod(mod)

        #font = self._editor.get_textview().get_font()        
        #mod_button.handler_block(mod_id)
        #mod_button.set_active(font.mods[mod])
        #mod_button.handler_unblock(mod_id)


    def on_toggle_link(self):

        textview = self._editor.get_textview()
        textview.toggle_link()
        tag, start, end = textview.get_link()

        if tag is not None:
            if tag.get_href() == "":
                # set default url to link text
                url = start.get_text(end)
                textview.set_link(url, start, end)
            self.emit("make-link")
    

    def on_justify(self, justify):
        """Set font justification"""
        self._editor.get_textview().set_justify(justify)
        font = self._editor.get_textview().get_font()
        self.on_font_change(self._editor, font)
        
    def on_bullet_list(self):
        """Toggle bullet list"""
        self._editor.get_textview().toggle_bullet()
        font = self._editor.get_textview().get_font()
        self.on_font_change(self._editor, font)
        
    def on_indent(self):
        """Indent current paragraph"""
        self._editor.get_textview().indent()

    def on_unindent(self):
        """Unindent current paragraph"""
        self._editor.get_textview().unindent()


    
    def on_family_set(self):
        """Set the font family"""
        self._editor.get_textview().set_font_family(
            self.font_family_combo.get_family())
        self._editor.get_textview().grab_focus()
        

    def on_font_size_change(self, size):
        """Set the font size"""
        self._editor.get_textview().set_font_size(size)
        self._editor.get_textview().grab_focus()
    
    def on_font_size_inc(self):
        """Increase font size"""
        font = self._editor.get_textview().get_font()
        font.size += 2        
        self._editor.get_textview().set_font_size(font.size)
        self.on_font_change(self._editor, font)
    
    
    def on_font_size_dec(self):
        """Decrease font size"""
        font = self._editor.get_textview().get_font()
        if font.size > 4:
            font.size -= 2
        self._editor.get_textview().set_font_size(font.size)
        self.on_font_change(self._editor, font)


    def on_color_set(self, kind, color=0):
        """Set text/background color"""
        
        if color == 0:
            if kind == "fg":
                color = self.fg_color_button.color
            elif kind == "bg":
                color = self.bg_color_button.color
            else:
                color = None

        if color is not None:
            colorstr = color_tuple_to_string(color)
        else:
            colorstr = None

        if kind == "fg":
            self._editor.get_textview().set_font_fg_color(colorstr)
        elif kind == "bg":
            self._editor.get_textview().set_font_bg_color(colorstr)
        else:
            raise Exception("unknown color type '%s'" % str(kind))
        

    def on_choose_font(self):
        """Callback for opening Choose Font Dialog"""
        
        font = self._editor.get_textview().get_font()

        dialog = gtk.FontSelectionDialog("Choose Font")
        dialog.set_font_name("%s %d" % (font.family, font.size))
        response = dialog.run()

        if response == gtk.RESPONSE_OK:
            self._editor.get_textview().set_font(dialog.get_font_name())
            self._editor.get_textview().grab_focus()

        dialog.destroy()


    def _make_toggle_button(self, toolbar, tips, tip_text, icon, 
                            stock_id=None, 
                            func=lambda: None,
                            use_stock_icons=False):

        button = gtk.ToggleToolButton()
        if use_stock_icons and stock_id:
            button.set_stock_id(stock_id)
        else:
            button.set_icon_widget(get_resource_image(icon))
        signal = button.connect("toggled", lambda w: func())
        font_ui = FontUI(button, signal)
        self._font_ui_signals.append(font_ui)
        
        toolbar.insert(button, -1)
        tips.set_tip(button, tip_text)

        return font_ui


    def make_toolbar(self, toolbar, tips, use_stock_icons):
        
        # bold tool
        self.bold = self._make_toggle_button(
            toolbar, tips,
            "Bold", "bold.png", gtk.STOCK_BOLD,
            lambda: self._editor.get_textview().toggle_font_mod("bold"),
            use_stock_icons)
        
        # italic tool
        self.italic = self._make_toggle_button(
            toolbar, tips,
            "Italic", "italic.png", gtk.STOCK_ITALIC,
            lambda: self._editor.get_textview().toggle_font_mod("italic"),
            use_stock_icons)

        # underline tool
        self.underline = self._make_toggle_button(
            toolbar, tips,
            "Underline", "underline.png", gtk.STOCK_UNDERLINE,
            lambda: self._editor.get_textview().toggle_font_mod("underline"),
            use_stock_icons)

        # strikethrough
        self.strike = self._make_toggle_button(
            toolbar, tips,
            "Strike", "strike.png", gtk.STOCK_STRIKETHROUGH,
            lambda: self._editor.get_textview().toggle_font_mod("strike"),
            use_stock_icons)
        
        # fixed-width tool
        self.fixed_width = self._make_toggle_button(
            toolbar, tips,
            "Monospace", "fixed-width.png", None,
            lambda: self._editor.get_textview().toggle_font_mod("tt"),
            use_stock_icons)

        # link
        self.link = self._make_toggle_button(
            toolbar, tips,
            "Make Link", "link.png", None,
            self.on_toggle_link,
            use_stock_icons)

        # no wrap tool
        self.no_wrap = self._make_toggle_button(
            toolbar, tips,
            "No Wrapping", "no-wrap.png", None,
            lambda: self._editor.get_textview().toggle_font_mod("nowrap"),
            use_stock_icons)

        

        # family combo
        self.font_family_combo = FontSelector()
        self.font_family_combo.set_size_request(150, 25)
        item = gtk.ToolItem()
        item.add(self.font_family_combo)
        tips.set_tip(item, "Font Family")
        toolbar.insert(item, -1)
        self.font_family_id = self.font_family_combo.connect("changed",
            lambda w: self.on_family_set())
        self._font_ui_signals.append(FontUI(self.font_family_combo,
                                           self.font_family_id))
                
        # font size
        DEFAULT_FONT_SIZE = 10
        self.font_size_button = gtk.SpinButton(
          gtk.Adjustment(value=DEFAULT_FONT_SIZE, lower=2, upper=500, 
                         step_incr=1))
        self.font_size_button.set_size_request(-1, 25)
        #self.font_size_button.set_range(2, 100)
        self.font_size_button.set_value(DEFAULT_FONT_SIZE)
        self.font_size_button.set_editable(False)
        item = gtk.ToolItem()
        item.add(self.font_size_button)
        tips.set_tip(item, "Font Size")
        toolbar.insert(item, -1)
        self.font_size_id = self.font_size_button.connect("value-changed",
            lambda w: 
            self.on_font_size_change(self.font_size_button.get_value()))
        self._font_ui_signals.append(FontUI(self.font_size_button,
                                           self.font_size_id))


        # font fg color
        # TODO: code in proper default color
        self.fg_color_button = FgColorTool(14, 15, (0, 0, 0))
        self.fg_color_button.connect("set-color",
            lambda w, color: self.on_color_set("fg", color))
        tips.set_tip(self.fg_color_button, "Set Text Color")
        toolbar.insert(self.fg_color_button, -1)
        

        # font bg color
        self.bg_color_button = BgColorTool(14, 15, (65535, 65535, 65535))
        self.bg_color_button.connect("set-color",
            lambda w, color: self.on_color_set("bg", color))
        tips.set_tip(self.bg_color_button, "Set Background Color")
        toolbar.insert(self.bg_color_button, -1)

                
        
        # separator
        toolbar.insert(gtk.SeparatorToolItem(), -1)
        
                
        # left tool
        self.left_align = self._make_toggle_button(
            toolbar, tips,
            "Left Align", "alignleft.png", gtk.STOCK_JUSTIFY_LEFT,
            lambda: self.on_justify("left"),
            use_stock_icons)

        # center tool
        self.center_align = self._make_toggle_button(
            toolbar, tips,
            "Center Align", "aligncenter.png", gtk.STOCK_JUSTIFY_CENTER,
            lambda: self.on_justify("center"),
            use_stock_icons)

        # right tool
        self.right_align = self._make_toggle_button(
            toolbar, tips,
            "Right Align", "alignright.png", gtk.STOCK_JUSTIFY_RIGHT,
            lambda: self.on_justify("right"),
            use_stock_icons)

        # justify tool
        self.fill_align = self._make_toggle_button(
            toolbar, tips,
            "Justify Align", "alignjustify.png", gtk.STOCK_JUSTIFY_FILL,
            lambda: self.on_justify("fill"),
            use_stock_icons)
        
        
        # bullet list tool
        self.bullet = self._make_toggle_button(
            toolbar, tips,
            "Bullet List", "bullet.png", None,
            lambda: self.on_bullet_list(),
            use_stock_icons)

    def get_actions(self):
        
        return map(lambda x: Action(*x), [
            ("Insert Horizontal Rule", None, _("Insert _Horizontal Rule"),
             "<control>H", None,
             lambda w: self._editor.on_insert_hr()),
            
            ("Insert Image", None, _("Insert _Image"),
             "", None,
             lambda w: self._editor.on_insert_image()),
            
            ("Insert Screenshot", None, _("Insert _Screenshot"),
             "<control>Insert", None,
             lambda w: self._editor.on_screenshot()),


            # finding
            ("Find In Page", gtk.STOCK_FIND, _("_Find In Page"),
             "<control>F", None,
             lambda w: self._editor.find_dialog.on_find(False)),
            
            ("Find Next In Page", gtk.STOCK_FIND, _("Find _Next In Page"),
             "<control>G", None,
             lambda w: self._editor.find_dialog.on_find(False, forward=True)),
                        
            ("Find Previous In Page", gtk.STOCK_FIND,
             _("Find Pre_vious In Page"),
             "<control><shift>G", None,
             lambda w: self._editor.find_dialog.on_find(False, forward=False)),
            
            ("Replace In Page", gtk.STOCK_FIND_AND_REPLACE, 
             _("_Replace In Page"), 
             "<control><shift>R", None,
             lambda w: self._editor.find_dialog.on_find(True)),


            
            ("Format", None, _("Fo_rmat")),

            ("Bold", None, _("_Bold"), 
             "<control>B", None,
             lambda w: self.on_mod("bold")),
            
            ("Italic", None, _("_Italic"), 
             "<control>I", None,
             lambda w: self.on_mod("italic")),
            
            ("Underline", None, "_Underline", 
             "<control>U", None,
             lambda w: self.on_mod("underline")),
            
            ("Strike", None, _("S_trike"),
             "", None,
             lambda w: self.on_mod("strike")),
            
            ("Monospace", None, _("_Monospace"),
             "<control>M", None,
             lambda w: self.on_mod("tt")),
            
            ("Link", None, _("Lin_k"),
             "<control>L", None,
             lambda w: self.on_toggle_link()),
            
            ("No Wrapping", None, _("No _Wrapping"),
             "", None,
             lambda w: self.on_mod("nowrap")),
            
            ("Left Align", None, _("_Left Align"), 
             "<shift><control>L", None,
             lambda w: self.on_justify("left")),
            
            ("Center Align", None, _("C_enter Align"), 
             "<shift><control>E", None,
             lambda w: self.on_justify("center")),
            
            ("Right Align", None, _("_Right Align"), 
             "<shift><control>R", None,
             lambda w: self.on_justify("right")),
            
            ("Justify Align", None, _("_Justify Align"), 
             "<shift><control>J", None,
             lambda w: self.on_justify("fill")),

            ("Bullet List", None, _("_Bullet List"), 
             "<control>asterisk", None,
             lambda w: self.on_bullet_list()),
            
            ("Indent More", None, _("Indent M_ore"), 
             "<control>parenright", None,
             lambda w: self.on_indent()),
            
            ("Indent Less", None, _("Indent Le_ss"), 
             "<control>parenleft", None,
             lambda w: self.on_unindent()),
            
            ("Increase Font Size", None, _("Increase Font _Size"), 
             "<control>equal", None,
             lambda w: self.on_font_size_inc()),
            
            ("Decrease Font Size", None, _("_Decrease Font Size"),
             "<control>minus", None,
             lambda w: self.on_font_size_dec()),

            ("Apply Text Color", None, _("_Apply Text Color"), 
             "", None,
             lambda w: self.on_color_set("fg")),
            
            ("Apply Background Color", None, _("A_pply Background Color"), 
             "", None,
             lambda w: self.on_color_set("bg")),
                        
            ("Choose Font", None, _("Choose _Font"), 
             "<control><shift>F", None,
             lambda w: self.on_choose_font())
        ])
        

    def get_ui(self):

        return ["""
        <ui>
        <menubar name="main_menu_bar">
          <menu action="Edit">
            <placeholder name="Editor">
              <menuitem action="Insert Horizontal Rule"/>
              <menuitem action="Insert Image"/>
              <menuitem action="Insert Screenshot"/>
            </placeholder>
          </menu>
          <menu action="Search">
            <placeholder name="Editor">
              <menuitem action="Find In Page"/>
              <menuitem action="Find Next In Page"/>
              <menuitem action="Find Previous In Page"/>
              <menuitem action="Replace In Page"/>
            </placeholder>
          </menu>
          <placeholder name="Editor">
          <menu action="Format">
            <menuitem action="Bold"/>
            <menuitem action="Italic"/>
            <menuitem action="Underline"/>
            <menuitem action="Strike"/>
            <menuitem action="Monospace"/>
            <menuitem action="Link"/>
            <menuitem action="No Wrapping"/>
            <menuitem action="Left Align"/>
            <menuitem action="Center Align"/>
            <menuitem action="Right Align"/>
            <menuitem action="Justify Align"/>
            <menuitem action="Bullet List"/>
            <menuitem action="Indent More"/>
            <menuitem action="Indent Less"/>
            <menuitem action="Increase Font Size"/>
            <menuitem action="Decrease Font Size"/>
            <menuitem action="Apply Text Color"/>
            <menuitem action="Apply Background Color"/>
            <menuitem action="Choose Font"/>
          </menu>
          </placeholder>
        </menubar>
        </ui>
        """]

    def setup_menu(self, uimanager):

        u = uimanager
        
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Bold",
                      get_resource("images", "bold.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Italic",
                      get_resource("images", "italic.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Underline",
                      get_resource("images", "underline.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Strike",
                      get_resource("images", "strike.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Monospace",
                      get_resource("images", "fixed-width.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Link",
                      get_resource("images", "link.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/No Wrapping",
                      get_resource("images", "no-wrap.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Left Align",
                      get_resource("images", "alignleft.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Center Align",
                      get_resource("images", "aligncenter.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Right Align",
                      get_resource("images", "alignright.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Justify Align",
                      get_resource("images", "alignjustify.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Bullet List",
                      get_resource("images", "bullet.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Indent More",
                      get_resource("images", "indent-more.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Indent Less",
                      get_resource("images", "indent-less.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Increase Font Size",
                      get_resource("images", "font-inc.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Decrease Font Size",
                      get_resource("images", "font-dec.png"))
        set_menu_icon(u, "/main_menu_bar/Editor/Format/Choose Font",
                      get_resource("images", "font.png"))

        
    def set_menu_icon(self, uimanager, path, filename):
        item = uimanager.get_widget(path)
        img = gtk.Image()
        img.set_from_pixbuf(get_resource_pixbuf(filename))
        item.set_image(img)        
            


gobject.type_register(EditorMenus)
gobject.signal_new("make-link", EditorMenus, gobject.SIGNAL_RUN_LAST,
                   gobject.TYPE_NONE, ())
