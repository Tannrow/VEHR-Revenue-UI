## ERA Extract (Azure Document Intelligence)

### Required environment variables
- `AZURE_DOCINTEL_ENDPOINT`
- `AZURE_DOCINTEL_KEY`

Put them in a local `.env` at the repo root (already gitignored).

### Run once
```powershell
.\.venv313\Scripts\python.exe -m scripts.era_extract.extract_era --pdf "inputs/eras\\your-era.pdf"
```

### Watch folder
```powershell
.\.venv313\Scripts\python.exe -m scripts.era_extract.watch_folder
```

