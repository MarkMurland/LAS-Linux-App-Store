import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

class PasswordDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(
            title="Authentication Required",
            transient_for=parent,
            flags=0,
        )
        self.set_default_size(300, 100)

        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )

        box = self.get_content_area()
        label = Gtk.Label(label="Enter your password to update package list:")
        self.entry = Gtk.Entry()
        self.entry.set_visibility(False)
        self.entry.set_invisible_char('*')
        self.entry.set_activates_default(True)

        box.set_spacing(8)
        box.add(label)
        box.add(self.entry)

        self.set_default_response(Gtk.ResponseType.OK)
        self.show_all()

    def get_password(self):
        return self.entry.get_text()

    def shake(self):
        # Simple shake animation: move window left-right quickly
        win = self.get_window()
        if win:
            x, y = win.get_position()
            for _ in range(3):
                win.move(x + 10, y)
                while Gtk.events_pending():
                    Gtk.main_iteration()
                win.move(x - 10, y)
                while Gtk.events_pending():
                    Gtk.main_iteration()
            win.move(x, y)

    def clear_password(self):
        self.entry.set_text("")