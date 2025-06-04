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

    icon_name = package_name
    for ddir in desktop_dirs:
        if not os.path.exists(ddir):
            continue
        desktop_file = os.path.join(ddir, f"{package_name}.desktop")
        if not os.path.isfile(desktop_file):
            try:
                for f in os.listdir(ddir):
                    if f.lower().startswith(package_name.lower()) and f.endswith(".desktop"):
                        desktop_file = os.path.join(ddir, f)
                        break
                else:
                    continue
            except PermissionError:
                logging.warning(f"Permission denied accessing {ddir}")
                continue
        try:
            config = configparser.ConfigParser()
            if config.read(desktop_file) and config.has_option('Desktop Entry', 'Icon'):
                icon_name = config.get('Desktop Entry', 'Icon')
                logging.debug(f"Found icon {icon_name} in {desktop_file}")
                break
        except Exception as e:
            logging.error(f"Error reading desktop file {desktop_file}: {e}")
            continue

    for name in (icon_name, icon_name.lower().replace('.', '-'), ICON_ALIASES.get(package_name.lower(), '')):
        if name and icon_theme.has_icon(name):
            try:
                return icon_theme.load_icon(name, 64, 0)
            except Exception as e:
                logging.error(f"Error loading icon {name}: {e}")
                continue
    try:
        return icon_theme.load_icon("application-x-executable", 64, 0)
    except Exception as e:
        logging.error(f"Error loading fallback icon: {e}")
        return None  # Optionally, add a default icon file path

def load_icon_async(package_name, callback):
    """Load icon asynchronously to avoid blocking the UI."""
    def do_load():
        pixbuf = get_icon_for_package(package_name)
        GLib.idle_add(callback, pixbuf)
    Thread(target=do_load, daemon=True).start()

def get_package_info(package_name):
    """Get detailed package information including size, dependencies, etc."""
    logging.debug(f"Getting package info for {package_name}")
    try:
        with apt_lock:
            cache = apt.Cache()
            if package_name in cache:
                pkg = cache[package_name]
                info = {
                    'name': package_name,
                    'installed': pkg.is_installed,
                    'description': 'No description available',
                    'size': 'Unknown',
                    'version': 'Unknown',
                    'dependencies': [],
                    'homepage': None
                }
                
                if pkg.versions:
                    version = pkg.versions[0]
                    info['description'] = version.description or 'No description available'
                    info['size'] = f"{version.size / 1024 / 1024:.1f} MB"
                    info['version'] = version.version
                    if hasattr(version, 'homepage') and version.homepage:
                        info['homepage'] = version.homepage
                    
                    # Get dependencies
                    if version.dependencies:
                        deps = []
                        for dep_group in version.dependencies:
                            for dep in dep_group:
                                deps.append(dep.name)
                        info['dependencies'] = deps[:10]  # Limit to first 10
                
                return info
    except Exception as e:
        logging.error(f"Error getting package info for {package_name}: {e}")
    return None

