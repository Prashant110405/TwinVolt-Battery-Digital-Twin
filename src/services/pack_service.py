"""Battery Pack Management Application Service.

Provides lifecycle coordination, registry storage, and declarative profile loading
for BatteryPack domain entities without HTTP or transport dependencies.
"""

from pathlib import Path
import threading
from typing import Any, Mapping, Optional, Sequence, Union

from src.domain.battery.entities import BatteryPack
from src.schemas.loader import BatteryProfileLoader
from src.services.exceptions import DuplicateEntityError, PackNotFoundError


class PackManagementService:
    """Application service for managing battery pack domain entities and configurations.

    Coordinates in-memory registration, lookup, and declarative profile loading
    via the safe BatteryProfileLoader schema engine.
    """

    def __init__(self, initial_packs: Optional[Sequence[BatteryPack]] = None) -> None:
        self._registry: dict[str, BatteryPack] = {}
        self._lock = threading.RLock()

        if initial_packs:
            for pack in initial_packs:
                self.register_pack(pack)

    def register_pack(self, pack: BatteryPack, overwrite: bool = False) -> BatteryPack:
        """Registers a BatteryPack domain entity in the pack registry.

        Args:
            pack: BatteryPack instance to register.
            overwrite: If True, replaces any existing pack with the same pack_id.

        Returns:
            The registered BatteryPack.

        Raises:
            TypeError: If pack is not a BatteryPack instance.
            DuplicateEntityError: If pack_id already exists and overwrite is False.
        """
        if not isinstance(pack, BatteryPack):
            raise TypeError(f"Expected BatteryPack instance, got {type(pack).__name__}.")

        with self._lock:
            if pack.pack_id in self._registry and not overwrite:
                raise DuplicateEntityError(
                    f"Battery pack with identifier '{pack.pack_id}' already exists.",
                    service_name="PackManagementService",
                    details={"pack_id": pack.pack_id},
                )
            self._registry[pack.pack_id] = pack
            return pack

    def create_pack_from_profile(
        self,
        profile_data: Union[str, Mapping[str, Any]],
        format_type: str = "dict",
        overwrite: bool = False,
    ) -> BatteryPack:
        """Loads a declarative profile and materializes a validated BatteryPack entity.

        Args:
            profile_data: Dictionary mapping, JSON string, or YAML string.
            format_type: Format hint ("dict", "json", "yaml").
            overwrite: If True, replaces existing pack with same ID.

        Returns:
            Registered BatteryPack domain entity.
        """
        if isinstance(profile_data, Mapping):
            schema = BatteryProfileLoader.load_from_dict(profile_data)
        elif isinstance(profile_data, str):
            fmt = format_type.lower()
            if fmt == "json" or (fmt == "dict" and profile_data.strip().startswith("{")):
                schema = BatteryProfileLoader.load_from_json(profile_data)
            else:
                schema = BatteryProfileLoader.load_from_yaml(profile_data)
        else:
            raise TypeError(
                f"Expected mapping or string for profile_data, got {type(profile_data).__name__}."
            )

        pack = schema.to_domain_pack()
        return self.register_pack(pack, overwrite=overwrite)

    def create_pack_from_file(
        self,
        file_path: Union[str, Path],
        overwrite: bool = False,
    ) -> BatteryPack:
        """Loads a file (.yaml, .yml, or .json) and registers the materialized BatteryPack.

        Args:
            file_path: Path to profile file.
            overwrite: If True, replaces existing pack with same ID.

        Returns:
            Registered BatteryPack domain entity.
        """
        pack = BatteryProfileLoader.create_domain_pack_from_file(file_path)
        return self.register_pack(pack, overwrite=overwrite)

    def get_pack(self, pack_id: str) -> BatteryPack:
        """Retrieves a registered BatteryPack by its identifier.

        Args:
            pack_id: Battery pack identifier.

        Returns:
            BatteryPack instance.

        Raises:
            PackNotFoundError: If pack_id is not registered.
        """
        with self._lock:
            pack = self._registry.get(pack_id)
            if pack is None:
                raise PackNotFoundError(
                    f"Battery pack '{pack_id}' not found in registry.",
                    service_name="PackManagementService",
                    details={"pack_id": pack_id},
                )
            return pack

    def list_packs(self) -> tuple[BatteryPack, ...]:
        """Returns all registered BatteryPack instances."""
        with self._lock:
            return tuple(self._registry.values())

    def delete_pack(self, pack_id: str) -> bool:
        """Removes a BatteryPack from the registry.

        Args:
            pack_id: Battery pack identifier.

        Returns:
            True if removed, False if pack was not found.
        """
        with self._lock:
            if pack_id in self._registry:
                del self._registry[pack_id]
                return True
            return False

    def exists(self, pack_id: str) -> bool:
        """Checks if a battery pack identifier is registered."""
        with self._lock:
            return pack_id in self._registry

    @property
    def count(self) -> int:
        """Total number of registered packs."""
        with self._lock:
            return len(self._registry)

    def clear(self) -> None:
        """Clears all registered battery packs."""
        with self._lock:
            self._registry.clear()
