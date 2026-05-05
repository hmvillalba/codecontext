"""Extract Observer, Event, and Listener mappings from Laravel PHP code."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import EventMapping, ObserverMapping


_RE_OBSERVE_CALL = re.compile(
    r"(\w+)::observe\s*\(\s*([\w\\]+)::class"
)
_RE_EVENT_LISTEN = re.compile(
    r"(\w+)::listen\s*\(\s*([\w\\]+)::class"
)
_RE_EVENT_DISPATCH = re.compile(
    r"event\s*\(\s*new\s+([\w\\]+)\b"
)
_RE_LISTEN_ARRAY_ENTRY = re.compile(
    r"([\w\\]+)::class\s*=>\s*\[(.*?)\]",
    re.DOTALL,
)
_RE_CLASS_IN_ARRAY = re.compile(r"([\w\\]+)::class")


def extract_observers(root: Path, index_files=None) -> list[ObserverMapping]:
    observers: list[ObserverMapping] = []
    seen: set[tuple[str, str]] = set()

    provider_dirs = [
        root / "app" / "Providers",
        root / "app" / "app" / "Providers",
    ]

    for pd in provider_dirs:
        if not pd.is_dir():
            continue
        for php_file in pd.rglob("*.php"):
            try:
                content = php_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rel = str(php_file.relative_to(root)).replace("\\", "/")

            for m in _RE_OBSERVE_CALL.finditer(content):
                model = m.group(1)
                observer = m.group(2).rsplit("\\", 1)[-1]
                key = (model, observer)
                if key not in seen:
                    seen.add(key)
                    observers.append(ObserverMapping(
                        model=model,
                        observer=observer,
                        file_path=rel,
                        events=["created", "updated", "deleted"],
                    ))

    if index_files:
        _extract_observer_files(index_files, observers, seen, root)

    return observers


def _extract_observer_files(index_files, observers: list[ObserverMapping], seen: set, root: Path):
    registered_observers = {o.observer for o in observers}

    for f in index_files:
        for n in f.nodes:
            if "Observer" in n.name and n.node_type.value in ("class",):
                if n.name in registered_observers:
                    continue
                events = []
                for method_name in n.meta.get("methods", []):
                    if method_name in ("created", "updated", "deleted", "restored", "forceDeleted"):
                        events.append(method_name)
                if events:
                    observers.append(ObserverMapping(
                        model="",
                        observer=n.name,
                        file_path=f.file_path,
                        events=events,
                    ))
                    registered_observers.add(n.name)


def extract_events(root: Path) -> list[EventMapping]:
    events: list[EventMapping] = []
    seen: set[str] = set()

    provider_dirs = [
        root / "app" / "Providers",
        root / "app" / "app" / "Providers",
    ]

    for pd in provider_dirs:
        if not pd.is_dir():
            continue
        for php_file in pd.rglob("*.php"):
            try:
                content = php_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rel = str(php_file.relative_to(root)).replace("\\", "/")

            for m in _RE_LISTEN_ARRAY_ENTRY.finditer(content):
                event_cls = m.group(1).rsplit("\\", 1)[-1]
                listener_block = m.group(2)
                listeners = [
                    l.rsplit("\\", 1)[-1]
                    for l in _RE_CLASS_IN_ARRAY.findall(listener_block)
                ]
                if event_cls not in seen:
                    seen.add(event_cls)
                    events.append(EventMapping(
                        event=event_cls,
                        listeners=listeners,
                        file_path=rel,
                    ))

            for m in _RE_EVENT_LISTEN.finditer(content):
                event_cls = m.group(2).rsplit("\\", 1)[-1]
                if event_cls not in seen:
                    seen.add(event_cls)
                    events.append(EventMapping(
                        event=event_cls,
                        listeners=[],
                        file_path=rel,
                    ))

    for php_file in root.rglob("*.php"):
        parts = [p.lower() for p in php_file.parts]
        if "vendor" in parts or "node_modules" in parts:
            continue
        if "events" not in parts and "listeners" not in parts:
            continue
        try:
            content = php_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_EVENT_DISPATCH.finditer(content):
            event_cls = m.group(1).rsplit("\\", 1)[-1]
            if event_cls not in seen:
                seen.add(event_cls)
                rel = str(php_file.relative_to(root)).replace("\\", "/")
                events.append(EventMapping(
                    event=event_cls,
                    listeners=[],
                    file_path=rel,
                ))

    return events
