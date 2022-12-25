from __future__ import annotations

import sys
from collections.abc import Callable
from inspect import isclass
from typing import Any, TypeVar, overload

if sys.version_info >= (3, 10):
    from importlib.metadata import EntryPoint, entry_points
else:
    from importlib_metadata import EntryPoint, entry_points

T_Object = TypeVar("T_Object")


def qualified_name(obj) -> str:
    """
    Return the qualified name (e.g. package.module.Type) for the given object.

    If ``obj`` is not a class, the returned name will match its type instead.

    """
    cls = obj if isclass(obj) else type(obj)
    if cls.__module__ == "builtins":
        return cls.__name__
    else:
        return f"{cls.__module__}.{cls.__qualname__}"


def callable_name(func: Callable[..., Any]) -> str:
    """Return the qualified name (e.g. package.module.func) for the given callable."""
    if func.__module__ == "builtins":
        return func.__name__
    else:
        return f"{func.__module__}.{func.__qualname__}"


def merge_config(
    original: dict[str, Any] | None, overrides: dict[str, Any] | None
) -> dict[str, Any]:
    """
    Return a copy of the ``original`` configuration dictionary, with overrides from
    ``overrides`` applied.

    This similar to what :meth:`dict.update` does, but when a dictionary is about to be
    replaced with another dictionary, it instead merges the contents.

    If a key in ``overrides`` is a dotted path (ie. ``foo.bar.baz: value``), it is
    assumed to be a shorthand for ``foo: {bar: {baz: value}}``.

    :param original: a configuration dictionary (or ``None``)
    :param overrides: a dictionary containing overriding values to the configuration
        (or ``None``)
    :return: the merge result

    """
    copied = original.copy() if original else {}
    if overrides:
        for key, value in overrides.items():
            if "." in key:
                key, rest = key.split(".", 1)
                value = {rest: value}

            orig_value = copied.get(key)
            if isinstance(orig_value, dict) and isinstance(value, dict):
                copied[key] = merge_config(orig_value, value)
            else:
                copied[key] = value

    return copied


class PluginContainer:
    """
    A convenience class for loading and instantiating plugins through the use of entry
    points.

    :param namespace: a setuptools entry points namespace
    :param base_class: the base class for plugins of this type (or ``None`` if the
        entry points don't point to classes)
    """

    __slots__ = "namespace", "base_class", "_entrypoints"

    def __init__(self, namespace: str, base_class: type | None = None) -> None:
        self.namespace = namespace
        self.base_class = base_class
        group = entry_points(group=namespace)  # type: ignore[attr-defined]
        self._entrypoints = {ep.name: ep for ep in group}

    @overload
    def resolve(self, obj: str) -> Any:
        pass

    @overload
    def resolve(self, obj: T_Object) -> T_Object:
        pass

    def resolve(self, obj: Any) -> Any:
        """
        Resolve a reference to an entry point.

        If ``obj`` is a string, the named entry point is loaded from this container's
        namespace. Otherwise, ``obj`` is returned as is.

        :param obj: an entry point identifier, an object reference or an arbitrary
            object
        :return: the loaded entry point, resolved object or the unchanged input value
        :raises LookupError: if ``obj`` was a string but the named entry point was not
            found

        """
        if not isinstance(obj, str):
            return obj

        value = self._entrypoints.get(obj)
        if value is None:
            raise LookupError(f"no such entry point in {self.namespace}: {obj}")

        if isinstance(value, EntryPoint):
            value = self._entrypoints[obj] = value.load()

        return value

    def create_object(self, type: type | str, **constructor_kwargs) -> Any:
        """
        Instantiate a plugin.

        The entry points in this namespace must point to subclasses of the
        ``base_class`` parameter passed to this container.

        :param type: an entry point identifier or an actual class object
        :param constructor_kwargs: keyword arguments passed to the constructor of the
            plugin class
        :return: the plugin instance

        """
        assert self.base_class, "base class has not been defined"
        plugin_class = self.resolve(type)
        if not isclass(plugin_class) or not issubclass(plugin_class, self.base_class):
            raise TypeError(
                f"{qualified_name(plugin_class)} is not a subclass of "
                f"{qualified_name(self.base_class)}"
            )

        return plugin_class(**constructor_kwargs)

    @property
    def names(self) -> list[str]:
        """Return names of all entry points in this namespace."""
        return list(self._entrypoints)

    def all(self) -> list[Any]:
        """
        Load all entry points (if not already loaded) in this namespace and return the
        resulting objects as a list.

        """
        values = []
        for name, value in self._entrypoints.items():
            if isinstance(value, EntryPoint):
                value = self._entrypoints[name] = value.load()

            values.append(value)

        return values

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(namespace={self.namespace!r}, "
            f"base_class={qualified_name(self.base_class)})"
        )