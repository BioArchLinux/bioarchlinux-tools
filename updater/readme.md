# Updater

Scripts used to help update the PKGBUILD and `lilac.yaml` automatically.

For usage, run with argument `-h`.

## TODO

- [x] Use databases to store metadata, currently, each query takes about 10s. Now each query finishes in 1 second
- [ ] Support packages hosted in github.
- [ ] Clean codes
- [x] `depends_updater` supports archiving PKGs automatically.
- [ ] generate PKGBUILD for missing dependencies `depends_updater`
- [x] merge `sync_meta_data` into `dbmanager`
- [x] merge `pkg_archiver` into `dbmanager`
