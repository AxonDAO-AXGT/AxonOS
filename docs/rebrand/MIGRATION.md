# Migration Guide: DeSciOS → AxonOS

This document describes breaking changes and migration steps for users upgrading from DeSciOS to AxonOS.

## Overview

AxonOS is a rebranded fork of DeSciOS. The core functionality remains unchanged, but branding, naming, and some paths have been updated.

## Breaking Changes

### 1. CLI Binary Name

**Old**: `descios`
**New**: `axonos`

**Migration**:
```bash
# Old command
descios --version

# New command
axonos --version
```

**Note**: If you have scripts using `descios`, update them to use `axonos`.

### 2. Directory Names

**Old**: 
- `descios_launcher/`
- `descios_assistant/`
- `descios_plugins/`

**New**:
- `axonos_launcher/`
- `axonos_assistant/`
- `axonos_plugins/`

**Migration**: If you have custom code importing from these directories, update import paths:
```python
# Old
from descios_launcher import something

# New
from axonos_launcher import something
```

### 3. Docker Image Tags

**Old**: `descios:custom`, `descios:latest`
**New**: `axonos:custom`, `axonos:latest`

**Migration**:
```bash
# Rebuild with new tag
docker build -t axonos:custom .

# Or tag existing image
docker tag descios:custom axonos:custom
```

### 4. Container Names

**Old**: `descios`
**New**: `axonos`

**Migration**:
```bash
# Stop and remove old container
docker stop descios
docker rm descios

# Start with new name
docker run -d --name axonos axonos:custom
```

### 5. Config Files

**Old**: `descios.yaml` (if used)
**New**: `axonos.yaml`

**Migration**: The launcher will continue to read `descios.yaml` with a deprecation warning. Migrate by:
1. Rename `descios.yaml` to `axonos.yaml`
2. Update any references in your scripts

### 6. CSS Theme Classes

**Old**: `.descios-branding`, `.descios-theme`, etc.
**New**: `.axonos-branding`, `.axonos-theme`, etc.

**Migration**: If you have custom CSS or HTML using these classes, update class names.

## Non-Breaking Changes

### User-Facing Text
- Window titles, UI labels, help text now show "AxonOS" instead of "DeSciOS"
- No functional impact

### Documentation
- README, guides, and docs updated to AxonOS branding
- No code changes needed

### GitHub URLs
- Repository URLs updated to new location
- Update your git remotes:
```bash
git remote set-url origin https://github.com/[new-org]/axonos.git
```

## Backward Compatibility

The following are maintained for compatibility:

1. **Username**: The default username `deScier` is kept for backward compatibility
2. **Config files**: Old config file names are still read (with deprecation warning)
3. **Docker paths**: During transition, both old and new paths may work

## Upgrade Steps

1. **Pull latest code**:
   ```bash
   git pull origin main
   ```

2. **Update Docker images**:
   ```bash
   docker build -t axonos:custom .
   ```

3. **Update running containers**:
   ```bash
   docker stop descios
   docker rm descios
   docker run -d --name axonos axonos:custom
   ```

4. **Update scripts**: Search for `descios` references and update to `axonos`

5. **Update config**: Rename config files if applicable

## Rollback

If you need to rollback:

1. Use previous git commit/tag
2. Rebuild Docker images with old tags
3. Restore old config files

## Support

For issues during migration:
- Check this document first
- Review `docs/rebrand/REPORT.md` for detailed changes
- Open an issue on GitHub
