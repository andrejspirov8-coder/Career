"""The versioned CV catalogue loaded from the single YAML source of truth."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from career_job_search.core.paths import project_path

CATALOGUE_PATH = project_path("cv", "variant_profiles.yaml")


class CvVariantV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    language: Literal["English", "Lithuanian"]
    focus: str
    display_order: int = Field(ge=0)
    source_filename: str
    pdf_stem: str
    target_titles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)


class CvCatalogueV1(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: Literal["cv_catalogue_v1"] = Field(
        default="cv_catalogue_v1",
        alias="schema",
    )
    variants: list[CvVariantV1]


def load_cv_catalogue(path: Path = CATALOGUE_PATH) -> CvCatalogueV1:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    version = raw.get("schema") or raw.get("schema_version")
    if version is not None and version != "cv_catalogue_v1":
        raise ValueError(
            f"Unsupported cv/variant_profiles.yaml schema {version!r} "
            "(expected 'cv_catalogue_v1')"
        )
    variants = raw.get("variants")
    if not isinstance(variants, dict) or not variants:
        raise ValueError("variant_profiles.yaml must contain a non-empty variants map")

    parsed: list[CvVariantV1] = []
    for slug, value in variants.items():
        if not isinstance(value, dict):
            raise ValueError(f"CV variant {slug!r} must be a mapping")
        parsed.append(
            CvVariantV1(
                slug=str(slug),
                name=str(value.get("name") or "").strip(),
                language=str(value.get("language") or "").strip(),
                focus=str(value.get("focus") or "").strip(),
                display_order=int(value.get("display_order") or 0),
                source_filename=str(value.get("markdown") or "").strip(),
                pdf_stem=str(value.get("pdf_stem") or "").strip(),
                target_titles=[str(item) for item in value.get("target_titles") or []],
                keywords=[str(item) for item in value.get("keywords") or []],
                negative_keywords=[
                    str(item) for item in value.get("negative_keywords") or []
                ],
            )
        )
    for variant in parsed:
        if not variant.name or not variant.focus:
            raise ValueError(f"CV variant {variant.slug!r} is missing display metadata")
        if not variant.source_filename or not variant.pdf_stem:
            raise ValueError(f"CV variant {variant.slug!r} is missing file metadata")
    parsed.sort(key=lambda variant: (variant.display_order, variant.slug))
    return CvCatalogueV1(variants=parsed)


def cv_variant_tuples(
    *,
    catalogue: CvCatalogueV1 | None = None,
    root: Path | None = None,
) -> tuple[tuple[str, Path, Path, Path], ...]:
    data = catalogue or load_cv_catalogue()
    project_root = root or project_path()
    cv_root = project_root / "cv"
    output_root = project_root / "output"
    return tuple(
        (
            variant.slug,
            cv_root / variant.source_filename,
            output_root / f"{variant.pdf_stem}.pdf",
            output_root / "canva" / f"{variant.pdf_stem}-canva.txt",
        )
        for variant in data.variants
    )
