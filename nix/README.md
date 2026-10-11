# The Nix variant

`nix flake` gives you a development shell with exactly the toolchain
`docker/vlang/Dockerfile.nix.build` installs:

```bash
nix develop          # gcc, make, git, openssl, sqlite, pkg-config
make                 # builds ./v in this checkout
```

`nixpkgs` is pinned inline in the flake's `url`,
`github:NixOS/nixpkgs/39ad350a0602fa0a58a544344e3e9187526ea45c`, to the same
revision `NIXPKGS_REV` names in `Dockerfile.nix.build`, so bumping the pin changes
both together. There is no committed `flake.lock`: the revision is in the input
URL, which pins the source tree but not the dependency graph a lock file would
freeze. Run `nix flake update` once and commit the result if you want that, or
leave it as is for a source pin only.

## Why there is no `nix build .#image`

A pure Nix image would be built by `pkgs.dockerTools.buildImage` /
`nix2container.buildImage`, and it is worth knowing why one is *not* offered
here: V bakes the location of its own stdlib into the compiler binary at compile
time.

- `@VMODROOT` is resolved at parse time to the directory containing the nearest
  `v.mod` (see `vmod_root_for_file` in `vlib/v/parser/parser.v`).
- At run time `detect_vroot` (`vlib/v/pref/pref.v:336`) returns that baked path
  as-is, before any fallback to searching.
- `$embed_file('@VMODROOT/...')` in V's own sources keeps the path, so a V
  binary whose build directory no longer exists cannot start.

Measured: a V compiler built in one directory and moved to another panics with

    V panic: EmbedFileData error: files "manual_stdlib_c_headers.h" and
    "<build-dir>/vlib/v/gen/c/manual_stdlib_c_headers.h" do not exist

A Nix build runs in a sandbox whose build directory is absent from the built
output, so a `dockerTools`-built V would carry a dead path and be unusable. That
is why the Nix variant is built by `Dockerfile.nix` — which builds V in
`/opt/vlang` and installs it at the same `/opt/vlang` — with the *toolchain*
coming from Nix, which is where the reproducibility actually comes from.

The same constraint is why `nixpkgs`' own `vlang` package is not used to build
`:nix`: it is built in the Nix sandbox, so its `@VMODROOT` points somewhere that
does not exist in an image.

If you do want a pure Nix image, the derivation must build V at a path that also
exists in the image (a fixed subdirectory of the build top), and the payload for
`v fmt`/`v doc` additionally needs a `GNUmakefile` next to `vlib/v`, because
`find_vroot` in `cmd/v/v.v:1222` checks for exactly that.
