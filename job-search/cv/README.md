# CV sources

For normal use, open **CV Studio** in the local dashboard. It edits these same
Markdown sources, rebuilds only the selected variant, shows both PDF formats,
and keeps a private recovery version before each saved change.

Edit these Markdown files directly only when the dashboard is unavailable:

| Variant | Source file | Finished PDFs |
| --- | --- | --- |
| `luxury-retail` | `andrej-spirov-cv-luxury-retail.md` | `../output/andrej-spirov-cv-luxury-retail.pdf`, `../output/andrej-spirov-cv-luxury-retail-ats.pdf` |
| `luxury-retail-lt` | `andrej-spirov-cv-luxury-retail-lt.md` | `../output/andrej-spirov-cv-luxury-retail-lt.pdf`, `../output/andrej-spirov-cv-luxury-retail-lt-ats.pdf` |
| `operations-management` | `andrej-spirov-cv-operations-management.md` | `../output/andrej-spirov-cv-operations-management.pdf`, `../output/andrej-spirov-cv-operations-management-ats.pdf` |
| `operations-management-lt` | `andrej-spirov-cv-operations-management-lt.md` | `../output/andrej-spirov-cv-operations-management-lt.pdf`, `../output/andrej-spirov-cv-operations-management-lt-ats.pdf` |
| `business-process-operations` | `andrej-spirov-cv-business-process-operations.md` | `../output/andrej-spirov-cv-business-process-operations.pdf`, `../output/andrej-spirov-cv-business-process-operations-ats.pdf` |
| `it-business` | `andrej-spirov-cv-it-business.md` | `../output/andrej-spirov-cv-it-business.pdf`, `../output/andrej-spirov-cv-it-business-ats.pdf` |

Use the visual PDF when emailing a person. Use the `-ats.pdf` file for online hiring portals.

Rebuild all PDFs and Canva paste files:

```bash
uv run python cv/build_cv_pdf.py --all
```

Rebuild only one variant:

```bash
uv run python cv/build_cv_pdf.py --variant business-process-operations
```

Generated Canva paste files are written to `../output/canva/`. Keep `cv/` for editable source files, the build script, profiles, metrics, fonts, and assets.

Use `business-process-operations` first for Vilnius business analyst, process analyst, operations analyst, implementation support, and customer operations roles. Use `it-business` only for IT-adjacent support roles where the advert is about systems support rather than software delivery.

Use `operations-management-lt` for Lithuanian-language operations, process-management, process-improvement, and customer-experience leadership roles. Use `luxury-retail-lt` for Lithuanian store, salon, boutique, jewellery, perfume, and premium-retail roles.
