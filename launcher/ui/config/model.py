import weakref


class StrWithExplicit(str):

    @property
    def int(self):
        return int(self or "0")


class ImplicitConfig:
    def __init__(self, config, settings):
        self._values = {}
        self._config = config
        self._settings = settings

    def items(self):
        return self._values.items()

    def get(self, key, default=""):
        value = self._values.get(key, default)
        explicit = self._config[key]
        if not explicit:
            explicit = self._settings[key]
        if value:
            result = StrWithExplicit(value)
        else:
            result = StrWithExplicit(explicit)
        result.explicit = explicit
        return result

    def __getitem__(self, item):
        result = self.get(item)
        return result

    def __setitem__(self, key, value):
        if not value:
            value = ""
        else:
            value = str(value)
        self._values[key] = value

    def __getattr__(self, item):
        result = self.get(item)
        return result

    def __setattr__(self, key, value):
        if key.startswith("_"):
            self.__dict__[key] = value
        else:
            self[key] = value


class NoParent:
    def __call__(self):
        return None


class Item:
    def __init__(self, text, active=True):
        self.text = text
        self.extra = ""
        self._active = active
        self.represents = []
        self.parent = NoParent()
        self.children = []

    @property
    def active(self):
        return self._active

    def add(self, child):
        child.parent = weakref.ref(self)
        self.children.append(child)

    def __str__(self):
        return f" + {self.text}"


class ContainerItem(Item):
    """This item is only active if it has children."""

    @property
    def active(self):
        return len(self.children) > 0


class InactiveItem(Item):
    def __init__(self, text):
        super().__init__(text, active=False)

    def __str__(self):
        return f" ( {self.text} )"


class Model:
    def __init__(self, show_all=False):
        self.items = []
        self.show_all = show_all

    def add(self, item):
        if True:
            if item.parent:
                for i in range(len(self.items) - 1, -1, -1):
                    if (
                        self.items[0].parent == item.parent
                        or self.items[0] == item.parent
                    ):
                        self.items.insert(i + 1, item)
                        break
                else:
                    self.items.append(item)
            else:
                self.items.append(item)
        return item

    def remove(self, item):
        self.items.remove(item)
        return item

    def last_item(self):
        return self.items[-1]


def normalize(value):
    n = ""
    for c in value.lower():
        if c in "abcdefghijklmnopqrstuvwxyz0123456789+":
            n += c
    return n


def create_joystick_port_item(c, num: int) -> Item:
    # FIXME: retrieve uae_ option
    mode = c.get(f"joystick_port_{num}_mode")
    if mode == "nothing":
        item = InactiveItem(f"Joystick Port {num}")
    else:
        item = Item(f"Joystick Port {num}")
    return item


def create_slirp_item(c):
    implementation = c.uae_slirp_implementation
    if implementation == "auto":
        name = "Auto"
    elif implementation == "none":
        name = "None"
    elif implementation == "builtin":
        name = "Built-in"
    elif implementation == "qemu":
        name = "QEMU"
    else:
        name = implementation
    slirp_item = Item(f"Slirp ({name})")

    if c.uae_slirp_ports:
        slirp_ports_item = Item("Ports: " + c.uae_slirp_ports)
        slirp_item.add(slirp_ports_item)
    if c.uae_slirp_redir:
        slirp_redirect_item = Item("Redirect: " + c.uae_slirp_redir)
        slirp_item.add(slirp_redirect_item)

    return slirp_item


