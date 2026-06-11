"""Konfiguration: kuratierte Quellenliste (sources.yaml) als striktes Schema."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

ROOT = Path(__file__).resolve().parents[2]

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class CatalogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    i14y_publicservices_url: str
    ech0070_inventory_url: str


class CrawlerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_agent: str
    delay_seconds: float = 2.0


class ProcessSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    service_name: str
    target_audience: Literal["bevoelkerung", "wirtschaft", "behoerden"]
    official_urls: list[str]
    catalog_keywords: list[str] = []
    notes: str = ""

    @field_validator("id")
    @classmethod
    def _kebab(cls, v: str) -> str:
        if not KEBAB.match(v):
            raise ValueError(f"id muss kebab-case sein: {v!r}")
        return v

    @field_validator("official_urls")
    @classmethod
    def _urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("official_urls darf nicht leer sein")
        for u in v:
            if not u.startswith("https://"):
                raise ValueError(f"nur https-Quellen erlaubt: {u!r}")
        return v


class SourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog: CatalogConfig
    crawler: CrawlerConfig
    processes: list[ProcessSource]

    def by_id(self, proc_id: str) -> ProcessSource:
        for p in self.processes:
            if p.id == proc_id:
                return p
        raise KeyError(f"Leistung {proc_id!r} nicht in sources.yaml")


def load_sources(path: Path | None = None) -> SourcesConfig:
    path = path or ROOT / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourcesConfig.model_validate(data)
