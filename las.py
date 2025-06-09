#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf
import threading
import os
import subprocess

from core.password_dialog import PasswordDialog

GLADE_FILE = "ui/splash.glade"
LOGO_FILE = "assets/logo.png"

class SplashScreen:
    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file(GLADE_FILE)
        self.window = self.builder.get_object("splash_window")
        self.spinner = self.builder.get_object("splash_spinner")
        self.progress = self.builder.get_object("splash_progress")
        self.logo_image = self.builder.get_object("logo_image")
        self._set_logo(LOGO_FILE)
        self.progress_fraction = 0.0
        self.process_complete = False
        self.password_attempts = 0
        self.max_attempts = 3
        self.password = None

    def _set_logo(self, logo_path):
        if os.path.exists(logo_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, 512, 512, True)
            self.logo_image.set_from_pixbuf(pixbuf)

    def ask_for_password(self):
        dialog = PasswordDialog(self.window)
        password = None
        while self.password_attempts < self.max_attempts:
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                password = dialog.get_password()
                if self.check_password(password):
                    dialog.destroy()
                    return password
                else:
                    self.password_attempts += 1
                    dialog.shake()   # You must implement shake() in your PasswordDialog!
                    dialog.clear_password()  # You must implement clear_password()!
            else:
                dialog.destroy()
                Gtk.main_quit()
                return None
        dialog.destroy()
        self.show_error_dialog("Wrong Password", "You entered the wrong password three times.")
        GLib.idle_add(Gtk.main_quit)
        return None

    def check_password(self, password):
        # Test the password non-intrusively using 'sudo -S -v'
        try:
            proc = subprocess.Popen(
                ['sudo', '-S', '-k', '-v'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            proc.stdin.write(password + '\n')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    def show(self):
        self.spinner.start()
        self.window.show_all()
        password = self.ask_for_password()
        if not password:
            return
        self.password = password
        threading.Thread(target=self.long_task, daemon=True).start()
        GLib.timeout_add(50, self.fake_progress)

    def fake_progress(self):
        if self.process_complete:
            if self.progress_fraction < 1.0:
                self.progress_fraction += 0.1
                if self.progress_fraction > 1.0:
                    self.progress_fraction = 1.0
                self.progress.set_fraction(self.progress_fraction)
                return True
            else:
                return False
        else:
            if self.progress_fraction < 0.8:
                self.progress_fraction += 0.005
                if self.progress_fraction > 0.8:
                    self.progress_fraction = 0.8
                self.progress.set_fraction(self.progress_fraction)
            return True

    def long_task(self):
        cmd = ['sudo', '-S', 'apt', 'update']
        output_lines = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            try:
                proc.stdin.write(self.password + '\n')
                proc.stdin.flush()
            except Exception as e:
                GLib.idle_add(self.show_error_dialog, "Failed to send password to sudo", str(e))
                GLib.idle_add(Gtk.main_quit)
                return

            for line in proc.stdout:
                output_lines.append(line)
            proc.wait()
            if proc.returncode != 0:
                error_text = "".join(output_lines)
                if "Could not get lock" in error_text:
                    error_message = "Another package manager is currently using apt. Please close it and try again."
                else:
                    error_message = error_text.strip() or "Unknown error occurred during apt update."
                GLib.idle_add(self.show_error_dialog, "apt update failed", error_message)
                GLib.idle_add(Gtk.main_quit)
                return
            else:
                print("apt update succeeded.")
        except Exception as e:
            GLib.idle_add(self.show_error_dialog, "Error running apt update", str(e))
            GLib.idle_add(Gtk.main_quit)
            return
        self.process_complete = True
        GLib.idle_add(self.check_progress_completion)

    def check_progress_completion(self):
        if self.progress_fraction >= 1.0:
            self.on_finish()
        else:
            GLib.timeout_add(50, self.check_progress_completion)
        return False

    def show_error_dialog(self, title, message):
        dialog = Gtk.MessageDialog(
            parent=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def on_finish(self):
        self.spinner.stop()
        self.window.destroy()
        print("Splash complete! Launch main window here...")

def main():
    splash = SplashScreen()
    splash.show()
    Gtk.main()

if __name__ == "__main__":
    main()