def create_model(c, show_all=False):
    model = Model(show_all=show_all)

    text = c.int_chipset_name
    if c.uae_chipset_compatible != "-":
        text += f" ({c.uae_chipset_compatible})"
    if c.ntsc_mode:
        text += " NTSC"
    else:
        text += " PAL"
    chipset_item = Item(text)
    chipset_item.represents = [
        "uae_chipset",
        "uae_chipset_compatible",
        "ntsc_mode",
    ]
    model.add(chipset_item)

    if c.uae_chipset == "aga":
        text = "Alice (AGA)"
        if c.ntsc_mode:
            text += " NTSC"
        else:
            text += " PAL"
    else:
        # http://en.wikipedia.org/wiki/MOS_Technology_Agnus
        if c.uae_chipset in ["ecs_agnus", "ecs"]:
            text = "Agnus (ECS)"
        else:
            text = "Agnus"
        if c.ntsc_mode:
            text += " NTSC"
        else:
            text += " PAL"

    kickstart_item = Item(
        f"Kickstart {c.int_kickstart_version} Rev {c.int_kickstart_revision}"
    )
    model.add(kickstart_item)

    if c.int_kickstart_ext_sha1 == "5bef3d628ce59cc02a66e6e4ae0da48f60e78f7f":
        kickstart_ext_item = Item("CD32 Extended ROM")
    elif (
        c.int_kickstart_ext_sha1 == "7ba40ffa17e500ed9fed041f3424bd81d9c907be"
    ):
        kickstart_ext_item = Item("CDTV Extended ROM")
    else:
        kickstart_ext_item = InactiveItem("Extended ROM")
    model.add(kickstart_ext_item)

    jit_text = " [JIT]" if c.jit_compiler == "1" else ""
    cpu_item = Item("MC" + c.int_cpu_name + jit_text)
    cpu_item.represents = ["cpu", "uae_cpu_model"]  # FIXME: uae_cpu_type

    if c.int_accelerator_name:
        item = Item(f"{c.int_accelerator_name}")
        accelerator_item = model.add(item)
    else:
        accelerator_item = InactiveItem("No Accelerator")
        model.add(accelerator_item)
    accelerator_item.represents = ["accelerator", "uae_cpuboard_type"]

    if accelerator_item.active:
        accelerator_item.add(cpu_item)
    else:
        model.add(cpu_item)

    if accelerator_item.active:
        if c.int_ppc_model:
            item = Item(f"PowerPC {c.int_ppc_model}")
            accelerator_item.add(item)

        if c.int_cpuboardmem1_size:
            size = f"{int(c.int_cpuboardmem1_size) // (1024 * 1024)} MB"
            item = Item(f"{size} RAM")
            item.represents = ["uae_cpuboard1mem_size"]
            accelerator_item.add(item)

        item = Item("ROM/Flash [FIXME]")
        item.represents = ["accelerator_rom"]
        accelerator_item.add(item)

        if c.uae_cpuboard_type == "CyberStormPPC":
            # FIXME: other too?
            accelerator_scsi_item = Item("CyberStorm SCSI")
            accelerator_item.add(accelerator_scsi_item)

    if int(c.uae_mmu_model):
        mmu_item = Item(f"{c.uae_mmu_model} MMU")
    else:
        mmu_item = InactiveItem("No MMU")
    cpu_item.represents = ["mmu_model"]
    cpu_item.add(mmu_item)

    if int(c.uae_fpu_model):
        fpu_item = Item(f"{c.uae_fpu_model} FPU")
    else:
        fpu_item = InactiveItem("No FPU")
    fpu_item.represents = ["fpu_model"]
    if c.uae_fpu_model == c.uae_cpu_model:
        cpu_item.add(fpu_item)
    else:
        model.add(fpu_item)

    if int(c.int_chipmem_size) % (1024 * 1024) == 0:
        size = f"{int(c.int_chipmem_size) // (1024 * 1024)} MB"
    else:
        size = f"{int(c.int_chipmem_size) // 1024} KB"
    chipmem_item = Item(f"{size} Chip RAM")
    chipmem_item.represents = ["chip_memory", "uae_chipmem_size"]
    model.add(chipmem_item)

    if int(c.int_mbresmem_low_size):
        size = f"{int(c.int_mbresmem_low_size) // (1024 * 1024)} MB"
        item = Item(f"{size} Fast RAM")
    else:
        item = InactiveItem("No Fast RAM")
    item.extra = "Motherboard"
    item.represents = ["uae_a3000mem_size"]
    model.add(item)

    trapdoor_item = ContainerItem("Trapdoor Slot")
    zorro_ii_item = ContainerItem("Zorro II Bus")
    zorro_iii_item = ContainerItem("Zorro III Bus")

    flatten = True

    if int(c.int_bogomem_size):
        if int(c.int_bogomem_size) % (1024 * 1024) == 0:
            size = f"{int(c.int_bogomem_size) // (1024 * 1024)} MB"
        else:
            size = f"{int(c.int_bogomem_size) // 1024} KB"
        bogomem_item = Item(f"{size} Slow RAM")
    else:
        bogomem_item = InactiveItem("No Slow RAM")
    bogomem_item.represents = ["slow_memory", "uae_bogomem_size"]
    if flatten:
        bogomem_item.extra = "Trapdoor"
        model.add(bogomem_item)
    else:
        trapdoor_item.add(bogomem_item)

    if int(c.int_fastmem_size):
        if int(c.int_fastmem_size) % (1024 * 1024) == 0:
            size = f"{int(c.int_fastmem_size) // (1024 * 1024)} MB"
        else:
            size = f"{int(c.int_fastmem_size) // 1024} KB"
        fastmem_item = Item(f"{size} Fast RAM")
    else:
        fastmem_item = InactiveItem("No Zorro II Fast RAM")
    fastmem_item.represents = ["fast_memory", "uae_fastmem_size"]
    if flatten:
        fastmem_item.extra = "Zorro II"
        model.add(fastmem_item)
    else:
        zorro_ii_item.add(fastmem_item)

    if int(c.int_z3fastmem_size):
        size = f"{int(c.int_z3fastmem_size) // (1024 * 1024)} MB"
        z3fastmem_item = Item(f"{size} Fast RAM")
    else:
        z3fastmem_item = InactiveItem("No Zorro III Fast RAM")
    z3fastmem_item.represents = ["zorro_iii_memory", "uae_z3mem_size"]
    if flatten:
        z3fastmem_item.extra = "Zorro III"
        model.add(z3fastmem_item)
    else:
        zorro_iii_item.add(z3fastmem_item)

    if c.uae_rtc != "none":
        rtc_item = Item(f"{c.uae_rtc} RTC")
    else:
        rtc_item = InactiveItem("No Real Time Clock")
    rtc_item.represents = ["uae_rtc"]
    if bogomem_item.active and c.uae_rtc == "MSM6242B":
        if flatten:
            model.add(rtc_item)
        else:
            trapdoor_item.add(rtc_item)
    else:
        model.add(rtc_item)

    if c.uae_cd32fmv == "true":

        fmv_item = Item("CD32 FMV Module")
        model.add(fmv_item)

        fmv_rom_item = Item("CD32 FMV ROM")
        fmv_item.add(fmv_rom_item)

    model.add(trapdoor_item)
    model.add(zorro_ii_item)
    model.add(zorro_iii_item)

    resident_item = model

    if c.int_uae_boot_rom == "true":
        uae_boot_rom_item = Item("UAE Boot ROM")
        resident_item.add(uae_boot_rom_item)

        uae_resource_item = Item("UAE uae.resource")
        uae_boot_rom_item.add(uae_resource_item)

        if c.uae_bsdsocket_emu == "true":
            bsdsocket_item = Item("UAE bsdsocket.library")
        else:
            bsdsocket_item = InactiveItem("No bsdsocket.library")
        bsdsocket_item.represents = ["bsdsocket_library", "uae_bsdsocket_emu"]
        resident_item.add(bsdsocket_item)

        if c.uae_native_code == "true":
            uaenative_library_item = Item("UAE uaenative.library")
        else:
            uaenative_library_item = InactiveItem("No uaenative.library")
        uaenative_library_item.represents = [
            "uaenative.library",
            "uae_native_code",
        ]
        resident_item.add(uaenative_library_item)

        if c.uae_sana2 == "true":
            uaenet_device_item = Item("UAE uaenet.device")
        else:
            uaenet_device_item = InactiveItem("No uaenet.device")
        uaenet_device_item.represents = ["uae_sana2"]
        resident_item.add(uaenet_device_item)

    if c.uae_gfxcard_type:
        graphics_card_item = Item(
            f"{c.int_graphics_card_name} {c.uae_gfxcard_size} MB"
        )
        if flatten:
            if c.int_graphics_card_bus == "zorro-ii":
                graphics_card_item.extra = "Zorro II"
            elif c.int_graphics_card_bus == "zorro-iii":
                graphics_card_item.extra = "Zorro III"
            model.add(graphics_card_item)
        elif c.int_graphics_card_bus == "zorro-ii":
            zorro_ii_item.add(graphics_card_item)
        elif c.int_graphics_card_bus == "zorro-iii":
            zorro_iii_item.add(graphics_card_item)
        else:
            model.add(graphics_card_item)

    if c.uae_toccata == "true":
        sound_card_item = Item("Toccata")
        sound_card_item.represents = ["sound_card", "uae_toccata"]
        if flatten:
            sound_card_item.extra = "Zorro II"
            model.add(sound_card_item)
        else:
            zorro_ii_item.add(sound_card_item)

    if c.uae_a2065:
        network_card_item = Item("A2065")
        network_card_item.represents = ["network_card", "uae_a2065"]
        if flatten:
            network_card_item.extra = "Zorro II"
            model.add(network_card_item)
        else:
            zorro_ii_item.add(network_card_item)

    joystick_port_0_item = create_joystick_port_item(c, 0)
    joystick_port_1_item = create_joystick_port_item(c, 1)
    joystick_port_2_item = create_joystick_port_item(c, 2)
    joystick_port_3_item = create_joystick_port_item(c, 3)

    model.add(joystick_port_0_item)
    model.add(joystick_port_1_item)

    if joystick_port_2_item.active or joystick_port_3_item.active:
        parallel_port_item = Item("Parallel Port Joystick Adapter")
        model.add(parallel_port_item)
        parallel_port_item.add(joystick_port_2_item)
        parallel_port_item.add(joystick_port_3_item)
    else:
        parallel_port_item = InactiveItem("No Parallel Port Device")
        model.add(parallel_port_item)

    for i in range(4):
        drive_type = getattr(c, f"uae_floppy{i}type")
        if drive_type == "0":
            description = '3.5" DD'
        elif drive_type == "1":
            description = '3.5" HD'
        elif drive_type == "2":
            description = '5.25" SD'
        elif drive_type == "3":
            description = '3.5" DD (ESCOM)'
        else:
            description = None
        if description:
            drive_item = Item(
                f"{description} Floppy Drive [DF{i}]"
            )
        else:
            drive_item = InactiveItem(f"No Floppy Drive [DF{i}]")
        drive_item.represents = [
            f"floppy_drive_{i}",
            f"uae_df{i}type",
        ]
        model.add(drive_item)

    return model
