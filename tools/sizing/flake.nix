{
  # Pinned toolchain for the sizing harness (S-013, S-015): a measurement tool, not hub product code.
  # Run on ksb: ksb run <path-to-this-dir>#sizing -- run --out /job/out   (S-013)
  #             ksb run <path-to-this-dir>#sizing -- tsra --out /job/out   (S-015)
  description = "scitadel-hub sizing harness (S-013, S-015)";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  # tessera dev, pinned: the .tsra writer under test (S-015). Built from source by its own flake.
  inputs.tessera.url = "github:vig-os/tessera/f390528eb2bfa3fc4ea474d9129c242b906e8e0a";
  outputs = { self, nixpkgs, tessera }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      tess = tessera.packages.x86_64-linux;
      py = pkgs.python3.withPackages (p: [ p.tantivy p.tokenizers p.pyarrow p.zstandard p.numpy p.typing-extensions ]);
      # The tessera-py wheel (abi3, pure extension) unpacked onto a PYTHONPATH.
      tesseraPy = pkgs.runCommand "tessera-py" { nativeBuildInputs = [ pkgs.unzip ]; } ''
        mkdir $out && unzip -q ${tess.wheel}/*.whl -d $out
      '';
      mk = name: tail: pkgs.writeShellApplication {
        inherit name;
        runtimeInputs = [ py pkgs.poppler-utils pkgs.cacert pkgs.libjxl pkgs.uv tess.default ];
        text = ''
          export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
          # vortex-data (PyPI, manylinux wheel; the version tessera links) for the shapes tessera cannot write yet.
          VORTEX=''${VORTEX_DIR:-/tmp/vortex-py}
          [ -d "$VORTEX/vortex" ] || uv pip install --quiet --python ${py}/bin/python --no-deps --target "$VORTEX" vortex-data==0.93.0
          [ -d "$VORTEX/substrait" ] || uv pip install --quiet --python ${py}/bin/python --target "$VORTEX" 'substrait>=0.23,<0.29'
          export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib
          export PYTHONPATH=${./.}:${tesseraPy}:$VORTEX
          exec ${tail}
        '';
      };
      sizing = mk "sizing" ''python3 -m sizing.run "$@"'';
      sizing-py = mk "sizing-py" ''python3 "$@"'';  # the same pinned environment, for probes
    in {
      apps.x86_64-linux.sizing = { type = "app"; program = "${sizing}/bin/sizing"; };
      apps.x86_64-linux.py = { type = "app"; program = "${sizing-py}/bin/sizing-py"; };
      devShells.x86_64-linux.default = pkgs.mkShell { packages = [ py pkgs.poppler-utils pkgs.libjxl ]; };
    };
}
