# Mixed sample (test fixture)

One folder that both runtimes of `dd-inventory` describe: natively and under Pyodide in the
browser bundle's parity check (`inventory/browser/README.md`). Made up for the tests.

| File | Why it is here |
| --- | --- |
| `tables/plots.csv` | A CSV table: integer, number, boolean, date and string columns |
| `tables/nested/readings.tsv` | A TSV table in a nested folder |
| `images/plot-map.png` | A format with a byte signature |
| `reports/report.docx` | A container format (Word) |
| `misnamed.csv` | A PNG under a table's extension |
| `empty.txt` | An empty file |
| `.DS_Store`, `.hidden/` | Hidden: skipped and counted |
