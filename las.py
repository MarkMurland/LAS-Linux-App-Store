#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango, Gdk, GLib, GdkPixbuf
import apt
import os
import configparser
import re
import subprocess
import platform
import shutil
import logging
from threading import Thread, Lock

# Set up logging
logging.basicConfig(filename='las.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Thread lock for apt.Cache
apt_lock = Lock()

# Icon aliases for common packages
ICON_ALIASES = {
    'obs-studio': 'obs',
    'vokoscreen-ng': 'vokoscreen',
    'firefox': 'firefox',
    'chromium-browser': 'chromium',
    'vlc': 'vlc',
    'gimp': 'gimp',
    'libreoffice': 'libreoffice-startcenter',
    'code': 'visual-studio-code',
    'spotify': 'spotify-client',
    'discord': 'discord',
    'telegram': 'telegram',
    'steam': 'steam',
}

# Categories for apps
APP_CATEGORIES = {
    'Development': ['code', 'vim', 'git', 'nodejs', 'python3', 'gcc', 'make', 'cmake', 'build-essential', 'gdb', 'valgrind'],
    'Graphics': ['gimp', 'inkscape', 'blender', 'krita', 'darktable', 'rawtherapee', 'scribus'],
    'Internet': ['firefox', 'chromium-browser', 'thunderbird', 'filezilla', 'transmission', 'qbittorrent', 'wget', 'curl'],
    'Office': ['libreoffice', 'libreoffice-writer', 'libreoffice-calc', 'libreoffice-impress', 'calibre', 'okular'],
    'Multimedia': ['vlc', 'audacity', 'obs-studio', 'kdenlive', 'handbrake', 'audacious', 'rhythmbox'],
    'Games': ['steam', '0ad', 'supertuxkart', 'frozen-bubble', 'gnome-games', 'lutris'],
    'System': ['htop', 'neofetch', 'tree', 'curl', 'wget', 'synaptic', 'gparted', 'bleachbit'],
    'Communication': ['discord', 'telegram-desktop', 'slack-desktop', 'zoom', 'skype', 'signal-desktop'],
}

# Featured/recommended apps
FEATURED_APPS = [
    'firefox', 'vlc', 'gimp', 'libreoffice', 'code', 'obs-studio', 
    'audacity', 'thunderbird', 'steam', 'discord'
]

def get_icon_for_package(package_name):
    """Fetch an icon for a package from .desktop files or fallbacks."""
    logging.debug(f"Loading icon for package: {package_name}")
    icon_theme = Gtk.IconTheme.get_default()
    desktop_dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications")
    ]

    main()
