#!/bin/bash
set -euo pipefail

# install deps
npm i --legacy-peer-deps

# Webpack imports this on first compile; start:css used to race and lose.
npm run build:css

# start running (css watcher + webpack)
npm run start:docker
