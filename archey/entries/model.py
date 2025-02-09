"""Hardware model information detection class"""

import os
import platform
import re

from subprocess import CalledProcessError, DEVNULL, check_output
from typing import Optional

from archey.entry import Entry


class Model(Entry):
    """Uses multiple methods to retrieve some information about the host hardware"""

    LINUX_DMI_SYS_PATH = "/sys/devices/virtual/dmi/id"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.value = \
            self._fetch_virtual_env_info() \
            or self._fetch_dmi_info() \
            or self._fetch_sysctl_hw() \
            or self._fetch_raspberry_pi_revision() \
            or self._fetch_android_device_model()

    def _fetch_virtual_env_info(self) -> Optional[str]:
        """
        Relying on some system tools, tries to gather some details about hypervisor.
        When available, relies on systemd.
        If running with enough privileges, `virt-what` and/or `dmidecode` may be called.
        """
        try:
            environment = check_output(
                'systemd-detect-virt',
                stderr=DEVNULL, universal_newlines=True
            ).rstrip()
        except CalledProcessError:
            # Not a virtual environment.
            environment = ""
        except FileNotFoundError:
            # If not available, let's query `virt-what` (privileges usually required).
            try:
                environment = ", ".join(
                    check_output(
                        "virt-what",
                        stderr=DEVNULL, universal_newlines=True
                    ).splitlines()
                )
            except (OSError, CalledProcessError):
                environment = ""

        # We couldn't retrieve any information from `systemd-detect-virt`, nor `virt-what`.
        if not environment:
            return None

        # Sometimes we may gather info added by hosting service provider by relying on `dmidecode`.
        try:
            product_name = check_output(
                ["dmidecode", "-s", "system-product-name"],
                stderr=DEVNULL, universal_newlines=True
            ).rstrip()
        except (OSError, CalledProcessError):
            product_name = self._default_strings.get("virtual_environment")

        # If we got there with some info, this _should_ be a virtual environment.
        return f"{product_name} ({environment})"

    @classmethod
    def _fetch_dmi_info(cls) -> Optional[str]:
        """Tries to open DMI Linux files, looking for hardware information"""
        def _read_dmi_file(file_name: str) -> str:
            try:
                with open(
                    os.path.join(cls.LINUX_DMI_SYS_PATH, file_name), encoding='UTF-8'
                ) as f_dmi_file:
                    dmi_info = f_dmi_file.read().rstrip()
            except OSError:
                return ""

            # Stop `/sys/devices/virtual/dmi/id/*` parsing on fuzzy data.
            if "to be filled" in dmi_info.lower():
                return ""

            return dmi_info

        # Fetch product name.
        product_name = _read_dmi_file("product_name")
        if product_name:
            product_info = [product_name]
            # Prepend product vendor name (if available).
            product_info.insert(0, _read_dmi_file("sys_vendor"))
            # Append product version (if available).
            product_info.append(_read_dmi_file("product_version"))

            return " ".join(filter(None, product_info))

        # Fetch board name.
        board_name = _read_dmi_file("board_name")
        if board_name:
            board_info = [board_name]
            # Prepend board vendor name (if available).
            board_info.insert(0, _read_dmi_file("board_vendor"))
            # Append board version (if available).
            board_info.append(_read_dmi_file("board_version"))

            return " ".join(filter(None, board_info))

        return None

    @staticmethod
    def _fetch_sysctl_hw() -> Optional[str]:
        # `hw.model` might be populated with CPU info on BSD platforms.
        # Let's only query this OID on Darwin (macOS).
        if platform.system() == 'Darwin':
            try:
                model = check_output(
                    ['sysctl', '-n', 'hw.model'],
                    stderr=DEVNULL, universal_newlines=True
                )
            except FileNotFoundError:
                return None
            except CalledProcessError:
                pass
            else:
                return model.rstrip().replace(',', '.')

        # Any other BSD (or derivatives).
        hw_oids = []
        for hw_oid in ('vendor', 'product', 'version'):
            try:
                sysctl_output = check_output(
                    ['sysctl', '-n', f'hw.{hw_oid}'],
                    stderr=DEVNULL, universal_newlines=True
                )
            except FileNotFoundError:
                return None
            except CalledProcessError:
                pass
            else:
                sysctl_output = sysctl_output.rstrip()
                if sysctl_output != 'None':
                    hw_oids.append(sysctl_output)

        return ' '.join(hw_oids) or None

    @staticmethod
    def _fetch_raspberry_pi_revision() -> Optional[str]:
        """Tries to retrieve 'Hardware' and 'Revision IDs' from `/proc/cpuinfo`"""
        try:
            with open('/proc/cpuinfo', encoding='ASCII') as f_cpu_info:
                cpu_info = f_cpu_info.read()
        except OSError:
            return None

        # If the output contains 'Hardware' and 'Revision'...
        hardware = re.search(r'(?<=Hardware\t: ).*', cpu_info)
        revision = re.search(r'(?<=Revision\t: ).*', cpu_info)
        if hardware and revision:
            # ... let's set a pretty info string with these data
            return f'Raspberry Pi {hardware.group(0)} (Rev. {revision.group(0)})'

        return None

    @staticmethod
    def _fetch_android_device_model() -> Optional[str]:
        """Tries to retrieve `brand` and `model` device properties on Android platforms"""
        try:
            brand = check_output(
                ['getprop', 'ro.product.brand'],
                universal_newlines=True
            ).rstrip()
            model = check_output(
                ['getprop', 'ro.product.model'],
                universal_newlines=True
            ).rstrip()
        except FileNotFoundError:
            return None

        return f'{brand} ({model})'
