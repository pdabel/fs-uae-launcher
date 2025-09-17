from fsbc.settings import Settings
from fsgs.amiga.amiga import Amiga

class SyncSettings:
    def __init__(self):
        self.load()

    def load(self):
        sync = Settings.instance()
        self.MAX_FLOPPY_DRIVES = int(sync.get("max_floppy_drives", Amiga.MAX_FLOPPY_DRIVES))
        self.MAX_FLOPPY_IMAGES = int(sync.get("max_floppy_images", Amiga.MAX_FLOPPY_IMAGES))
        self.MAX_CDROM_DRIVES = int(sync.get("max_cdrom_drives", Amiga.MAX_CDROM_DRIVES))
        self.MAX_CDROM_IMAGES = int(sync.get("max_cdrom_images", Amiga.MAX_CDROM_IMAGES))
        self.MAX_HARD_DRIVES = int(sync.get("max_hard_drives", Amiga.MAX_HARD_DRIVES))

    def update(self):
        self.load()

# Create a global instance
sync_settings = SyncSettings()
