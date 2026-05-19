# CV sources

Edit these Markdown files when you want to change a CV:

| Variant | Source file | Finished PDFs |
| --- | --- | --- |
| `luxury-retail` | `andrej-spirov-cv-luxury-retail.md` | `../output/andrej-spirov-cv-luxury-retail.pdf`, `../output/andrej-spirov-cv-luxury-retail-ats.pdf` |
| `luxury-retail-lt` | `andrej-spirov-cv-luxury-retail-lt.md` | `../output/andrej-spirov-cv-luxury-retail-lt.pdf`, `../output/andrej-spirov-cv-luxury-retail-lt-ats.pdf` |
| `operations-management` | `andrej-spirov-cv-operations-management.md` | `../output/andrej-spirov-cv-operations-management.pdf`, `../output/andrej-spirov-cv-operations-management-ats.pdf` |
| `it-business` | `andrej-spirov-cv-it-business.md` | `../output/andrej-spirov-cv-it-business.pdf`, `../output/andrej-spirov-cv-it-business-ats.pdf` |

Use the visual PDF when emailing a person. Use the `-ats.pdf` file for online hiring portals.

Rebuild all PDFs and Canva paste files:

```bash
python3 cv/build_cv_pdf.py --all
```

Generated Canva paste files are written to `../output/canva/`. Keep `cv/` for editable source files, the build script, profiles, metrics, fonts, and assets.