class PackageInfoDialog(Gtk.Dialog):
    """Dialog to show detailed package information."""
    
    def __init__(self, parent, package_name):
        super().__init__(title=f"Package Info - {package_name}", transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(500, 400)
        
        content_area = self.get_content_area()
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        content_area.pack_start(scrolled, True, True, 0)
        
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.info_box.set_margin_left(20)
        self.info_box.set_margin_right(20)
        self.info_box.set_margin_top(20)
        self.info_box.set_margin_bottom(20)
        scrolled.add(self.info_box)
        
        # Loading spinner
        spinner = Gtk.Spinner()
        spinner.start()
        self.info_box.pack_start(spinner, False, False, 0)
        
        # Load package info in background
        def load_info():
            info = get_package_info(package_name)
            GLib.idle_add(self.update_info, info, spinner)
        
        Thread(target=load_info, daemon=True).start()
        self.show_all()
    
    def update_info(self, info, spinner):
        """Update the dialog with package information."""
        spinner.stop()
        spinner.hide()
        
        if not info:
            error_label = Gtk.Label(label="Failed to load package information")
            self.info_box.pack_start(error_label, False, False, 0)
            self.show_all()
            return
        
        # Package name and version
        name_label = Gtk.Label()
        name_label.set_markup(f"<b><big>{info['name']}</big></b>\nVersion: {info['version']}")
        name_label.set_xalign(0)
        name_label.set_yalign(0)
        self.info_box.pack_start(name_label, False, False, 0)
        
        # Status
        status = "Installed" if info['installed'] else "Not Installed"
        status_label = Gtk.Label(label=f"Status: {status}")
        status_label.set_xalign(0)
        status_label.set_yalign(0)
        self.info_box.pack_start(status_label, False, False, 0)
        
        # Size
        size_label = Gtk.Label(label=f"Size: {info['size']}")
        size_label.set_xalign(0)
        size_label.set_yalign(0)
        self.info_box.pack_start(size_label, False, False, 0)
        
        # Description
        desc_label = Gtk.Label()
        desc_label.set_markup("<b>Description:</b>")
        desc_label.set_xalign(0)
        desc_label.set_yalign(0)
        self.info_box.pack_start(desc_label, False, False, 0)
        
        desc_text = Gtk.Label(label=info['description'])
        desc_text.set_line_wrap(True)
        desc_text.set_xalign(0)
        desc_text.set_yalign(0)
        desc_text.set_selectable(True)
        self.info_box.pack_start(desc_text, False, False, 0)
        
        # Dependencies
        if info['dependencies']:
            deps_label = Gtk.Label()
            deps_label.set_markup("<b>Dependencies (first 10):</b>")
            deps_label.set_xalign(0)
            deps_label.set_yalign(0)
            self.info_box.pack_start(deps_label, False, False, 0)
            
            deps_text = Gtk.Label(label=", ".join(info['dependencies']))
            deps_text.set_line_wrap(True)
            deps_text.set_xalign(0)
            deps_text.set_yalign(0)
            deps_text.set_selectable(True)
            self.info_box.pack_start(deps_text, False, False, 0)
        
        # Homepage
        if info['homepage']:
            homepage_label = Gtk.Label()
            homepage_label.set_markup(f"<b>Homepage:</b> <a href='{info['homepage']}'>{info['homepage']}</a>")
            homepage_label.set_xalign(0)
            homepage_label.set_yalign(0)
            self.info_box.pack_start(homepage_label, False, False, 0)
        
        self.show_all()

class LASWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="LAS - Linux App Store")
        self.set_default_size(900, 700)
        self.set_border_width(10)
        self.connect("destroy", Gtk.main_quit)

        # Set a window icon
        try:
            icon_theme = Gtk.IconTheme.get_default()
            pixbuf = icon_theme.load_icon("system-software-install", 48, 0)
            self.set_icon(pixbuf)
        except Exception as e:
            logging.error(f"Error setting window icon: {e}")

        # Apply CSS for beautiful UI
        css = """
        .app-card {
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 12px;
            margin: 6px;
            background-color: #ffffff;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .app-card:hover {
            background-color: #f8f8f8;
            box-shadow: 0 6px 10px rgba(0,0,0,0.15);
            border: 1px solid #4CAF50;
        }
        .featured-card {
            border: 2px solid #FF9800;
            background: linear-gradient(135deg, #fff3e0 0%, #ffffff 100%);
        }
        .install-button {
            background-color: #4CAF50;
            color: white;
            border-radius: 5px;
            padding: 6px;
            font-weight: bold;
        }
        .install-button:hover {
            background-color: #45a049;
        }
        .uninstall-button {
            background-color: #f44336;
            color: white;
            border-radius: 5px;
            padding: 6px;
            font-weight: bold;
        }
        .uninstall-button:hover {
            background-color: #da190b;
        }
        .info-button {
            background-color: #2196F3;
            color: white;
            border-radius: 5px;
            padding: 4px;
        }
        .info-button:hover {
            background-color: #1976D2;
        }
        .desc-label {
            font-size: 10px;
            color: #666;
            margin-top: 4px;
        }
        .search-entry {
            padding: 8px;
            border-radius: 5px;
            border: 1px solid #ccc;
            font-size: 14px;
        }
        .category-button {
            padding: 8px 16px;
            margin: 4px;
            border-radius: 20px;
            background-color: #e0e0e0;
            border: 1px solid #ccc;
        }
        .category-button:hover {
            background-color: #d0d0d0;
        }
        .category-button.active {
            background-color: #4CAF50;
            color: white;
        }
        .section-title {
            font-size: 18px;
            font-weight: bold;
            margin: 15px 0 10px 0;
            color: #333;
        }
        """
        
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode('utf-8'))
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            else:
                logging.error("No default screen available for CSS provider")
        except Exception as e:
            logging.error(f"Error applying CSS: {e}")
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Failed to apply CSS styles"
            )
            dialog.format_secondary_text(str(e))
            dialog.run()
            dialog.destroy()

        # Main layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # Header with search and controls
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(header_box, False, False, 0)

        # Search bar
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Search for apps...")
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.connect("activate", self.on_search)
        self.search_entry.connect("changed", self.on_search_changed)
        header_box.pack_start(self.search_entry, True, True, 0)

        # View mode buttons
        view_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        header_box.pack_start(view_box, False, False, 0)

        self.home_button = Gtk.Button(label="Home")
        self.home_button.connect("clicked", self.show_home)
        view_box.pack_start(self.home_button, False, False, 0)

        self.installed_button = Gtk.Button(label="Installed")
        self.installed_button.connect("clicked", self.show_installed)
        view_box.pack_start(self.installed_button, False, False, 0)

        self.updates_button = Gtk.Button(label="Updates")
        self.updates_button.connect("clicked", self.show_updates)
        view_box.pack_start(self.updates_button, False, False, 0)

        # Categories bar
        self.categories_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        categories_scroll = Gtk.ScrolledWindow()
        categories_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        categories_scroll.add(self.categories_box)
        categories_scroll.set_size_request(-1, 50)
        vbox.pack_start(categories_scroll, False, False, 0)

        # Create category buttons
        self.category_buttons = {}
        all_button = Gtk.Button(label="All")
        all_button.get_style_context().add_class("category-button")
        all_button.get_style_context().add_class("active")
        all_button.connect("clicked", lambda btn: self.show_category("All"))
        self.categories_box.pack_start(all_button, False, False, 0)
        self.category_buttons["All"] = all_button

        for category in APP_CATEGORIES.keys():
            button = Gtk.Button(label=category)
            button.get_style_context().add_class("category-button")
            button.connect("clicked", lambda btn, cat=category: self.show_category(cat))
            self.categories_box.pack_start(button, False, False, 0)
            self.category_buttons[category] = button

        # Loading spinner
        self.spinner = Gtk.Spinner()
        vbox.pack_start(self.spinner, False, False, 0)

        # Main content area
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(self.scroll, True, True, 0)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.scroll.add(self.main_box)

        # Current view state
        self.current_view = "home"
        self.current_category = "All"

        # Show default content
        self.show_home()

    def update_category_buttons(self, active_category):
        """Update category button styles."""
        for name, button in self.category_buttons.items():
            if name == active_category:
                button.get_style_context().add_class("active")
            else:
                button.get_style_context().remove_class("active")

    def show_home(self, widget=None):
        """Show the home view with featured apps and categories."""
        logging.debug("Showing home view")
        self.current_view = "home"
        self.clear_main_content()
        
        # Featured Apps Section
        featured_label = Gtk.Label()
        featured_label.set_markup("<b><big>Featured Apps</big></b>")
        featured_label.get_style_context().add_class("section-title")
        featured_label.set_xalign(0)
        featured_label.set_yalign(0.5)
        self.main_box.pack_start(featured_label, False, False, 0)
        
        featured_flowbox = Gtk.FlowBox()
        featured_flowbox.set_max_children_per_line(6)
        featured_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.main_box.pack_start(featured_flowbox, False, False, 0)
        
        # Load featured apps
        def load_featured():
            logging.debug("Loading featured apps")
            try:
                with apt_lock:
                    cache = apt.Cache()
                    cache.update()
                    cache.open()
                    apps = []
                    for app_name in FEATURED_APPS:
                        if app_name in cache:
                            pkg = cache[app_name]
                            description = "No description available"
                            if pkg.versions:
                                full_desc = pkg.versions[0].description or description
                                if len(full_desc) > 120:
                                    description = full_desc[:120].rsplit(' ', 1)[0] + "..."
                                else:
                                    description = full_desc.replace('\n', ' ')
                            apps.append((app_name, description, pkg.is_installed, True))
                        else:
                            logging.warning(f"Package {app_name} not found in cache")
                    logging.debug(f"Found {len(apps)} featured apps")
                GLib.idle_add(self.populate_flowbox, featured_flowbox, apps, "No featured apps available. Try running 'sudo apt update'.")
            except Exception as e:
                logging.error(f"Error loading featured apps: {e}")
                GLib.idle_add(self.populate_flowbox, featured_flowbox, [], "Error loading featured apps.")
        
        Thread(target=load_featured, daemon=True).start()
        
        # Categories Preview
        for category, apps in list(APP_CATEGORIES.items())[:3]:  # Show first 3 categories
            category_label = Gtk.Label()
            category_label.set_markup(f"<b><big>{category}</big></b>")
            category_label.get_style_context().add_class("section-title")
            category_label.set_xalign(0)
            category_label.set_yalign(0.5)
            category_label.set_margin_top(20)
            self.main_box.pack_start(category_label, False, False, 0)
            
            category_flowbox = Gtk.FlowBox()
            category_flowbox.set_max_children_per_line(6)
            category_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
            self.main_box.pack_start(category_flowbox, False, False, 0)
            
            # Load category apps
            Thread(target=lambda: self.load_category_apps(apps, category_flowbox, category), daemon=True).start()
        
        self.main_box.show_all()

    def load_category_apps(self, cat_apps, flowbox, category):
        """Load apps for a category and populate the flowbox."""
        logging.debug(f"Loading apps for category: {category}")
        try:
            with apt_lock:
                cache = apt.Cache()
                cache.update()
                cache.open()
                apps = []
                for app_name in cat_apps[:6]:
                    if app_name in cache:
                        pkg = cache[app_name]
                        description = "No description available"
                        if pkg.versions:
                            full_desc = pkg.versions[0].description or description
                            if len(full_desc) > 120:
                                description = full_desc[:120].rsplit(' ', 1)[0] + "..."
                            else:
                                description = full_desc.replace('\n', ' ')
                        apps.append((app_name, description, pkg.is_installed, False))
                    else:
                        logging.warning(f"Package {app_name} not found in cache")
                logging.debug(f"Found {len(apps)} apps for category {category}")
            GLib.idle_add(self.populate_flowbox, flowbox, apps, f"No apps available in {category}. Try running 'sudo apt update'.")
        except Exception as e:
            logging.error(f"Error loading category {category}: {e}")
            GLib.idle_add(self.populate_flowbox, flowbox, [], f"Error loading {category} apps.")

    def show_category(self, category):
        """Show apps from a specific category."""
        logging.debug(f"Showing category: {category}")
        self.current_view = "category"
        self.current_category = category
        self.update_category_buttons(category)
        self.clear_main_content()
        
        if category == "All":
            self.show_home()
            return
        
        category_label = Gtk.Label()
        category_label.set_markup(f"<b><big>{category} Apps</big></b>")
        category_label.get_style_context().add_class("section-title")
        category_label.set_xalign(0)
        category_label.set_yalign(0.5)
        self.main_box.pack_start(category_label, False, False, 0)
        
        flowbox = Gtk.FlowBox()
        flowbox.set_max_children_per_line(6)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.main_box.pack_start(flowbox, True, True, 0)
        
        # Show loading
        self.spinner.start()
        self.spinner.show()
        
        def load_category_apps():
            try:
                with apt_lock:
                    cache = apt.Cache()
                    cache.update()
                    cache.open()
                    apps = []
                    if category in APP_CATEGORIES:
                        for app_name in APP_CATEGORIES[category]:
                            if app_name in cache:
                                pkg = cache[app_name]
                                description = "No description available"
                                if pkg.versions:
                                    full_desc = pkg.versions[0].description or description
                                    if len(full_desc) > 120:
                                        description = full_desc[:120].rsplit(' ', 1)[0] + "..."
                                    else:
                                        description = full_desc.replace('\n', ' ')
                                apps.append((app_name, description, pkg.is_installed, False))
                            else:
                                logging.warning(f"Package {app_name} not found in cache")
                    logging.debug(f"Found {len(apps)} apps for category {category}")
                GLib.idle_add(self.finish_loading_category, flowbox, apps)
            except Exception as e:
                logging.error(f"Error loading category {category}: {e}")
                GLib.idle_add(self.finish_loading_category, flowbox, [])
        
        Thread(target=load_category_apps, daemon=True).start()

    def finish_loading_category(self, flowbox, apps):
        """Finish loading category apps."""
        self.spinner.stop()
        self.spinner.hide()
        self.populate_flowbox(flowbox, apps, "No apps available in this category.")
        self.main_box.show_all()

    def show_installed(self, widget=None):
        """Show installed packages."""
        logging.debug("Showing installed packages")
        self.current_view = "installed"
        self.clear_main_content()
        
        installed_label = Gtk.Label()
        installed_label.set_markup("<b><big>Installed Applications</big></b>")
        installed_label.get_style_context().add_class("section-title")
        installed_label.set_xalign(0)
        installed_label.set_yalign(0.5)
        self.main_box.pack_start(installed_label, False, False, 0)
        
        flowbox = Gtk.FlowBox()
        flowbox.set_max_children_per_line(6)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.main_box.pack_start(flowbox, True, True, 0)
        
        # Show loading
        self.spinner.start()
        self.spinner.show()
        
        def load_installed():
            try:
                with apt_lock:
                    cache = apt.Cache()
                    cache.update()
                    cache.open()
                    apps = []
                    count = 0
                    for pkg in cache:
                        if pkg.is_installed and count < 100:  # Limit to prevent UI freeze
                            # Filter out system packages
                            if not any(pkg.name.startswith(prefix) for prefix in ['lib', 'python3-', 'gir1.2-']):
                                description = "No description available"
                                if pkg.versions:
                                    full_desc = pkg.versions[0].description or description
                                    if len(full_desc) > 120:
                                        description = full_desc[:120].rsplit(' ', 1)[0] + "..."
                                    else:
                                        description = full_desc.replace('\n', ' ')
                                apps.append((pkg.name, description, True, False))
                                count += 1
                    logging.debug(f"Found {len(apps)} installed packages")
                GLib.idle_add(self.finish_loading_installed, flowbox, apps)
            except Exception as e:
                logging.error(f"Error loading installed packages: {e}")
                GLib.idle_add(self.finish_loading_installed, flowbox, [])
        
        Thread(target=load_installed, daemon=True).start()

    def finish_loading_installed(self, flowbox, apps):
        """Finish loading installed apps."""
        self.spinner.stop()
        self.spinner.hide()
        self.populate_flowbox(flowbox, apps, "No installed applications found.")
        self.main_box.show_all()

    def show_updates(self, widget=None):
        """Show available updates."""
        logging.debug("Showing available updates")
        self.current_view = "updates"
        self.clear_main_content()
        
        updates_label = Gtk.Label()
        updates_label.set_markup("<b><big>Available Updates</big></b>")
        updates_label.get_style_context().add_class("section-title")
        updates_label.set_xalign(0)
        updates_label.set_yalign(0.5)
        self.main_box.pack_start(updates_label, False, False, 0)
        
        # Update all button
        update_all_button = Gtk.Button(label="Update All")
        update_all_button.get_style_context().add_class("install-button")
        update_all_button.connect("clicked", self.update_all_packages)
        self.main_box.pack_start(update_all_button, False, False, 0)
        
        flowbox = Gtk.FlowBox()
        flowbox.set_max_children_per_line(6)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.main_box.pack_start(flowbox, True, True, 0)
        
        # Show loading
        self.spinner.start()
        self.spinner.show()
        
        def load_updates():
            try:
                with apt_lock:
                    cache = apt.Cache()
                    cache.update()
                    cache.open()
                    
                    apps = []
                    for pkg in cache:
                        if pkg.is_installed and pkg.is_upgradable:
                            description = "No description available"
                            if pkg.versions:
                                full_desc = pkg.versions[0].description or description
                                if len(full_desc) > 120:
                                    description = full_desc[:120].rsplit(' ', 1)[0] + "..."
                                else:
                                    description = full_desc.replace('\n', ' ')
                            apps.append((pkg.name, description, True, False))
                    logging.debug(f"Found {len(apps)} upgradable packages")
                GLib.idle_add(self.finish_loading_updates, flowbox, apps)
            except Exception as e:
                logging.error(f"Error loading updates: {e}")
                GLib.idle_add(self.finish_loading_updates, flowbox, [])
        
        Thread(target=load_updates, daemon=True).start()

    def finish_loading_updates(self, flowbox, apps):
        """Finish loading updates."""
        self.spinner.stop()
        self.spinner.hide()
        self.populate_flowbox(flowbox, apps, "No updates available or unable to check for updates.")
        self.main_box.show_all()

    def populate_flowbox(self, flowbox, apps, empty_message="No apps available."):
        """Populate a flowbox with app cards."""
        logging.debug(f"Populating flowbox with {len(apps)} apps")
        if not apps:
            logging.warning(f"No apps to display: {empty_message}")
            no_apps_label = Gtk.Label(label=empty_message)
            no_apps_label.set_xalign(0)
            no_apps_label.set_yalign(0.5)
            flowbox.add(no_apps_label)
        else:
            for name, desc, is_installed, is_featured in apps:
                card = self.create_app_card(name, desc, is_installed, is_featured)
                flowbox.add(card)

    def clear_main_content(self):
        """Clear the main content area."""
        logging.debug("Clearing main content")
        for child in self.main_box.get_children():
            self.main_box.remove(child)

    def search_packages(self, query):
        """Search packages using python3-apt, filtering duplicates by architecture."""
        logging.debug(f"Searching packages with query: {query}")
        if not query or not re.match(r'^[\w\s.-]*$', query):
            logging.warning("Invalid or empty search query")
            return []
        try:
            with apt_lock:
                cache = apt.Cache()
                cache.update()
                cache.open()
                if len(cache) == 0:
                    logging.error("Package cache is empty")
                    return []

                # Detect system architecture
                system_arch = platform.machine()
                native_arch = "amd64" if system_arch == "x86_64" else system_arch

                # Store seen base package names to avoid duplicates
                seen = set()
                results = []
                for pkg in cache:
                    pkg_name = pkg.name
                    # Skip if we've already seen this base package
                    base_name = re.sub(r'(:amd64|:i386)$', '', pkg_name)
                    if base_name in seen:
                        continue

                    # Match query
                    if query.lower() in pkg_name.lower() or pkg_name.lower().startswith(query.lower()):
                        # Prefer native architecture
                        if pkg_name.endswith(f":{native_arch}") or not any(pkg_name.endswith(f":{arch}") for arch in ["amd64", "i386"]):
                            seen.add(base_name)
                            description = "No description available"
                            if pkg.versions:
                                full_desc = pkg.versions[0].description or description
                                if len(full_desc) > 120:
                                    description = full_desc[:120].rsplit(' ', 1)[0] + "..."
                                else:
                                    description = full_desc.replace('\n', ' ')
                            results.append((pkg_name, description, pkg.is_installed))
                logging.debug(f"Found {len(results)} packages matching query: {query}")
                return results
        except Exception as e:
            logging.error(f"Error searching packages: {e}")
            return []

    def create_app_card(self, name, desc, is_installed, is_featured=False):
        """Create a card for an app with icon, name, description, and buttons."""
        logging.debug(f"Creating app card for {name}")
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("app-card")
        if is_featured:
            card.get_style_context().add_class("featured-card")
        
        screen = Gdk.Screen.get_default()
        dpi_scale = screen.get_resolution() / 96.0
        card.set_size_request(int(140 * dpi_scale), int(180 * dpi_scale))

        # Placeholder image while icon loads
        image = Gtk.Image.new_from_icon_name("image-loading", Gtk.IconSize.DIALOG)
        card.pack_start(image, False, False, 0)

        # Load icon asynchronously
        def update_icon(pixbuf):
            if pixbuf:
                image.set_from_pixbuf(pixbuf)
            else:
                image.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
            image.show()
        load_icon_async(name, update_icon)

        # App name
        name_label = Gtk.Label(label=name)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_max_width_chars(15)
        name_label.set_justify(Gtk.Justification.CENTER)
        name_label.set_margin_top(5)
        card.pack_start(name_label, False, False, 0)

        # Description
        desc_label = Gtk.Label(label=desc)
        desc_label.set_ellipsize(Pango.EllipsizeMode.END)
        desc_label.set_line_wrap(True)
        desc_label.set_max_width_chars(20)
        desc_label.set_justify(Gtk.Justification.CENTER)
        desc_label.get_style_context().add_class("desc-label")
        card.pack_start(desc_label, False, False, 0)

        # Button container
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        card.pack_start(button_box, False, False, 0)

        # Install/Uninstall button
        button_label = "Uninstall" if is_installed else "Install"
        main_button = Gtk.Button(label=button_label)
        button_class = "uninstall-button" if is_installed else "install-button"
        main_button.get_style_context().add_class(button_class)
        if is_installed:
            main_button.connect("clicked", lambda btn: self.uninstall_package(name))
        else:
            main_button.connect("clicked", lambda btn: self.install_package(name))
        button_box.pack_start(main_button, True, True, 0)

        # Info button
        info_button = Gtk.Button(label="ℹ")
        info_button.get_style_context().add_class("info-button")
        info_button.connect("clicked", lambda btn: self.show_package_info(name))
        info_button.set_tooltip_text("Package Information")
        button_box.pack_start(info_button, False, False, 0)

        return card

    def show_package_info(self, package_name):
        """Show detailed package information dialog."""
        logging.debug(f"Showing package info for {package_name}")
        dialog = PackageInfoDialog(self, package_name)
        dialog.run()
        dialog.destroy()

    def install_package(self, package_name):
        """Install a package using apt with pkexec."""
        logging.debug(f"Installing package {package_name}")
        def do_install():
            try:
                if not shutil.which("pkexec"):
                    GLib.idle_add(self.show_install_error, package_name, "pkexec not found. Please install policykit-1.")
                    return
                process = subprocess.run(
                    ["pkexec", "apt", "install", "-y", package_name], 
                    check=True,
                    capture_output=True,
                    text=True
                )
                GLib.idle_add(self.show_install_success, package_name)
            except subprocess.CalledProcessError as e:
                logging.error(f"Installation failed for {package_name}: {e.stderr}")
                GLib.idle_add(self.show_install_error, package_name, f"Installation failed: {e.stderr}")
        
        Thread(target=do_install, daemon=True).start()

    def show_install_success(self, package_name):
        """Show installation success dialog."""
        logging.debug(f"Installation successful for {package_name}")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"{package_name} installed successfully!"
        )
        dialog.run()
        dialog.destroy()
        self.refresh_current_view()

    def show_install_error(self, package_name, error):
        """Show installation error dialog."""
        logging.error(f"Installation error for {package_name}: {error}")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=f"Failed to install {package_name}"
        )
        dialog.format_secondary_text(str(error))
        dialog.run()
        dialog.destroy()

    def uninstall_package(self, package_name):
        """Uninstall a package using apt with pkexec."""
        logging.debug(f"Uninstalling package {package_name}")
        def do_uninstall():
            try:
                if not shutil.which("pkexec"):
                    GLib.idle_add(self.show_uninstall_error, package_name, "pkexec not found. Please install policykit-1.")
                    return
                process = subprocess.run(
                    ["pkexec", "apt", "remove", "-y", package_name], 
                    check=True,
                    capture_output=True,
                    text=True
                )
                GLib.idle_add(self.show_uninstall_success, package_name)
            except subprocess.CalledProcessError as e:
                logging.error(f"Uninstallation failed for {package_name}: {e.stderr}")
                GLib.idle_add(self.show_uninstall_error, package_name, f"Uninstallation failed: {e.stderr}")
        
        Threads(target=do_uninstall, daemon=True).start()

    def show_uninstall_success(self, package_name):
        """Show uninstallation success dialog."""
        logging.debug(f"Uninstallation successful for {package_name}")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"{package_name} uninstalled successfully!"
        )
        dialog.run()
        dialog.destroy()
        self.refresh_current_view()

    def show_uninstall_error(self, package_name, error):
        """Show uninstallation error dialog."""
        logging.error(f"Uninstallation error for {package_name}: {error}")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=f"Failed to uninstall {package_name}"
        )
        dialog.format_secondary_text(str(error))
        dialog.run()
        dialog.destroy()

    def update_all_packages(self, widget):
        """Update all packages."""
        logging.debug("Updating all packages")
        def do_update_all():
            try:
                if not shutil.which("pkexec"):
                    GLib.idle_add(self.show_update_error, "pkexec not found. Please install policykit-1.")
                    return
                # Update package lists first
                process1 = subprocess.run(
                    ["pkexec", "apt", "update"], 
                    check=True,
                    capture_output=True,
                    text=True
                )
                # Upgrade packages
                process2 = subprocess.run(
                    ["pkexec", "apt", "upgrade", "-y"], 
                    check=True,
                    capture_output=True,
                    text=True
                )
                GLib.idle_add(self.show_update_success)
            except subprocess.CalledProcessError as e:
                logging.error(f"Update failed: {e.stderr}")
                GLib.idle_add(self.show_update_error, f"Update failed: {e.stderr}")
        
        Thread(target=do_update_all, daemon=True).start()

    def show_update_success(self):
        """Show update success dialog."""
        logging.debug("System update successful")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="System updated successfully!"
        )
        dialog.run()
        dialog.destroy()
        self.refresh_current_view()

    def show_update_error(self, error):
        """Show update error dialog."""
        logging.error(f"Update error: {error}")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Failed to update system"
        )
        dialog.format_secondary_text(str(error))
        dialog.run()
        dialog.destroy()

    def refresh_current_view(self):
        """Refresh the current view after package operations."""
        logging.debug(f"Refreshing view: {self.current_view}")
        if self.current_view == "home":
            self.show_home()
        elif self.current_view == "installed":
            self.show_installed()
        elif self.current_view == "updates":
            self.show_updates()
        elif self.current_view == "category":
            self.show_category(self.current_category)
        elif self.current_view == "search":
            self.on_search(self.search_entry)

    def on_search_changed(self, entry):
        """Handle search text changes with debouncing."""
        query = entry.get_text().strip()
        logging.debug(f"Search query changed: {query}")
        if hasattr(self, '_search_timeout'):
            GLib.source_remove(self._search_timeout)
        
        if query:
            self._search_timeout = GLib.timeout_add(500, lambda: self.on_search(entry))

    def on_search(self, entry):
        """Handle search input and update UI."""
        query = entry.get_text().strip().lower()
        logging.debug(f"Performing search for: {query}")
        if not query:
            self.show_home()
            return False  # For timeout callback

        self.current_view = "search"
        self.clear_main_content()

        search_label = Gtk.Label()
        search_label.set_markup(f"<b><big>Search Results for '{query}'</big></b>")
        search_label.get_style_context().add_class("section-title")
        search_label.set_xalign(0)
        search_label.set_yalign(0.5)
        self.main_box.pack_start(search_label, False, False, 0)

        flowbox = Gtk.FlowBox()
        flowbox.set_max_children_per_line(6)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.main_box.pack_start(flowbox, True, True, 0)

        # Show loading spinner
        self.spinner.start()
        self.spinner.show()

        # Search and update UI
        def update_results():
            packages = self.search_packages(query)
            GLib.idle_add(self.finish_search, flowbox, packages, query)

        Thread(target=update_results, daemon=True).start()
        return False  # For timeout callback

    def finish_search(self, flowbox, packages, query):
        """Finish search operation and update UI."""
        logging.debug(f"Finishing search for {query}, found {len(packages)} results")
        self.spinner.stop()
        self.spinner.hide()
        
        if not packages:
            no_results = Gtk.Label(label=f"No results found for '{query}'. Try running 'sudo apt update' or search for different terms.")
            self.main_box.pack_start(no_results, False, False, 0)
        else:
            for name, desc, is_installed in packages:
                card = self.create_app_card(name, desc, is_installed)
                flowbox.add(card)
        
        self.main_box.show_all()

def main():
    try:
        win = LASWindow()
        win.show_all()
        Gtk.main()
    except Exception as e:
        logging.error(f"Error in main(): {e}")
        print(f"Error in main(): {e}")
        exit(1)

if __name__ == "__main__":
    # Check if display is available
    if not os.environ.get('DISPLAY'):
        print("Error: No display environment found. Are you running this in a graphical environment?")
        exit(1)
    main()