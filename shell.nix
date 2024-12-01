{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShellNoCC {

  packages = with pkgs; [
      python312Full
      python312Packages.flask
      python312Packages.pip
      python312Packages.kubernetes
      python312Packages.fastapi
      pipreqs
      python312Packages.autopep8
  ];

}
