{
  description = "The hermetic toolchain thevlang/vlang:nix is built with";

  # The same pin as Dockerfile.nix.build. Bump both, or neither: the image and
  # this shell are meant to be the same environment.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/39ad350a0602fa0a58a544344e3e9187526ea45c";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in
    forAllSystems (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.${system}.default = pkgs.mkShell {
          name = "vlang-build";

          # Exactly what Dockerfile.nix.build installs, so a build here and a
          # build in :nix produce the same V.
          packages = with pkgs; [
            git
            make
            gcc
            pkg-config
            # V links against these when it finds them.
            openssl
            sqlite
          ];
        };
      });
}
